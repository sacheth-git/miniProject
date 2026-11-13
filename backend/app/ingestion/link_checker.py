"""Nightly link check: mark jobs whose apply URL is gone (404/410) as inactive.

Job-board pages we must not crawl (LinkedIn, Indeed, Naukri, Glassdoor, Google...)
are never requested; those listings expire via the source API instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion.http import HttpClient
from app.models.job import Job

log = get_logger(__name__)

NO_CHECK_DOMAINS = (
    "linkedin.com", "indeed.com", "naukri.com", "glassdoor.", "google.", "wellfound.com",
    "angel.co", "foundit.in", "monster.", "shine.com", "instahyre.com", "iimjobs.com",
)
GONE = {404, 410}


def checkable(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return bool(host) and not any(d in host for d in NO_CHECK_DOMAINS)


def check_links(db: Session, http: HttpClient, limit: int = 500, min_age_hours: int = 20) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    rows = db.scalars(
        select(Job)
        .where(Job.is_active.is_(True), or_(Job.last_checked_at.is_(None), Job.last_checked_at < cutoff))
        .order_by(Job.last_checked_at.is_not(None), Job.last_checked_at)
        .limit(limit)
    ).all()
    stats = {"checked": 0, "deactivated": 0, "skipped": 0, "errors": 0}
    now = datetime.now(timezone.utc)
    for job in rows:
        if not checkable(job.apply_url):
            stats["skipped"] += 1
            continue
        status = http.check_url(job.apply_url)
        job.last_checked_at = now
        stats["checked"] += 1
        if status is None:
            stats["errors"] += 1
        elif status in GONE:
            job.is_active = False
            stats["deactivated"] += 1
            log.info("Deactivated job %s (%s): apply URL returned %d", job.id, job.title, status)
    db.commit()
    log.info("Link check: %s", stats)
    return stats
