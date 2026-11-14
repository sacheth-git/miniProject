"""Admin (is_admin users only): trigger ingestion, per-source status."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.core.db import SessionLocal, get_db
from app.core.logging import get_logger
from app.ingestion import pipeline
from app.ingestion.http import HttpClient
from app.ingestion.sources import SOURCE_CLASSES, build_sources
from app.models.job import Job, SourceRun
from app.schemas.job import IngestRequest, SourcesStatusOut, SourceStatus

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
log = get_logger(__name__)


def _background_ingest(sources: list[str] | None) -> None:
    with SessionLocal() as db:
        try:
            pipeline.run_ingestion(db, sources)
        except Exception:
            log.exception("Background ingestion failed")


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def trigger_ingest(body: IngestRequest | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    body = body or IngestRequest()
    if body.sources:
        unknown = set(body.sources) - set(SOURCE_CLASSES)
        if unknown:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown sources: {sorted(unknown)}")
    if pipeline.is_running():
        raise HTTPException(status.HTTP_409_CONFLICT, "An ingestion run is already in progress")
    if body.wait:
        return pipeline.run_ingestion(db, body.sources).to_dict()
    threading.Thread(target=_background_ingest, args=(body.sources,), daemon=True, name="ingest").start()
    return {"started": True, "sources": body.sources or list(SOURCE_CLASSES)}


@router.get("/sources/status", response_model=SourcesStatusOut)
def sources_status(db: Session = Depends(get_db)) -> SourcesStatusOut:
    counts = dict(db.execute(select(Job.source, func.count()).group_by(Job.source)).all())
    active = dict(db.execute(select(Job.source, func.count()).where(Job.is_active.is_(True)).group_by(Job.source)).all())
    unique = db.scalar(
        select(func.count()).select_from(Job).where(Job.is_active.is_(True), Job.is_duplicate.is_(False))
    ) or 0
    http = HttpClient(cache_dir=None)
    try:
        sources = {s.name: s for s in build_sources(http)}
    finally:
        http.close()
    out: list[SourceStatus] = []
    for name in [*SOURCE_CLASSES, "import"]:
        last = db.scalars(select(SourceRun).where(SourceRun.source == name).order_by(SourceRun.id.desc()).limit(1)).first()
        ok, why = sources[name].available() if name in sources else (True, "user imports")
        out.append(
            SourceStatus(
                source=name,
                configured=ok,
                reason=why,
                active_jobs=int(active.get(name, 0)),
                total_jobs=int(counts.get(name, 0)),
                last_run_at=last.finished_at or last.started_at if last else None,
                last_status=last.status if last else None,
                last_fetched=last.fetched if last else 0,
                last_created=last.created if last else 0,
                last_updated=last.updated if last else 0,
                last_deactivated=last.deactivated if last else 0,
                last_errors=last.errors if last else 0,
                last_message=last.message if last else "",
            )
        )
    return SourcesStatusOut(
        running=pipeline.is_running(),
        total_active=sum(int(v) for v in active.values()),
        total_active_unique=unique,
        sources=out,
    )
