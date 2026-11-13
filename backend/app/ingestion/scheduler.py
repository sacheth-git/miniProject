"""APScheduler jobs: ingestion every 12 h, link check nightly."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.ingestion.http import HttpClient

log = get_logger(__name__)
_scheduler: BackgroundScheduler | None = None


def ingest_job() -> None:
    from app.ingestion.pipeline import run_ingestion

    with SessionLocal() as db:
        try:
            run_ingestion(db)
        except RuntimeError as exc:
            log.warning("Scheduled ingestion skipped: %s", exc)
        except Exception:
            log.exception("Scheduled ingestion failed")


def link_check_job() -> None:
    from app.ingestion.link_checker import check_links

    http = HttpClient(cache_dir=None)
    try:
        with SessionLocal() as db:
            check_links(db, http)
    except Exception:
        log.exception("Scheduled link check failed")
    finally:
        http.close()


def start_scheduler(ingest_hours: int = 12) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone="Asia/Kolkata", job_defaults={"coalesce": True, "max_instances": 1})
    sched.add_job(ingest_job, IntervalTrigger(hours=ingest_hours), id="ingest", replace_existing=True)
    sched.add_job(link_check_job, CronTrigger(hour=2, minute=30), id="link_check", replace_existing=True)
    sched.start()
    _scheduler = sched
    log.info("Scheduler started: ingest every %dh, link check daily 02:30 IST", ingest_hours)
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
