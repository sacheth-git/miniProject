"""FastAPI application entry point."""

from __future__ import annotations

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, resume
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


def _load_models() -> None:
    """Load spaCy, the encoder and taxonomy embeddings so the first upload is fast."""
    log = get_logger("app.warmup")
    try:
        from app.skills.extractor import get_extractor

        ext = get_extractor()
        ext.extract({"experience": "Built machine learning models in Python."})
        log.info("Model warm-up complete")
    except Exception:
        log.exception("Model warm-up failed; models will load on first request")


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
    app.include_router(resume.router)

    @app.on_event("startup")
    def _warm_up() -> None:
        if settings.environment == "test":
            return
        threading.Thread(target=_load_models, name="model-warmup", daemon=True).start()

    missing = [k for k, ok in settings.source_keys_status().items() if not ok]
    if missing:
        log.warning("Job sources without API keys (will be skipped): %s", ", ".join(missing))
    return app


app = create_app()
