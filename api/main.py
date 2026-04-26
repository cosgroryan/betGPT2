"""
FastAPI backend for betGPT2.

Endpoints:
  GET  /api/meetings/today          → schedule with race statuses
  GET  /api/race/{event_id}         → runners + model predictions
  GET  /api/race/{event_id}/results → post-race results + model verdict
  GET  /api/value/today             → all races ranked by best value edge
  GET  /api/tracker/history         → value bet history
  POST /api/tracker/session/start   → open a tracker session
  POST /api/tracker/session/end     → close a tracker session
  POST /api/model/reload            → hot-swap model after retraining
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict
from datetime import date, datetime
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from api.collector import fetch_meetings, fetch_race_detail, fetch_and_store_results, snapshot_race
from api.db import Race, Result, Runner, ValueBet, get_db, init_db
from api.predictor import RunnerPrediction, predict_race, reload_artifacts

log = logging.getLogger(__name__)

app = FastAPI(title="betGPT2 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-process cache: event_id → (payload, predictions, fetched_at)
# 90-second TTL to avoid hammering TAB API
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[dict, list, float]] = {}
CACHE_TTL = 90.0


def _get_cached(event_id: str) -> tuple[dict, list] | None:
    entry = _cache.get(event_id)
    if entry and (time.time() - entry[2]) < CACHE_TTL:
        return entry[0], entry[1]
    return None


def _set_cache(event_id: str, payload: dict, predictions: list):
    _cache[event_id] = (payload, predictions, time.time())


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    init_db()
    log.info("Database initialised")


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

@app.get("/api/meetings/today")
def get_meetings_today():
    """Today's meeting schedule for AU + NZ thoroughbreds."""
    try:
        meetings = fetch_meetings()
    except Exception as e:
        raise HTTPException(502, f"TAB API error: {e}")

    out = []
    for m in meetings:
        races = []
        for r in m.get("races", []):
            races.append({
                "event_id": r.get("id"),
                "race_number": r.get("race_number"),
                "name": r.get("name"),
                "distance": r.get("distance"),
                "status": r.get("status"),
                "start_time": r.get("start_time"),
                "track_condition": r.get("track_condition"),
                "weather": r.get("weather"),
                "country": r.get("country"),
            })
        out.append({
            "meeting_id": m.get("meeting"),
            "name": m.get("name"),
            "country": m.get("country", ""),
            "state": m.get("state", ""),
            "track_condition": m.get("track_condition", ""),
            "races": races,
        })

    return {"meetings": out, "date": date.today().isoformat()}


# ---------------------------------------------------------------------------
# Race detail + predictions
# ---------------------------------------------------------------------------

@app.get("/api/race/{event_id}")
def get_race(event_id: str, db: Session = Depends(get_db)):
    """
    Full race detail with ML predictions per runner.
    Cached for 90 seconds; also persists runner snapshot to DB.
    """
    cached = _get_cached(event_id)
    if cached:
        payload, predictions = cached
        return _race_response(payload, predictions)

    try:
        payload = snapshot_race(event_id)
    except Exception as e:
        raise HTTPException(502, f"TAB API error: {e}")

    try:
        predictions = predict_race(payload)
    except FileNotFoundError:
        predictions = []
        log.warning("No model trained yet — serving raw data only")

    _set_cache(event_id, payload, predictions)

    # Persist any flagged value bets
    _persist_value_bets(db, event_id, payload, predictions)

    return _race_response(payload, predictions)


def _race_response(payload: dict, predictions: list[RunnerPrediction]) -> dict:
    race = payload.get("race", {})
    pred_map = {p.entrant_id: p for p in predictions}

    runners_out = []
    for r in payload.get("runners", []):
        eid = r.get("entrant_id")
        pred = pred_map.get(eid)
        odds = r.get("odds", {})
        flucs = r.get("flucs_with_timestamp", {})
        last_six = [f.get("fluc") for f in (flucs.get("last_six") or [])[-6:]]

        runner_data = {
            "entrant_id": eid,
            "name": r.get("name"),
            "runner_number": r.get("runner_number"),
            "barrier": r.get("barrier"),
            "jockey": r.get("jockey"),
            "trainer": r.get("trainer_name"),
            "weight": r.get("weight"),
            "age": r.get("age"),
            "sex": r.get("sex"),
            "is_scratched": r.get("is_scratched"),
            "is_late_scratched": r.get("is_late_scratched"),
            "is_favourite": r.get("favourite"),
            "is_mover": r.get("mover"),
            "silk_url": r.get("silk_url_64x64"),
            "form_comment_short": r.get("form_comment_short"),
            "last_twenty_starts": r.get("last_twenty_starts"),
            "odds": {
                "fixed_win": odds.get("fixed_win"),
                "fixed_place": odds.get("fixed_place"),
                "pool_win": odds.get("pool_win"),
                "pool_place": odds.get("pool_place"),
            },
            "flucs_sparkline": last_six,
            "speedmap": r.get("speedmap"),
            "form_indicators": r.get("form_indicators", []),
            # ML predictions (None if no model yet)
            "ml": asdict(pred) if pred else None,
        }
        runners_out.append(runner_data)

    return {
        "race": {
            "event_id": race.get("event_id"),
            "meeting_name": race.get("meeting_name"),
            "display_name": race.get("display_meeting_name"),
            "race_number": race.get("race_number"),
            "distance": race.get("distance"),
            "class": race.get("class"),
            "track_condition": race.get("track_condition"),
            "track_surface": race.get("track_surface"),
            "track_direction": race.get("track_direction"),
            "rail_position": race.get("rail_position"),
            "weather": race.get("weather"),
            "start_time": race.get("advertised_start_string"),
            "status": race.get("status"),
            "field_size": race.get("field_size"),
            "prize_money": race.get("prize_monies"),
            "group": race.get("group"),
        },
        "runners": runners_out,
        "money_tracker": payload.get("money_tracker"),
        "big_bets": payload.get("big_bets", []),
        "biggest_bet": payload.get("biggest_bet"),
        "tote_pools": payload.get("tote_pools", []),
        "model_available": len(predictions) > 0,
    }


def _persist_value_bets(
    db: Session, event_id: str, payload: dict, predictions: list[RunnerPrediction]
):
    race = payload.get("race", {})
    label = f"R{race.get('race_number')} {race.get('meeting_name', '')}"
    for pred in predictions:
        if not pred.is_value_bet:
            continue
        existing = (
            db.query(ValueBet)
            .filter(ValueBet.event_id == event_id, ValueBet.entrant_id == pred.entrant_id)
            .first()
        )
        if existing:
            continue
        db.add(
            ValueBet(
                event_id=event_id,
                entrant_id=pred.entrant_id,
                runner_name=pred.name,
                race_label=label,
                model_prob=pred.model_prob,
                model_odds=pred.model_odds,
                tab_odds=pred.tab_fixed_win,
                tab_implied_prob=pred.tab_implied_prob,
                value_edge=pred.value_edge,
            )
        )
    db.commit()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@app.get("/api/race/{event_id}/results")
def get_race_results(event_id: str, db: Session = Depends(get_db)):
    """
    Post-race results with model verdict.
    Fetches fresh results from TAB if not yet in DB.
    """
    results = db.query(Result).filter(Result.event_id == event_id).all()
    if not results:
        try:
            fetch_and_store_results(event_id)
            results = db.query(Result).filter(Result.event_id == event_id).all()
        except Exception as e:
            raise HTTPException(502, f"TAB API error: {e}")

    if not results:
        raise HTTPException(404, "Results not yet available")

    # Attach model prediction to each result row
    pred_map: dict[str, RunnerPrediction] = {}
    cached = _get_cached(event_id)
    if cached:
        _, preds = cached
        pred_map = {p.entrant_id: p for p in preds}

    # Settle value bets
    _settle_value_bets(db, event_id, results)

    return {
        "event_id": event_id,
        "results": [
            {
                "position": r.position,
                "name": r.name,
                "entrant_id": r.entrant_id,
                "runner_number": r.runner_number,
                "barrier": r.barrier,
                "margin_lengths": r.margin_lengths,
                "time_ran": r.time_ran,
                "winning_time": r.winning_time,
                "ml": asdict(pred_map[r.entrant_id]) if r.entrant_id in pred_map else None,
            }
            for r in sorted(results, key=lambda r: r.position or 99)
        ],
    }


def _settle_value_bets(db: Session, event_id: str, results: list[Result]):
    result_map = {r.entrant_id: r for r in results}
    value_bets = db.query(ValueBet).filter(
        ValueBet.event_id == event_id, ValueBet.won == None
    ).all()

    for vb in value_bets:
        r = result_map.get(vb.entrant_id)
        if not r:
            continue
        vb.result_position = r.position
        vb.won = r.position == 1
        vb.placed = r.position is not None and r.position <= 3
        if vb.won and vb.tab_odds:
            vb.pl_flat_stake = vb.tab_odds - 1
        else:
            vb.pl_flat_stake = -1.0

    db.commit()


# ---------------------------------------------------------------------------
# Value dashboard (today's best opportunities across all races)
# ---------------------------------------------------------------------------

@app.get("/api/value/today")
def get_value_today():
    """
    All today's meetings, all races, ranked by best value edge.
    Only returns runners with is_value_bet=True.
    """
    try:
        meetings = fetch_meetings()
    except Exception as e:
        raise HTTPException(502, f"TAB API error: {e}")

    opportunities = []
    for meeting in meetings:
        for race in meeting.get("races", []):
            eid = race.get("id")
            if not eid or race.get("status") in ("Resulted", "Paying", "Abandoned"):
                continue
            cached = _get_cached(eid)
            if not cached:
                continue
            _, predictions = cached
            for pred in predictions:
                if pred.is_value_bet:
                    opportunities.append({
                        "event_id": eid,
                        "meeting": meeting.get("name"),
                        "race_number": race.get("race_number"),
                        "start_time": race.get("start_time"),
                        "status": race.get("status"),
                        "runner": pred.name,
                        "entrant_id": pred.entrant_id,
                        "barrier": pred.barrier,
                        "jockey": pred.jockey,
                        "ml_prob": pred.model_prob,
                        "ml_odds": pred.model_odds,
                        "tab_odds": pred.tab_fixed_win,
                        "tab_implied": pred.tab_implied_prob,
                        "value_edge": pred.value_edge,
                        "fluc_drift": pred.fluc_drift,
                        "is_mover": pred.is_market_mover,
                    })

    opportunities.sort(key=lambda x: x["value_edge"], reverse=True)
    return {"opportunities": opportunities, "count": len(opportunities)}


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

@app.get("/api/tracker/history")
def get_tracker_history(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    bets = (
        db.query(ValueBet)
        .order_by(ValueBet.flagged_at.desc())
        .limit(limit)
        .all()
    )
    rows = []
    for b in bets:
        rows.append({
            "id": b.id,
            "event_id": b.event_id,
            "race_label": b.race_label,
            "runner": b.runner_name,
            "model_odds": b.model_odds,
            "tab_odds": b.tab_odds,
            "value_edge": b.value_edge,
            "flagged_at": b.flagged_at.isoformat() if b.flagged_at else None,
            "result_position": b.result_position,
            "won": b.won,
            "placed": b.placed,
            "pl": b.pl_flat_stake,
        })

    total_pl = sum(r["pl"] for r in rows if r["pl"] is not None)
    settled = [r for r in rows if r["won"] is not None]
    win_rate = sum(1 for r in settled if r["won"]) / len(settled) if settled else None

    return {
        "bets": rows,
        "summary": {
            "total": len(rows),
            "settled": len(settled),
            "total_pl": round(total_pl, 2),
            "win_rate": round(win_rate * 100, 1) if win_rate is not None else None,
        },
    }


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------

@app.post("/api/model/reload")
def reload_model():
    """Hot-swap model after retraining without restarting the server."""
    reload_artifacts()
    _cache.clear()
    return {"status": "ok", "message": "Model reloaded and cache cleared"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
