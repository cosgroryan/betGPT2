"""
APScheduler-based job runner for betGPT2.

Jobs:
  - collect_today  : runs every 30 min, 5am–11pm NZT (catches all AU+NZ race days)
  - settle_results : runs every 10 min, polls resulted races and fills result rows
  - daily_summary  : runs at midnight, logs day's totals

Run standalone:
  python -m api.scheduler

Or import and start from within the FastAPI app on startup.
"""

import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from api.collector import collect_day, fetch_and_store_results, fetch_meetings
from api.db import Race, Runner, SessionLocal, init_db

log = logging.getLogger(__name__)

# NZT = UTC+12 (standard) / UTC+13 (daylight)
# Run collection 5am–11pm NZT → 17:00–11:00 UTC (cron hour range)
COLLECT_START_UTC = 17   # 5am NZT+12
COLLECT_END_UTC = 11     # 11pm NZT+12


def job_collect_today():
    """Collect today's race data. Safe to run multiple times — upserts."""
    today = date.today()
    log.info("Scheduled: collect_day(%s)", today)
    try:
        stats = collect_day(today, delay=0.4)
        log.info("collect_day done: %s", stats)
    except Exception as e:
        log.error("collect_day failed: %s", e, exc_info=True)


def job_settle_results():
    """
    Find races that are Resulted/Paying but have no result rows yet,
    and fetch their results.
    """
    db = SessionLocal()
    try:
        # Races from the last 2 days with no results yet
        cutoff = datetime.utcnow() - timedelta(days=2)
        races = (
            db.query(Race)
            .filter(
                Race.status.in_(["Resulted", "Paying", "Interim", "Final"]),
                Race.fetched_at >= cutoff,
            )
            .all()
        )

        settled = 0
        for race in races:
            from api.db import Result
            has_results = db.query(Result).filter(Result.event_id == race.event_id).first()
            if has_results:
                continue
            try:
                fetch_and_store_results(race.event_id)
                settled += 1
            except Exception as e:
                log.warning("settle_results %s: %s", race.event_id, e)

        if settled:
            log.info("Settled %d races", settled)
    finally:
        db.close()


def job_daily_summary():
    """Log a short summary of yesterday's collected data."""
    db = SessionLocal()
    try:
        yesterday = date.today() - timedelta(days=1)
        from api.db import Result
        races = db.query(Race).filter(Race.status.in_(["Resulted", "Paying", "Final"])).all()
        runners = db.query(Runner).count()
        results = db.query(Result).count()
        log.info(
            "Daily summary: %d resulted races in DB, %d runner snapshots, %d results",
            len(races), runners, results,
        )
    finally:
        db.close()


def create_scheduler(background: bool = False) -> BackgroundScheduler | BlockingScheduler:
    """
    Build and return a configured scheduler.
    background=True → BackgroundScheduler (for embedding in FastAPI)
    background=False → BlockingScheduler (for standalone process)
    """
    Sched = BackgroundScheduler if background else BlockingScheduler
    scheduler = Sched(timezone="UTC")

    # Collect today's races every 30 minutes, during NZT racing hours
    scheduler.add_job(
        job_collect_today,
        trigger=CronTrigger(
            minute="0,30",
            hour=f"{COLLECT_START_UTC}-23,0-{COLLECT_END_UTC}",
            timezone="UTC",
        ),
        id="collect_today",
        name="Collect today's races",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Settle results every 10 minutes
    scheduler.add_job(
        job_settle_results,
        trigger=IntervalTrigger(minutes=10),
        id="settle_results",
        name="Settle race results",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Daily summary at midnight UTC
    scheduler.add_job(
        job_daily_summary,
        trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="daily_summary",
        name="Daily DB summary",
        replace_existing=True,
    )

    return scheduler


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    init_db()
    log.info("Starting betGPT2 scheduler (standalone mode)...")
    # Run one immediate collection on startup
    job_collect_today()
    scheduler = create_scheduler(background=False)
    scheduler.start()
