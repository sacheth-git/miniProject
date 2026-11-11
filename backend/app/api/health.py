"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import get_settings
from app.core.db import ping_db
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
log = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    sources_configured: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        ping_db()
        db_status = "ok"
    except Exception:  # surfaced in response, also logged with traceback
        log.exception("Database health check failed")
        db_status = "error"
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=__version__,
        database=db_status,
        sources_configured=get_settings().source_keys_status(),
    )
