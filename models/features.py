"""
Feature engineering: convert raw runner JSON + race context into a flat dict
suitable for LightGBM training and inference.

All features are derived purely from pre-race information — no result leakage.
TAB's own predictor.win/place fields are intentionally excluded so our model
is independent of theirs.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRACK_CONDITION_ORDER = {
    "firm": 1, "firm1": 1, "firm2": 2,
    "good": 3, "good3": 3, "good4": 4,
    "soft": 5, "soft5": 5, "soft6": 6, "soft7": 7,
    "heavy": 8, "heavy8": 8, "heavy9": 9, "heavy10": 10,
    "slow": 6,
    "fast": 2,
    "all weather": 3,
    "synthetic": 3,
}

SPEEDMAP_LABEL_ENC = {"lead": 4, "on-speed": 3, "on speed": 3, "midfield": 2, "back": 1}

SEX_ENC = {"g": 0, "gelding": 0, "m": 1, "mare": 1, "h": 2, "horse": 2, "c": 2, "colt": 2, "f": 1, "filly": 1}

CAMPAIGN_PREP_COLS = ["first_up", "second_up", "third_up", "fourth_up"]

GOING_MAP = {
    # Maps today's track_condition string to which runner stat block to use
    "firm": "firm", "firm1": "firm", "firm2": "firm",
    "good": "good", "good3": "good", "good4": "good",
    "soft": "soft", "soft5": "soft", "soft6": "soft", "soft7": "soft",
    "slow": "slow",
    "heavy": "heavy", "heavy8": "heavy", "heavy9": "heavy", "heavy10": "heavy",
    "fast": "fast",
    "all weather": "all_weather",
    "synthetic": "synthetic",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _parse_weight(w) -> Optional[float]:
    if isinstance(w, dict):
        return _safe_float(w.get("total"))
    if isinstance(w, str):
        m = re.search(r"[\d.]+", w)
        return float(m.group()) if m else None
    return _safe_float(w)


def _win_rate(stat: dict) -> float:
    starts = _safe_int(stat.get("number_of_starts")) or 0
    wins = _safe_int(stat.get("number_of_wins")) or 0
    return wins / starts if starts > 0 else float("nan")


def _place_rate(stat: dict) -> float:
    starts = _safe_int(stat.get("number_of_starts")) or 0
    placings = (
        (_safe_int(stat.get("number_of_wins")) or 0)
        + (_safe_int(stat.get("number_of_placings")) or 0)
        + (_safe_int(stat.get("number_of_seconds")) or 0)
        + (_safe_int(stat.get("number_of_thirds")) or 0)
    )
    return placings / starts if starts > 0 else float("nan")


def _starts(stat: dict) -> int:
    return _safe_int(stat.get("number_of_starts")) or 0


def _stat_block(runner: dict, key: str) -> dict:
    return runner.get(key) or {}


# ---------------------------------------------------------------------------
# Form features from last_starts sequence
# ---------------------------------------------------------------------------

def _last_starts_features(last_starts: list[dict], today_distance: int, today_condition: str) -> dict:
    feats: dict[str, Any] = {}
    valid = [s for s in last_starts if s.get("finish") not in (None, "", "0")]
    n = len(valid)

    if n == 0:
        return {
            "last1_finish_norm": float("nan"),
            "avg_finish_norm_l3": float("nan"),
            "weighted_finish_l5": float("nan"),
            "avg_run_rating_l3": float("nan"),
            "best_run_rating_l5": float("nan"),
            "avg_margin_l3": float("nan"),
            "days_since_last": float("nan"),
            "last_condition_enc": float("nan"),
            "was_favourite_l1": float("nan"),
            "last_distance_diff": float("nan"),
            "prize_money_step": float("nan"),
            "has_gear_change": 0,
        }

    def finish_norm(s: dict) -> float:
        finish = _safe_float(s.get("finish"))
        runners = _safe_float(s.get("number_of_runners")) or 1
        return finish / runners if finish else float("nan")

    l1 = valid[0]
    feats["last1_finish_norm"] = finish_norm(l1)
    feats["avg_finish_norm_l3"] = float(np.nanmean([finish_norm(s) for s in valid[:3]]))

    # Exponential decay weighted finish (most recent = weight 1.0)
    decay = 0.6
    w_finishes = [finish_norm(valid[i]) * (decay ** i) for i in range(min(5, n))]
    feats["weighted_finish_l5"] = float(np.nanmean(w_finishes))

    run_ratings = [_safe_float(s.get("run_rating")) for s in valid[:3]]
    run_ratings = [r for r in run_ratings if r is not None]
    feats["avg_run_rating_l3"] = float(np.mean(run_ratings)) if run_ratings else float("nan")

    run_ratings5 = [_safe_float(s.get("run_rating")) for s in valid[:5]]
    run_ratings5 = [r for r in run_ratings5 if r is not None]
    feats["best_run_rating_l5"] = float(np.max(run_ratings5)) if run_ratings5 else float("nan")

    margins = [_safe_float(s.get("margin")) for s in valid[:3]]
    margins = [m for m in margins if m is not None]
    feats["avg_margin_l3"] = float(np.mean(margins)) if margins else float("nan")

    feats["days_since_last"] = _safe_float(l1.get("days_since")) or float("nan")
    feats["last_condition_enc"] = TRACK_CONDITION_ORDER.get(
        str(l1.get("track_condition", "")).lower(), float("nan")
    )
    feats["was_favourite_l1"] = 1.0 if l1.get("win_favouritism") == "1" else 0.0

    last_dist = _safe_float(l1.get("distance"))
    feats["last_distance_diff"] = abs(today_distance - last_dist) if last_dist else float("nan")

    last_prize = _safe_float(re.sub(r"[^\d.]", "", str(l1.get("prize_money", "0"))) or "0")
    feats["prize_money_step"] = float("nan")  # can't compute without today's prize here

    # Gear change: did the horse race with gear changes last start?
    feats["has_gear_change"] = 1 if l1.get("gear_changes") else 0

    return feats


# ---------------------------------------------------------------------------
# Main feature extractor
# ---------------------------------------------------------------------------

def extract_features(
    runner: dict,
    race: dict,
    field_runners: list[dict],
    money_tracker: dict | None = None,
) -> dict[str, Any]:
    """
    Build a flat feature dict for one runner in one race.

    Parameters
    ----------
    runner:         full runner dict from raceinfo.json schema
    race:           race-level dict (race.race from raceinfo.json)
    field_runners:  all runners in the field (for relative features)
    money_tracker:  money_tracker dict from raceinfo (optional)
    """
    feats: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Race context
    # ------------------------------------------------------------------
    distance = _safe_int(race.get("distance")) or 0
    condition_raw = str(race.get("track_condition", "")).lower()
    feats["race_distance"] = distance
    feats["track_condition_enc"] = TRACK_CONDITION_ORDER.get(condition_raw, 3)
    surface = str(race.get("track_surface", "")).lower()
    feats["surface_turf"] = 1 if "turf" in surface or "grass" in surface else 0
    feats["surface_synthetic"] = 1 if "synthetic" in surface or "all weather" in surface else 0
    feats["track_direction_left"] = 1 if str(race.get("track_direction", "")).lower() == "left" else 0
    feats["field_size"] = _safe_int(race.get("field_size") or race.get("entrant_count")) or len(field_runners)

    prize_raw = race.get("prize_monies", {})
    if isinstance(prize_raw, dict):
        first_prize = next(iter(prize_raw.values()), 0)
    else:
        first_prize = 0
    feats["prize_money_log"] = math.log1p(float(first_prize or 0))

    feats["start_type_mobile"] = 1 if str(race.get("start_type", "")).lower() == "mobile" else 0

    rail = str(race.get("rail_position", ""))
    rail_m = re.search(r"[-+]?\d+", rail)
    feats["rail_position_m"] = float(rail_m.group()) if rail_m else 0.0

    # ------------------------------------------------------------------
    # Runner attributes
    # ------------------------------------------------------------------
    barrier = _safe_int(runner.get("barrier")) or 0
    field_size = feats["field_size"] or 1
    feats["barrier"] = barrier
    feats["barrier_pct"] = barrier / field_size

    weight = _parse_weight(runner.get("weight"))
    feats["weight_total"] = weight if weight is not None else float("nan")

    # Field-mean weight delta
    weights = [_parse_weight(r.get("weight")) for r in field_runners]
    weights = [w for w in weights if w is not None]
    mean_weight = float(np.mean(weights)) if weights else (weight or 58.0)
    feats["weight_delta"] = (weight - mean_weight) if weight is not None else float("nan")

    feats["age"] = _safe_float(runner.get("age")) or float("nan")
    feats["sex_enc"] = SEX_ENC.get(str(runner.get("sex", "")).lower(), 2)
    feats["handicap_rating"] = _safe_float(runner.get("handicap_rating")) or float("nan")
    feats["spr"] = _safe_float(runner.get("spr")) or float("nan")
    feats["is_first_start"] = 1 if runner.get("first_start_indicator") else 0
    feats["is_apprentice"] = 1 if runner.get("apprentice_indicator") else 0

    # ------------------------------------------------------------------
    # Form statistics — win/place rates
    # ------------------------------------------------------------------
    going_key = GOING_MAP.get(condition_raw, "good")

    stat_map = {
        "overall": "overall",
        "distance": "distance",
        "track": "track",
        "track_distance": "track_distance",
        "going": going_key,
        "turf": "turf",
        "synthetic": "synthetic",
        "left_handed": "left_handed",
        "right_handed": "right_handed",
        "last12m": "last_12_months",
        "first_up": "first_up",
        "second_up": "second_up",
        "third_up": "third_up",
        "fourth_up": "fourth_up",
        "fresh_30": "fresh_30",
        "fresh_90": "fresh_90",
    }

    for feat_prefix, json_key in stat_map.items():
        block = _stat_block(runner, json_key)
        feats[f"{feat_prefix}_win_rate"] = _win_rate(block)
        feats[f"{feat_prefix}_place_rate"] = _place_rate(block)
        feats[f"{feat_prefix}_starts"] = _starts(block)

    # Which prep run is this (1st/2nd/3rd/4th+)
    for i, key in enumerate(CAMPAIGN_PREP_COLS, start=1):
        if _starts(_stat_block(runner, key)) > 0:
            feats["campaign_prep"] = i
            break
    else:
        feats["campaign_prep"] = 4

    # ------------------------------------------------------------------
    # Jockey & trainer
    # ------------------------------------------------------------------
    j_perf = runner.get("jockey_past_performances", {})
    j_last50 = j_perf.get("last_50_starts", {})
    j_trainer = j_perf.get("trainer", {})
    feats["jockey_win_rate_l50"] = _win_rate(j_last50)
    feats["jockey_place_rate_l50"] = _place_rate(j_last50)
    feats["jockey_trainer_win_rate"] = _win_rate(j_trainer)
    feats["jockey_trainer_place_rate"] = _place_rate(j_trainer)

    # ------------------------------------------------------------------
    # Speedmap
    # ------------------------------------------------------------------
    sm = runner.get("speedmap") or {}
    label = str(sm.get("label", "")).lower()
    feats["speedmap_label_enc"] = SPEEDMAP_LABEL_ENC.get(label, 2)
    feats["barrier_speed"] = _safe_float(sm.get("barrier_speed")) or float("nan")
    feats["finish_speed"] = _safe_float(sm.get("finish_speed")) or float("nan")
    feats["settling_lengths"] = _safe_float(sm.get("settling_lengths")) or float("nan")

    # Sole leader in field?
    leaders = [r for r in field_runners if str((r.get("speedmap") or {}).get("label", "")).lower() == "lead"]
    feats["is_sole_leader"] = 1 if len(leaders) == 1 and label == "lead" else 0

    # ------------------------------------------------------------------
    # Market signals
    # ------------------------------------------------------------------
    odds = runner.get("odds", {})
    fixed_win = _safe_float(odds.get("fixed_win"))
    feats["tab_fixed_win"] = fixed_win if fixed_win else float("nan")

    # Margin-removed implied probability across the field
    raw_probs = []
    for r in field_runners:
        fw = _safe_float((r.get("odds") or {}).get("fixed_win"))
        raw_probs.append((1 / fw) if fw and fw > 1 else 0.0)
    total_prob = sum(raw_probs) or 1.0
    my_raw = (1 / fixed_win) if fixed_win and fixed_win > 1 else 0.0
    feats["tab_implied_prob"] = my_raw / total_prob

    flucs = runner.get("flucs_with_timestamp", {})
    open_fluc = _safe_float((flucs.get("open") or {}).get("fluc"))
    nine_am = _safe_float((flucs.get("nine_am") or {}).get("fluc"))
    feats["fluc_open"] = open_fluc if open_fluc else float("nan")
    feats["fluc_9am"] = nine_am if nine_am else float("nan")
    feats["fluc_drift"] = (
        (fixed_win - open_fluc) / open_fluc
        if fixed_win and open_fluc and open_fluc > 0
        else float("nan")
    )
    feats["is_market_mover"] = 1 if runner.get("mover") else 0
    feats["is_favourite"] = 1 if runner.get("favourite") else 0

    mt_entry: dict = {}
    if money_tracker:
        for e in money_tracker.get("entrants", []):
            if e.get("entrant_id") == runner.get("entrant_id"):
                mt_entry = e
                break
    feats["hold_pct"] = _safe_float(mt_entry.get("hold_percentage")) or float("nan")
    feats["bet_pct"] = _safe_float(mt_entry.get("bet_percentage")) or float("nan")

    # ------------------------------------------------------------------
    # Last starts sequence
    # ------------------------------------------------------------------
    last_starts = runner.get("last_starts") or []
    ls_feats = _last_starts_features(last_starts, distance, condition_raw)
    feats.update(ls_feats)

    return feats


# ---------------------------------------------------------------------------
# Build training dataset from DB
# ---------------------------------------------------------------------------

def build_training_frame(db_session) -> "pd.DataFrame":
    """
    Query all completed races from DB, join runners + results,
    compute features for each runner, return a DataFrame.
    Rows with is_scratched=True are excluded.
    """
    import pandas as pd
    from api.db import Race, Result, Runner

    # Fetch all resulted races
    races = (
        db_session.query(Race)
        .filter(Race.status.in_(["Paying", "Resulted", "Interim"]))
        .all()
    )

    rows = []
    for race in races:
        runners = (
            db_session.query(Runner)
            .filter(Runner.event_id == race.event_id, Runner.is_scratched == False)
            .all()
        )
        results = (
            db_session.query(Result)
            .filter(Result.event_id == race.event_id)
            .all()
        )
        result_map = {r.entrant_id: r for r in results}

        if not runners or not results:
            continue

        # Reconstruct runner dicts from raw_json
        runner_dicts = []
        for runner in runners:
            if runner.raw_json:
                import json
                runner_dicts.append(json.loads(runner.raw_json))

        if not runner_dicts:
            continue

        race_dict = {
            "distance": race.distance,
            "track_condition": race.track_condition,
            "track_surface": race.track_surface,
            "track_direction": race.track_direction,
            "field_size": race.field_size,
            "prize_monies": {"first": race.prize_money_first or 0},
            "start_type": race.start_type,
            "rail_position": race.rail_position or "",
        }

        for runner_obj, runner_dict in zip(runners, runner_dicts):
            feats = extract_features(runner_dict, race_dict, runner_dicts)

            result = result_map.get(runner_obj.entrant_id)
            if result is None:
                continue

            feats["event_id"] = race.event_id
            feats["entrant_id"] = runner_obj.entrant_id
            feats["won"] = 1 if result.position == 1 else 0
            feats["placed"] = 1 if result.position <= 3 else 0
            feats["finish_position"] = result.position

            rows.append(feats)

    return pd.DataFrame(rows)
