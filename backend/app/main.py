"""FastAPI application entry point."""

from __future__ import annotations

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    admin, applications, auth, deeplinks, health, imports, jobs, match, resume, student_campus, tpo, tpo_analytics,
    tpo_drives, tpo_rounds,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


def _load_models() -> None:
    """Load spaCy, the encoder and taxonomy embeddings so the first upload is fast."""
    log = get_logger("app.warmup")
    try:
        from app.skills.extractor import get_extractor

        ext = get_extractor()
        ext.extract({"experience": "Built machine learning models in Python."})
        from app.embeddings.faiss_index import get_index
        from app.matching.service import get_skill_space

        get_skill_space().vectors([{"skill_id": "python", "name": "Python"}])
        idx = get_index()
        log.info("Job index: %s", f"{len(idx)} jobs" if idx else "not built (run scripts/build_index.py)")
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
    app.include_router(auth.router)
    app.include_router(auth.student_router)
    app.include_router(tpo.router)
    app.include_router(tpo_drives.router)
    app.include_router(tpo_rounds.router)
    app.include_router(tpo_analytics.router)
    app.include_router(tpo_analytics.public)
    app.include_router(student_campus.router)
    app.include_router(resume.router)
    app.include_router(jobs.router)
    app.include_router(imports.router)
    app.include_router(deeplinks.router)
    app.include_router(match.router)
    app.include_router(applications.router)
    app.include_router(admin.router)

    @app.on_event("startup")
    def _warm_up() -> None:
        if settings.environment == "test":
            return
        threading.Thread(target=_load_models, name="model-warmup", daemon=True).start()
        if settings.enable_scheduler:
            from app.ingestion.scheduler import start_scheduler

            start_scheduler(settings.ingest_interval_hours)

    @app.on_event("shutdown")
    def _shutdown() -> None:
        from app.ingestion.scheduler import stop_scheduler

        stop_scheduler()

    if settings.jwt_secret in ("change-me", "change-me-in-.env") or len(settings.jwt_secret) < 32:
        if settings.environment == "production":
            raise RuntimeError("Set a strong JWT_SECRET (32+ characters) in .env before running in production")
        log.warning("JWT_SECRET is weak or default; fine for local dev, never for production")

    missing = [k for k, ok in settings.source_keys_status().items() if not ok]
    if missing:
        log.warning("Job sources without API keys (will be skipped): %s", ", ".join(missing))
    return app


app = create_app()
