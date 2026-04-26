"""
Data collection from TAB Affiliates API.

Two modes:
  - backfill(): historical races via /extras endpoint (pagination)
  - snapshot_race(event_id): pre-race runner snapshot for live model input
  - fetch_results(event_id): post-race results

Filter: category=T (Thoroughbred), country in [AUS, NZL]
"""

import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from api.db import Meeting, Race, Result, Runner, SessionLocal, init_db

load_dotenv()
log = logging.getLogger(__name__)

AFF_BASE = "https://api.tab.co.nz/affiliates/v1/racing"
HEADERS = {
    "From": os.getenv("TAB_FROM", "r.cosgrove@hotmail.com"),
    "X-Partner": os.getenv("TAB_PARTNER", "Personal use"),
    "X-Partner-ID": os.getenv("TAB_PARTNER_ID", "Personal use"),
    "Accept": "application/json",
    "User-Agent": "RyanCosgrove/1.0",
}
COUNTRIES = ["AUS", "NZL"]
CATEGORY = "T"


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f"{AFF_BASE}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            if r.status_code == 429:
                wait = 2 ** attempt * 5
                log.warning("Rate limited, waiting %ss", wait)
                time.sleep(wait)
            elif r.status_code >= 500:
                time.sleep(2 ** attempt)
            else:
                raise
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to GET {url} after {retries} attempts")


# ---------------------------------------------------------------------------
# Meetings list (live / today)
# ---------------------------------------------------------------------------

def fetch_meetings(target_date: Optional[date] = None) -> list[dict]:
    """Return all T-category meetings for a given date (default: today)."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()

    meetings = []
    for country in COUNTRIES:
        data = _get("", params={"category": CATEGORY, "country": country, "date": date_str})
        meetings.extend(data.get("meetings", []))

    return meetings


# ---------------------------------------------------------------------------
# Full race detail (runners, odds, form, speedmap)
# ---------------------------------------------------------------------------

def fetch_race_detail(event_id: str) -> dict:
    """Full race payload from /racing/{event_id} (the raceinfo schema)."""
    return _get(f"/{event_id}")


# ---------------------------------------------------------------------------
# Historical results via /extras
# ---------------------------------------------------------------------------

def fetch_extras_page(
    country: str,
    date_from: str,
    date_to: str,
    page_token: Optional[str] = None,
) -> dict:
    params = {
        "category": CATEGORY,
        "country": country,
        "date_from": date_from,
        "date_to": date_to,
    }
    if page_token:
        params["page_token"] = page_token
    return _get("/extras", params=params)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _upsert_meeting(db: Session, meeting: dict, country: str):
    mid = meeting.get("meeting") or meeting.get("meeting_id")
    if not mid:
        return
    obj = db.get(Meeting, mid)
    if obj is None:
        obj = Meeting(meeting_id=mid)
        db.add(obj)
    obj.date = str(meeting.get("date", meeting.get("meeting_date", "")))[:10]
    obj.name = meeting.get("name", "")
    obj.country = country
    obj.state = meeting.get("state", "")
    obj.track_condition = meeting.get("track_condition", "")
    obj.category = CATEGORY


def _upsert_race(db: Session, race: dict, meeting_id: str):
    eid = race.get("id") or race.get("event_id")
    if not eid:
        return
    obj = db.get(Race, eid)
    if obj is None:
        obj = Race(event_id=eid)
        db.add(obj)
    obj.meeting_id = meeting_id
    obj.race_number = race.get("race_number", 0)
    obj.name = race.get("name", "")
    obj.distance = race.get("distance", 0)
    obj.status = race.get("status", "")
    obj.start_time = str(race.get("start_time", race.get("advertised_start_string", "")))
    obj.track_condition = race.get("track_condition", "")
    obj.weather = race.get("weather", "")
    obj.country = race.get("country", "")


def _upsert_result(db: Session, event_id: str, result: dict):
    eid_result = result.get("entrant_id")
    existing = (
        db.query(Result)
        .filter(Result.event_id == event_id, Result.entrant_id == eid_result)
        .first()
    )
    if existing:
        return
    db.add(
        Result(
            event_id=event_id,
            entrant_id=eid_result,
            name=result.get("entrant_name", result.get("name", "")),
            position=result.get("position", 0),
            runner_number=result.get("runner_number", 0),
            barrier=result.get("barrier", 0),
            margin_lengths=_safe_float(result.get("margin_length", 0)),
            time_ran=_safe_float(result.get("time_ran", 0)),
            winning_time=_safe_float(result.get("winning_time", 0)),
        )
    )


def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _parse_weight(w) -> Optional[float]:
    """Parse weight string like '58.5' or dict with 'total'."""
    if isinstance(w, dict):
        return _safe_float(w.get("total"))
    return _safe_float(w)


def _snapshot_runner(db: Session, event_id: str, runner: dict, money_tracker: dict):
    eid = runner.get("entrant_id")
    existing = (
        db.query(Runner)
        .filter(Runner.event_id == event_id, Runner.entrant_id == eid)
        .first()
    )

    money_entry = next(
        (e for e in money_tracker.get("entrants", []) if e.get("entrant_id") == eid),
        {},
    )

    odds = runner.get("odds", {})
    flucs = runner.get("flucs_with_timestamp", {})
    speedmap = runner.get("speedmap", {})
    open_fluc = _safe_float((flucs.get("open") or {}).get("fluc"))
    current_fluc = _safe_float(odds.get("fixed_win"))
    fluc_drift = None
    if open_fluc and current_fluc and open_fluc > 0:
        fluc_drift = (current_fluc - open_fluc) / open_fluc

    data = dict(
        event_id=event_id,
        entrant_id=eid,
        name=runner.get("name", ""),
        runner_number=runner.get("runner_number", 0),
        barrier=runner.get("barrier", 0),
        is_scratched=bool(runner.get("is_scratched")),
        is_late_scratched=bool(runner.get("is_late_scratched")),
        jockey=runner.get("jockey", ""),
        trainer_name=runner.get("trainer_name", ""),
        age=runner.get("age"),
        sex=runner.get("sex", ""),
        weight_total=_parse_weight(runner.get("weight")),
        weight_allocated=_safe_float((runner.get("weight") or {}).get("allocated") if isinstance(runner.get("weight"), dict) else None),
        handicap_rating=_safe_float(runner.get("handicap_rating")),
        spr=_safe_float(runner.get("spr")),
        class_level=runner.get("class_level", ""),
        colour=runner.get("colour", ""),
        is_first_start=bool(runner.get("first_start_indicator")),
        apprentice_indicator=runner.get("apprentice_indicator", ""),
        gear=runner.get("gear", ""),
        tab_fixed_win=_safe_float(odds.get("fixed_win")),
        tab_fixed_place=_safe_float(odds.get("fixed_place")),
        tab_pool_win=_safe_float(odds.get("pool_win")),
        tab_pool_place=_safe_float(odds.get("pool_place")),
        fluc_open=open_fluc,
        fluc_9am=_safe_float((flucs.get("nine_am") or {}).get("fluc")),
        fluc_high=_safe_float((flucs.get("high") or {}).get("fluc")),
        fluc_low=_safe_float((flucs.get("low") or {}).get("fluc")),
        fluc_drift=fluc_drift,
        is_market_mover=bool(runner.get("mover")),
        is_favourite=bool(runner.get("favourite")),
        hold_pct=_safe_float(money_entry.get("hold_percentage")),
        bet_pct=_safe_float(money_entry.get("bet_percentage")),
        speedmap_label=speedmap.get("label", ""),
        barrier_speed=_safe_float(speedmap.get("barrier_speed")),
        finish_speed=_safe_float(speedmap.get("finish_speed")),
        settling_lengths=_safe_float(speedmap.get("settling_lengths")),
        raw_json=json.dumps(runner),
    )

    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        existing.snapshotted_at = datetime.utcnow()
    else:
        db.add(Runner(**data))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def snapshot_race(event_id: str) -> dict:
    """
    Fetch live race detail, persist runners + market snapshot, return payload.
    Called ~2 hours before jump and again every 90s until race status = closed.
    """
    payload = fetch_race_detail(event_id)
    db = SessionLocal()
    try:
        runners = payload.get("runners", [])
        money_tracker = payload.get("money_tracker", {})

        # Compute margin-removed implied probabilities across the field
        raw_probs = []
        for r in runners:
            fw = _safe_float((r.get("odds") or {}).get("fixed_win"))
            raw_probs.append((1 / fw) if fw and fw > 1 else 0.0)
        total = sum(raw_probs) or 1.0
        norm_probs = [p / total for p in raw_probs]

        for runner, implied in zip(runners, norm_probs):
            _snapshot_runner(db, event_id, runner, money_tracker)
            # Write implied prob back
            existing = (
                db.query(Runner)
                .filter(
                    Runner.event_id == event_id,
                    Runner.entrant_id == runner.get("entrant_id"),
                )
                .first()
            )
            if existing:
                existing.tab_implied_prob = implied

        db.commit()
    finally:
        db.close()

    return payload


def fetch_and_store_results(event_id: str):
    """Persist race results after the race settles."""
    payload = fetch_race_detail(event_id)
    results = payload.get("results", [])
    if not results:
        return

    db = SessionLocal()
    try:
        for r in results:
            _upsert_result(db, event_id, r)
        db.commit()
    finally:
        db.close()


def backfill(
    date_from: str,
    date_to: str,
    delay: float = 0.5,
):
    """
    Historical backfill via /extras.
    date_from / date_to: ISO strings e.g. "2023-01-01"

    For each completed meeting, also fetches full race detail so we capture
    runner form data (needed for feature engineering at training time).
    The raw_json column on Runner stores the full runner dict.
    """
    init_db()
    db = SessionLocal()
    total_races = 0

    try:
        for country in COUNTRIES:
            page_token = None
            log.info("Backfilling %s from %s to %s", country, date_from, date_to)

            while True:
                page = fetch_extras_page(country, date_from, date_to, page_token)
                extras = page.get("extras", [])

                for extra in extras:
                    meeting = extra.get("meeting", {})
                    mid = meeting.get("meeting_id", "")
                    _upsert_meeting(db, meeting, country)

                    for market in extra.get("markets", []):
                        # extras gives us results but not full runner form.
                        # Store results immediately; then fetch full detail.
                        for result in market.get("results", []):
                            # We need an event_id — derive from entrant context.
                            # The extras endpoint doesn't give event_id directly;
                            # we'll fetch the meeting's races separately below.
                            pass

                db.commit()

                # For each meeting in this page, fetch today's race list
                # to get event_ids, then fetch full race detail.
                for extra in extras:
                    meeting = extra.get("meeting", {})
                    mid = meeting.get("meeting_id", "")
                    meeting_date = str(meeting.get("advertised_start", ""))[:10]

                    # Fetch meeting races via the meetings list endpoint
                    try:
                        meetings_data = _get(
                            "",
                            params={
                                "category": CATEGORY,
                                "country": country,
                                "date": meeting_date,
                            },
                        )
                    except Exception as e:
                        log.warning("Could not fetch meeting list for %s: %s", mid, e)
                        continue

                    for m in meetings_data.get("meetings", []):
                        if m.get("meeting") != mid and m.get("name") != meeting.get("meeting_name"):
                            continue
                        for race in m.get("races", []):
                            eid = race.get("id")
                            if not eid:
                                continue
                            _upsert_race(db, race, mid)
                            db.commit()

                            if race.get("status") not in ("Paying", "Resulted", "Interim"):
                                continue
                            try:
                                detail = fetch_race_detail(eid)
                                money_tracker = detail.get("money_tracker", {})

                                raw_probs = []
                                for r in detail.get("runners", []):
                                    fw = _safe_float((r.get("odds") or {}).get("fixed_win"))
                                    raw_probs.append((1 / fw) if fw and fw > 1 else 0.0)
                                total = sum(raw_probs) or 1.0
                                norm_probs = [p / total for p in raw_probs]

                                for runner, implied in zip(detail.get("runners", []), norm_probs):
                                    _snapshot_runner(db, eid, runner, money_tracker)
                                    existing = (
                                        db.query(Runner)
                                        .filter(
                                            Runner.event_id == eid,
                                            Runner.entrant_id == runner.get("entrant_id"),
                                        )
                                        .first()
                                    )
                                    if existing:
                                        existing.tab_implied_prob = implied

                                for r in detail.get("results", []):
                                    _upsert_result(db, eid, r)

                                db.commit()
                                total_races += 1
                                time.sleep(delay)
                            except Exception as e:
                                log.warning("Error fetching race %s: %s", eid, e)
                                db.rollback()

                page_token = page.get("next_page_token")
                if not page_token:
                    break
                time.sleep(delay)

    finally:
        db.close()

    log.info("Backfill complete. Stored %d races.", total_races)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="TAB data collector")
    sub = parser.add_subparsers(dest="cmd")

    bp = sub.add_parser("backfill")
    bp.add_argument("--from", dest="date_from", required=True)
    bp.add_argument("--to", dest="date_to", required=True)
    bp.add_argument("--delay", type=float, default=0.5)

    sp = sub.add_parser("snapshot")
    sp.add_argument("event_id")

    args = parser.parse_args()
    if args.cmd == "backfill":
        init_db()
        backfill(args.date_from, args.date_to, args.delay)
    elif args.cmd == "snapshot":
        init_db()
        snapshot_race(args.event_id)
