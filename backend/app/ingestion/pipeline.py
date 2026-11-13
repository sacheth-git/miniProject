"""fetch -> normalise -> HTML-to-text -> JD skills + weights -> upsert -> embed + dedup."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.embeddings.documents import job_document, text_ref
from app.ingestion.base import JobSource
from app.ingestion.dedup import dedup_jobs
from app.ingestion.http import HttpClient
from app.ingestion.normalizer import NormalizedJob, normalize
from app.ingestion.sources import build_sources
from app.models.job import Job, SourceRun
from app.skills.extractor import SkillExtractor
from app.skills.jd_skill_weighter import extract_jd_skills

log = get_logger(__name__)

# Sources that return their complete current feed: a job missing from it is closed.
FULL_FEED_SOURCES = {"greenhouse", "lever", "ashby", "remotive"}
# Search-API sources return partial results: expire jobs not seen for this long.
SEARCH_EXPIRY = timedelta(days=30)

_run_lock = threading.Lock()


@dataclass
class RunResult:
    source: str
    status: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    deactivated: int = 0
    errors: int = 0
    message: str = ""


@dataclass
class IngestReport:
    runs: list[RunResult] = field(default_factory=list)
    dedup: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"runs": [asdict(r) for r in self.runs], "dedup": self.dedup}


def apply_fields(job: Job, n: NormalizedJob, extractor: SkillExtractor) -> None:
    job.title = n.title
    job.company = n.company
    job.company_norm = n.company_norm
    job.description = n.description
    job.responsibilities = n.responsibilities
    job.location = n.location
    job.country = n.country
    job.remote = n.remote
    job.job_type = n.job_type
    job.experience_min = n.experience_min
    job.experience_max = n.experience_max
    job.posted_at = n.posted_at
    job.apply_url = n.apply_url
    job.apply_options = n.apply_options
    job.source_url = n.source_url
    job.content_hash = n.content_hash
    req, pref = extract_jd_skills(n.description, extractor)
    job.required_skills = [s.to_dict() for s in req]
    job.preferred_skills = [s.to_dict() for s in pref]
    job.embedding_ref = text_ref(job_document(n.title, n.description))


def upsert_source(db: Session, source: str, normalized: list[NormalizedJob], extractor: SkillExtractor) -> RunResult:
    res = RunResult(source=source, status="ok", fetched=len(normalized))
    existing = {j.source_job_id: j for j in db.scalars(select(Job).where(Job.source == source)).all()}
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    for n in normalized:
        if n.source_job_id in seen:
            continue
        seen.add(n.source_job_id)
        try:
            job = existing.get(n.source_job_id)
            if job is None:
                job = Job(source=source, source_job_id=n.source_job_id)
                apply_fields(job, n, extractor)
                db.add(job)
                res.created += 1
            elif job.content_hash != n.content_hash:
                apply_fields(job, n, extractor)
                res.updated += 1
            job.is_active = True
            job.last_seen_at = now
        except Exception as exc:  # one bad posting must not sink the run
            res.errors += 1
            log.exception("Failed to upsert %s:%s: %s", source, n.source_job_id, exc)
    if source in FULL_FEED_SOURCES and normalized:
        gone = [j for sid, j in existing.items() if sid not in seen and j.is_active]
        for j in gone:
            j.is_active = False
        res.deactivated = len(gone)
    db.commit()
    return res


def expire_search_jobs(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - SEARCH_EXPIRY
    result = db.execute(
        update(Job)
        .where(Job.source.not_in(FULL_FEED_SOURCES | {"import"}), Job.is_active.is_(True), Job.last_seen_at < cutoff)
        .values(is_active=False)
    )
    db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def run_source(db: Session, src: JobSource, extractor: SkillExtractor) -> RunResult:
    run = SourceRun(source=src.name)
    db.add(run)
    db.commit()
    ok, why = src.available()
    if not ok:
        log.warning("Skipping source %s: %s", src.name, why)
        res = RunResult(source=src.name, status="skipped", message=why)
    else:
        try:
            raw = src.fetch()
        except Exception as exc:
            log.exception("Source %s failed", src.name)
            res = RunResult(source=src.name, status="error", errors=1, message=f"{type(exc).__name__}: {exc}"[:500])
        else:
            normalized: list[NormalizedJob] = []
            bad = 0
            for r in raw:
                if not r.title or not r.apply_url:
                    bad += 1
                    continue
                try:
                    normalized.append(normalize(r))
                except Exception:
                    bad += 1
                    log.exception("Normalise failed for %s:%s", r.source, r.source_job_id)
            res = upsert_source(db, src.name, normalized, extractor)
            res.errors += bad
            res.fetched = len(raw)
            if bad:
                res.message = f"{bad} postings skipped (missing title/URL or parse error)"
    for k in ("status", "fetched", "created", "updated", "deactivated", "errors", "message"):
        setattr(run, k, getattr(res, k))
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    log.info("Source %s: %s", src.name, asdict(res))
    return res


def run_dedup(db: Session, encoder: Any) -> dict[str, int]:
    jobs = db.scalars(select(Job).where(Job.is_active.is_(True), Job.owner_id.is_(None))).all()
    stats = dedup_jobs(jobs, encoder)
    db.commit()
    return stats


def run_ingestion(
    db: Session,
    source_names: list[str] | None = None,
    http: HttpClient | None = None,
    extractor: SkillExtractor | None = None,
    encoder: Any = None,
    rebuild_index: bool = True,
) -> IngestReport:
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("An ingestion run is already in progress")
    try:
        if extractor is None:
            from app.skills.extractor import get_extractor

            extractor = get_extractor()
        if encoder is None:
            from app.embeddings.encoder import get_encoder

            encoder = get_encoder()
        own_http = http is None
        http = http or HttpClient()
        report = IngestReport()
        try:
            for src in build_sources(http, source_names):
                report.runs.append(run_source(db, src, extractor))
        finally:
            if own_http:
                http.close()
        expired = expire_search_jobs(db)
        report.dedup = run_dedup(db, encoder)
        report.dedup["expired_search_jobs"] = expired
        if rebuild_index:
            from app.embeddings.faiss_index import build_index, set_index

            index = build_index(db, encoder)
            index.save()
            set_index(index)
            report.dedup["indexed_jobs"] = len(index)
        log.info("Ingestion finished: dedup=%s", report.dedup)
        return report
    finally:
        _run_lock.release()


def is_running() -> bool:
    return _run_lock.locked()
