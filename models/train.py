"""
LightGBM training pipeline for betGPT2.

Steps:
  1. Load feature matrix from DB (build_training_frame)
  2. Time-based train/val/test split (no shuffle — forward-only)
  3. Hyperparameter search with Optuna
  4. Final model training
  5. Probability calibration (isotonic regression)
  6. Backtest: flat-stake ROI on value bets (edge > threshold)
  7. Save model + calibrator + feature list to artifacts/

Run:
  python -m models.train [--no-tune] [--edge-threshold 0.03]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

log = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("models/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

# Columns to drop before training (identifiers + targets)
DROP_COLS = ["event_id", "entrant_id", "won", "placed", "finish_position"]

# Minimum edge for a bet to be flagged as "value"
DEFAULT_EDGE_THRESHOLD = 0.03


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    from api.db import SessionLocal, init_db
    from models.features import build_training_frame

    init_db()
    db = SessionLocal()
    try:
        df = build_training_frame(db)
    finally:
        db.close()

    log.info("Loaded %d runner-rows from DB", len(df))
    return df


# ---------------------------------------------------------------------------
# Train/val/test split (chronological)
# ---------------------------------------------------------------------------

def time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split by event_id groups so all runners in a race stay together.
    Train: first 70%, Val: next 15%, Test: final 15%.
    """
    events = df["event_id"].unique()
    n = len(events)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    train_ev = set(events[:train_end])
    val_ev = set(events[train_end:val_end])
    test_ev = set(events[val_end:])

    train = df[df["event_id"].isin(train_ev)].copy()
    val = df[df["event_id"].isin(val_ev)].copy()
    test = df[df["event_id"].isin(test_ev)].copy()

    log.info(
        "Split: train=%d rows (%d races), val=%d rows (%d races), test=%d rows (%d races)",
        len(train), len(train_ev), len(val), len(val_ev), len(test), len(test_ev),
    )
    return train, val, test


# ---------------------------------------------------------------------------
# Feature prep
# ---------------------------------------------------------------------------

def get_feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in DROP_COLS]


def prep_xy(df: pd.DataFrame, feature_cols: list[str]) -> tuple:
    X = df[feature_cols].copy()
    y = df["won"].values
    return X, y


# ---------------------------------------------------------------------------
# Optuna hyperparameter search
# ---------------------------------------------------------------------------

def tune(X_train, y_train, X_val, y_val, n_trials: int = 50) -> dict:
    import lightgbm as lgb
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "n_estimators": trial.suggest_int("n_estimators", 300, 1500),
            "num_leaves": trial.suggest_int("num_leaves", 16, 256),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
            "bagging_freq": trial.suggest_int("bagging_freq", 1, 7),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
            "lambda_l1": trial.suggest_float("lambda_l1", 1e-4, 10.0, log=True),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-4, 10.0, log=True),
            "is_unbalance": True,
        }
        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
        )
        preds = model.predict_proba(X_val)[:, 1]
        return log_loss(y_val, preds)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    log.info("Best trial log_loss=%.4f", study.best_value)
    return study.best_params


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_model(X_train, y_train, X_val, y_val, params: dict):
    import lightgbm as lgb

    base_params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "is_unbalance": True,
    }
    base_params.update(params)

    model = lgb.LGBMClassifier(**base_params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(100)],
    )
    return model


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def calibrate(model, X_val, y_val) -> IsotonicRegression:
    """
    Fit isotonic regression calibrator on validation set raw probabilities.
    Returns calibrator that maps raw LGBM prob → calibrated prob.
    """
    raw_probs = model.predict_proba(X_val)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_probs, y_val)
    return calibrator


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(model, calibrator, X_test, y_test, df_test: pd.DataFrame, edge_threshold: float):
    raw_probs = model.predict_proba(X_test)[:, 1]
    cal_probs = calibrator.predict(raw_probs)

    print("\n=== Model Evaluation (test set) ===")
    print(f"  Log-loss (raw):       {log_loss(y_test, raw_probs):.4f}")
    print(f"  Log-loss (calibrated):{log_loss(y_test, cal_probs):.4f}")
    print(f"  Brier score:          {brier_score_loss(y_test, cal_probs):.4f}")
    print(f"  ROC-AUC:              {roc_auc_score(y_test, cal_probs):.4f}")

    # Calibration check: mean predicted prob vs actual win rate per decile
    frac_pos, mean_pred = calibration_curve(y_test, cal_probs, n_bins=10)
    print("\n  Calibration (predicted → actual):")
    for p, a in zip(mean_pred, frac_pos):
        print(f"    {p:.2f} → {a:.2f}")

    # Value-bet backtest
    df_test = df_test.copy()
    df_test["cal_prob"] = cal_probs
    df_test["tab_implied"] = df_test.get("tab_implied_prob", pd.Series([float("nan")] * len(df_test)))
    df_test["edge"] = df_test["cal_prob"] - df_test["tab_implied"]

    value_bets = df_test[df_test["edge"] > edge_threshold]
    if len(value_bets) == 0:
        print(f"\n  No value bets found with edge > {edge_threshold:.0%}")
        return

    # Flat $1 stake: return tab_odds if won, else -$1
    value_bets = value_bets.copy()
    value_bets["pl"] = value_bets.apply(
        lambda r: (r["tab_fixed_win"] - 1) if r["won"] == 1 else -1.0,
        axis=1,
    )
    total_bets = len(value_bets)
    total_pl = value_bets["pl"].sum()
    roi = total_pl / total_bets

    print(f"\n  Value-bet backtest (edge > {edge_threshold:.0%}):")
    print(f"    Bets:          {total_bets}")
    print(f"    Win rate:      {value_bets['won'].mean():.1%}")
    print(f"    Total P&L:     ${total_pl:+.2f} (flat $1 stake)")
    print(f"    ROI:           {roi:+.1%}")
    print(f"    Avg edge:      {value_bets['edge'].mean():.1%}")


# ---------------------------------------------------------------------------
# SHAP feature importance
# ---------------------------------------------------------------------------

def print_feature_importance(model, feature_cols: list[str], top_n: int = 20):
    import lightgbm as lgb

    importance = model.booster_.feature_importance(importance_type="gain")
    fi = sorted(zip(feature_cols, importance), key=lambda x: -x[1])
    print(f"\n=== Top {top_n} features by gain ===")
    for name, gain in fi[:top_n]:
        print(f"  {name:<45} {gain:.1f}")


# ---------------------------------------------------------------------------
# Save artifacts
# ---------------------------------------------------------------------------

def save_artifacts(model, calibrator, feature_cols: list[str], best_params: dict):
    with open(ARTIFACTS_DIR / "model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open(ARTIFACTS_DIR / "calibrator.pkl", "wb") as f:
        pickle.dump(calibrator, f)
    with open(ARTIFACTS_DIR / "feature_cols.json", "w") as f:
        json.dump(feature_cols, f, indent=2)
    with open(ARTIFACTS_DIR / "best_params.json", "w") as f:
        json.dump(best_params, f, indent=2)
    log.info("Artifacts saved to %s", ARTIFACTS_DIR)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--no-tune", action="store_true", help="Skip Optuna tuning, use defaults")
    parser.add_argument("--trials", type=int, default=50, help="Optuna trials")
    parser.add_argument("--edge-threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    args = parser.parse_args()

    df = load_data()
    if len(df) < 500:
        raise ValueError(f"Only {len(df)} rows — need more historical data before training.")

    train_df, val_df, test_df = time_split(df)
    feature_cols = get_feature_cols(df)

    X_train, y_train = prep_xy(train_df, feature_cols)
    X_val, y_val = prep_xy(val_df, feature_cols)
    X_test, y_test = prep_xy(test_df, feature_cols)

    if args.no_tune:
        best_params = {
            "n_estimators": 800,
            "num_leaves": 64,
            "learning_rate": 0.02,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "min_child_samples": 30,
            "lambda_l1": 0.1,
            "lambda_l2": 0.1,
        }
        log.info("Using default params (--no-tune)")
    else:
        log.info("Running Optuna search (%d trials)...", args.trials)
        best_params = tune(X_train, y_train, X_val, y_val, n_trials=args.trials)

    log.info("Training final model...")
    model = train_model(X_train, y_train, X_val, y_val, best_params)

    log.info("Calibrating probabilities...")
    calibrator = calibrate(model, X_val, y_val)

    evaluate(model, calibrator, X_test, y_test, test_df, args.edge_threshold)
    print_feature_importance(model, feature_cols)
    save_artifacts(model, calibrator, feature_cols, best_params)
    print("\nDone. Run `uvicorn api.main:app` to start the server.")


if __name__ == "__main__":
    main()
