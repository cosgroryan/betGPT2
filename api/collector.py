"""
Data collection from TAB Affiliates API.

Confirmed API behaviour (from openapi.json + live testing 2026-04-26):
  - All responses wrap payload under a `data` key  → response["data"]["meetings"]
  - Meetings:    GET /meetings        params: category=T, country=AUS|NZ
  - Race detail: GET /events/{id}     (NOT /{id})
  - Extras:      GET /extras          params: categories=T, countries=AUS,NZ, date_from, date_to
                 date window: 2 days max per request, 14 days max in the past
  - Race list:   GET /list            params: meet_types=T, countries=AUS,NZ, date_from, date_to
  - Country codes: AUS, NZ (not NZL)

Collection modes:
  collect_day(d):     fetch all meetings + results for one date (≤ 14 days ago)
  snapshot_race(eid): live pre-race runner snapshot
  fetch_results(eid): post-race results
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
COUNTRIES = ["AUS", "NZ"]      # NZ not NZL — confirmed from API response
CATEGORY = "T"                  # Thoroughbred
MAX_LOOKBACK_DAYS = 13          # API hard limit is 14; use 13 to stay safe


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f"{AFF_BASE}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError:
            if r.status_code == 429:
                time.sleep(2 ** attempt * 5)
            elif r.status_code >= 500:
                time.sleep(2 ** attempt)
            elif r.status_code == 400:
                body = {}
                try:
                    body = r.json()
                except Exception:
                    pass
                err = (body.get("header") or {}).get("error", r.text[:120])
                raise ValueError(f"API 400: {err}")
            else:
                raise
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed GET {url} after {retries} attempts")


def _unwrap(response: dict, key: str) -> list:
    """Extract a list from either top-level or nested under 'data'."""
    top = response.get(key)
    if top is not None:
        return top
    return (response.get("data") or {}).get(key, [])


# ---------------------------------------------------------------------------
# Meetings for a date
# ---------------------------------------------------------------------------

def fetch_meetings(target_date: Optional[date] = None) -> list[dict]:
    """
    Return all T-category AUS+NZ meetings for a given date.
    The API allows dates within the last 13 days.
    """
    if target_date is None:
        target_date = date.today()

    days_ago = (date.today() - target_date).days
    if days_ago > MAX_LOOKBACK_DAYS:
        raise ValueError(
            f"TAB API limit: {target_date} is {days_ago} days ago (max {MAX_LOOKBACK_DAYS})."
        )

    date_str = target_date.isoformat()
    meetings: list[dict] = []
    for country in COUNTRIES:
        try:
            data = _get(
                "/meetings",
                params={
                    "category": CATEGORY,
                    "country": country,
                    "date_from": date_str,
                    "date_to": date_str,
                },
            )
            for m in _unwrap(data, "meetings"):
                m["_country"] = country
                meetings.append(m)
        except Exception as e:
            log.warning("fetch_meetings %s %s: %s", country, date_str, e)

    return meetings


# ---------------------------------------------------------------------------
# Full race/event detail
# ---------------------------------------------------------------------------

def fetch_race_detail(event_id: str) -> dict:
    """
    Full race payload from /events/{id}.
    Includes runners, odds, form, speedmap, money_tracker, big_bets, results.
    """
    return _get(
        f"/events/{event_id}",
        params={
            "with_money_tracker": "true",
            "with_big_bets": "true",
            "with_biggest_bet": "true",
        },
    )


# ---------------------------------------------------------------------------
# Extras (results) for a single date
# ---------------------------------------------------------------------------

def fetch_extras_for_date(target_date: date) -> list[dict]:
    """
    Returns completed race extras (results + market data) for a single date.
    Uses categories + countries params (plural, as per OpenAPI spec).
    date_from and date_to must be within 2 days of each other.
    """
    date_str = target_date.isoformat()
    try:
        data = _get(
            "/extras",
            params={
                "categories": CATEGORY,
                "countries": ",".join(COUNTRIES),
                "date_from": date_str,
                "date_to": date_str,
            },
        )
    except ValueError as e:
        log.warning("extras %s: %s", date_str, e)
        return []

    return _unwrap(data, "extras")


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _parse_weight(w) -> Optional[float]:
    if isinstance(w, dict):
        return _safe_float(w.get("total"))
    return _safe_float(w)


def _upsert_meeting(db: Session, meeting_dict: dict, country: str):
    mid = (
        meeting_dict.get("meeting")
        or meeting_dict.get("meeting_id")
        or meeting_dict.get("id")
    )
    if not mid:
        return None
    obj = db.get(Meeting, mid)
    if obj is None:
        obj = Meeting(meeting_id=mid)
        db.add(obj)
    raw_date = meeting_dict.get("date", meeting_dict.get("meeting_date", ""))
    obj.date = str(raw_date)[:10]
    obj.name = meeting_dict.get("name", "")
    obj.country = country
    obj.state = meeting_dict.get("state", "")
    obj.track_condition = meeting_dict.get("track_condition", "")
    obj.category = CATEGORY
    return mid


def _upsert_race(db: Session, race: dict, meeting_id: str, country: str) -> Optional[str]:
    eid = race.get("id") or race.get("event_id")
    if not eid:
        return None
    obj = db.get(Race, eid)
    if obj is None:
        obj = Race(event_id=eid)
        db.add(obj)
    obj.meeting_id = meeting_id
    obj.race_number = race.get("race_number", 0)
    obj.name = race.get("name", "")
    obj.distance = race.get("distance", 0)
    obj.status = race.get("status", "")
    obj.start_time = str(race.get("start_time", ""))
    obj.track_condition = race.get("track_condition", "")
    obj.weather = race.get("weather", "")
    obj.country = country
    return eid


def _upsert_result(db: Session, event_id: str, result: dict):
    eid = result.get("entrant_id")
    if not eid:
        return
    existing = (
        db.query(Result)
        .filter(Result.event_id == event_id, Result.entrant_id == eid)
        .first()
    )
    if existing:
        return
    db.add(Result(
        event_id=event_id,
        entrant_id=eid,
        name=result.get("entrant_name", result.get("name", "")),
        position=result.get("position", 0),
        runner_number=result.get("runner_number", 0),
        barrier=result.get("barrier", 0),
        margin_lengths=_safe_float(result.get("margin_length", 0)),
        time_ran=_safe_float(result.get("time_ran", 0)),
        winning_time=_safe_float(result.get("winning_time", 0)),
    ))


def _snapshot_runner(db: Session, event_id: str, runner: dict, money_tracker: dict):
    eid = runner.get("entrant_id")
    if not eid:
        return

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
    current_win = _safe_float(odds.get("fixed_win"))
    fluc_drift = None
    if open_fluc and current_win and open_fluc > 0:
        fluc_drift = (current_win - open_fluc) / open_fluc

    weight_dict = runner.get("weight", {})
    weight_allocated = None
    if isinstance(weight_dict, dict):
        weight_allocated = _safe_float(weight_dict.get("allocated"))

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
        weight_allocated=weight_allocated,
        handicap_rating=_safe_float(runner.get("handicap_rating")),
        spr=_safe_float(runner.get("spr")),
        class_level=runner.get("class_level", ""),
        colour=runner.get("colour", ""),
        is_first_start=bool(runner.get("first_start_indicator")),
        apprentice_indicator=runner.get("apprentice_indicator", ""),
        gear=runner.get("gear", ""),
        tab_fixed_win=current_win,
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


def _compute_implied_probs(runners: list[dict]) -> list[float]:
    raw = []
    for r in runners:
        fw = _safe_float((r.get("odds") or {}).get("fixed_win"))
        raw.append((1 / fw) if fw and fw > 1 else 0.0)
    total = sum(raw) or 1.0
    return [p / total for p in raw]


# ---------------------------------------------------------------------------
# Public: live race snapshot
# ---------------------------------------------------------------------------

def snapshot_race(event_id: str) -> dict:
    """
    Fetch live race detail and persist runner snapshot + market data.
    The full payload is returned so the API server can serve it immediately.
    """
    payload = fetch_race_detail(event_id)

    # Unwrap nested data if present
    if "race" not in payload and "data" in payload:
        payload = payload["data"]

    db = SessionLocal()
    try:
        runners = _unwrap(payload, "runners") or payload.get("runners", [])
        money_tracker = payload.get("money_tracker", {})
        implied = _compute_implied_probs(runners)

        for runner, imp in zip(runners, implied):
            _snapshot_runner(db, event_id, runner, money_tracker)
            obj = (
                db.query(Runner)
                .filter(Runner.event_id == event_id, Runner.entrant_id == runner.get("entrant_id"))
                .first()
            )
            if obj:
                obj.tab_implied_prob = imp

        db.commit()
    finally:
        db.close()

    return payload


# ---------------------------------------------------------------------------
# Public: post-race results
# ---------------------------------------------------------------------------

def fetch_and_store_results(event_id: str):
    payload = fetch_race_detail(event_id)
    if "data" in payload and "race" not in payload:
        payload = payload["data"]

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


# ---------------------------------------------------------------------------
# Public: collect one full race day
# ---------------------------------------------------------------------------

def collect_day(target_date: date, delay: float = 0.5) -> dict:
    """
    Collect all AUS+NZ T-category race data for a single date.
    Fetches meeting list → race detail for each event → persists runners + results.
    """
    init_db()
    db = SessionLocal()
    stats = {"races": 0, "runners": 0, "results": 0}

    try:
        meetings = fetch_meetings(target_date)
        log.info("%s: %d meetings", target_date, len(meetings))

        for meeting in meetings:
            country = meeting.get("_country") or meeting.get("country", "")
            if country not in COUNTRIES:
                continue
            mid = _upsert_meeting(db, meeting, country)
            db.commit()

            for race in meeting.get("races", []):
                eid = _upsert_race(db, race, mid, country)
                db.commit()
                if not eid:
                    continue

                status = race.get("status", "")
                if status not in ("Resulted", "Paying", "Interim", "Final",
                                  "Open", "Closed", "Suspended"):
                    continue

                try:
                    raw = fetch_race_detail(eid)
                    detail = raw.get("data", raw)  # unwrap if nested
                    time.sleep(delay)
                except Exception as e:
                    log.warning("fetch_race_detail %s: %s", eid, e)
                    continue

                # Update race with full metadata
                race_meta = detail.get("race", {})
                race_obj = db.get(Race, eid)
                if race_obj and race_meta:
                    race_obj.distance = race_meta.get("distance", race_obj.distance)
                    race_obj.track_surface = race_meta.get("track_surface", "")
                    race_obj.track_direction = race_meta.get("track_direction", "")
                    race_obj.rail_position = race_meta.get("rail_position", "")
                    race_obj.class_level = race_meta.get("class", "")
                    race_obj.field_size = race_meta.get("field_size", 0)
                    pm = race_meta.get("prize_monies", {})
                    if isinstance(pm, dict) and pm:
                        race_obj.prize_money_first = float(next(iter(pm.values()), 0))
                    race_obj.start_type = race_meta.get("start_type", "")
                    race_obj.status = race_meta.get("status", race_obj.status)
                    db.commit()

                # Runners
                runners = detail.get("runners", [])
                implied = _compute_implied_probs(runners)
                for runner, imp in zip(runners, implied):
                    _snapshot_runner(db, eid, runner, detail.get("money_tracker", {}))
                    obj = (
                        db.query(Runner)
                        .filter(Runner.event_id == eid, Runner.entrant_id == runner.get("entrant_id"))
                        .first()
                    )
                    if obj:
                        obj.tab_implied_prob = imp
                db.commit()
                stats["runners"] += len(runners)

                # Results
                for res in detail.get("results", []):
                    _upsert_result(db, eid, res)
                    stats["results"] += 1
                db.commit()
                stats["races"] += 1

    finally:
        db.close()

    log.info("%s done: %s", target_date, stats)
    return stats


# ---------------------------------------------------------------------------
# Collect the last N days
# ---------------------------------------------------------------------------

def collect_recent(days: int = 13, delay: float = 0.5) -> dict:
    """
    Seed the DB with the last `days` days (capped at API limit).
    Run once on first setup, then use the daily scheduler going forward.
    """
    days = min(days, MAX_LOOKBACK_DAYS)
    today = date.today()
    total: dict[str, int] = {"races": 0, "runners": 0, "results": 0}

    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        log.info("Collecting %s (%d/%d)...", d, days - i + 1, days + 1)
        try:
            stats = collect_day(d, delay=delay)
            for k in total:
                total[k] += stats[k]
        except Exception as e:
            log.warning("collect_day %s failed: %s", d, e)

    log.info("collect_recent complete: %s", total)
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="TAB data collector")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("seed", help="Collect last 13 days (max API window)")
    dp = sub.add_parser("day", help="Collect a specific date (YYYY-MM-DD)")
    dp.add_argument("date")
    sp = sub.add_parser("snapshot", help="Live snapshot of a race")
    sp.add_argument("event_id")

    args = parser.parse_args()
    if args.cmd == "seed":
        collect_recent(13)
    elif args.cmd == "day":
        collect_day(date.fromisoformat(args.date))
    elif args.cmd == "snapshot":
        snapshot_race(args.event_id)
    else:
        parser.print_help()
