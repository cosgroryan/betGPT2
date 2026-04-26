"""
Prediction service: loads trained model + calibrator, produces per-runner
predictions for a live race payload.

Returns a list of RunnerPrediction dicts sorted by value_edge descending.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from models.features import extract_features

log = logging.getLogger(__name__)

MODEL_PATH = Path(os.getenv("MODEL_PATH", "models/artifacts/model.pkl"))
CALIBRATOR_PATH = Path(os.getenv("CALIBRATOR_PATH", "models/artifacts/calibrator.pkl"))
FEATURES_PATH = Path("models/artifacts/feature_cols.json")

VALUE_EDGE_THRESHOLD = float(os.getenv("VALUE_EDGE_THRESHOLD", "0.03"))


@dataclass
class RunnerPrediction:
    entrant_id: str
    name: str
    runner_number: int
    barrier: int
    jockey: str
    trainer: str

    tab_fixed_win: Optional[float]
    tab_implied_prob: float
    model_prob: float
    model_odds: float
    value_edge: float          # model_prob - tab_implied_prob
    value_pct: float           # edge as % of implied (relative edge)
    is_value_bet: bool         # edge > threshold

    # For UI display
    fluc_drift: Optional[float]
    is_market_mover: bool
    is_favourite: bool
    speedmap_label: str
    speedmap_label_enc: int

    shap_top_features: list[dict] = field(default_factory=list)


@lru_cache(maxsize=1)
def _load_artifacts():
    """Load model, calibrator, feature list once and cache in memory."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"No model at {MODEL_PATH}. Run: python -m models.train"
        )
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    with open(CALIBRATOR_PATH, "rb") as f:
        calibrator = pickle.load(f)
    with open(FEATURES_PATH) as f:
        feature_cols = json.load(f)
    log.info("Model artifacts loaded from %s", MODEL_PATH)
    return model, calibrator, feature_cols


def reload_artifacts():
    """Call after retraining to hot-swap the model without restarting."""
    _load_artifacts.cache_clear()
    _load_artifacts()


def predict_race(payload: dict) -> list[RunnerPrediction]:
    """
    Given a full race detail payload (raceinfo schema), return predictions
    for all non-scratched runners.

    Parameters
    ----------
    payload: dict
        Full response from GET /racing/{event_id}
    """
    model, calibrator, feature_cols = _load_artifacts()

    race = payload.get("race", {})
    all_runners = payload.get("runners", [])
    money_tracker = payload.get("money_tracker", {})

    # Exclude scratched runners
    active_runners = [r for r in all_runners if not r.get("is_scratched") and not r.get("is_late_scratched")]
    if not active_runners:
        return []

    # Build feature matrix
    rows = []
    for runner in active_runners:
        feats = extract_features(runner, race, active_runners, money_tracker)
        rows.append(feats)

    df = pd.DataFrame(rows)

    # Align to training feature columns — fill missing with NaN
    for col in feature_cols:
        if col not in df.columns:
            df[col] = float("nan")
    X = df[feature_cols]

    raw_probs = model.predict_proba(X)[:, 1]
    cal_probs = calibrator.predict(raw_probs)

    # Normalise calibrated probs so field sums to 1.0 (bookmaker-style display)
    total = cal_probs.sum()
    if total > 0:
        norm_probs = cal_probs / total
    else:
        norm_probs = cal_probs

    # SHAP values for top-feature explanations
    shap_values_list = _compute_shap(model, X, feature_cols)

    predictions = []
    for i, (runner, feat_row) in enumerate(zip(active_runners, rows)):
        odds = runner.get("odds", {})
        fixed_win = feat_row.get("tab_fixed_win")
        tab_implied = feat_row.get("tab_implied_prob", 0.0)
        model_prob = float(norm_probs[i])
        model_odds = round(1 / model_prob, 2) if model_prob > 0 else 999.0
        edge = model_prob - tab_implied
        value_pct = (edge / tab_implied * 100) if tab_implied > 0 else 0.0

        sm = runner.get("speedmap", {})

        predictions.append(
            RunnerPrediction(
                entrant_id=runner.get("entrant_id", ""),
                name=runner.get("name", ""),
                runner_number=runner.get("runner_number", 0),
                barrier=runner.get("barrier", 0),
                jockey=runner.get("jockey", ""),
                trainer=runner.get("trainer_name", ""),
                tab_fixed_win=fixed_win,
                tab_implied_prob=round(tab_implied * 100, 1),
                model_prob=round(model_prob * 100, 1),
                model_odds=model_odds,
                value_edge=round(edge * 100, 1),
                value_pct=round(value_pct, 1),
                is_value_bet=edge > VALUE_EDGE_THRESHOLD,
                fluc_drift=feat_row.get("fluc_drift"),
                is_market_mover=bool(runner.get("mover")),
                is_favourite=bool(runner.get("favourite")),
                speedmap_label=str(sm.get("label", "")),
                speedmap_label_enc=int(feat_row.get("speedmap_label_enc", 2)),
                shap_top_features=shap_values_list[i] if shap_values_list else [],
            )
        )

    return sorted(predictions, key=lambda p: p.value_edge, reverse=True)


def _compute_shap(model, X: pd.DataFrame, feature_cols: list[str]) -> list[list[dict]]:
    """Return top-5 SHAP features per runner. Returns empty list if shap unavailable."""
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X)
        # For binary classification, shap_values returns list[arr]; take class-1
        if isinstance(shap_vals, list):
            shap_arr = shap_vals[1]
        else:
            shap_arr = shap_vals

        result = []
        for row_idx in range(len(X)):
            row_shap = shap_arr[row_idx]
            top_idx = np.argsort(np.abs(row_shap))[::-1][:5]
            top = [
                {
                    "feature": feature_cols[j],
                    "value": float(X.iloc[row_idx, j]),
                    "shap": float(row_shap[j]),
                }
                for j in top_idx
            ]
            result.append(top)
        return result
    except Exception as e:
        log.debug("SHAP computation skipped: %s", e)
        return []
