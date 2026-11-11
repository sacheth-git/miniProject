"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("app")

    app = FastAPI(
        title="SkillMatch API",
        version=__version__,
        description="Semantic resume-job matching with skill-weighted embeddings.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)

    missing = [k for k, ok in settings.source_keys_status().items() if not ok]
    if missing:
        log.warning("Job sources without API keys (will be skipped): %s", ", ".join(missing))
    return app


app = create_app()
