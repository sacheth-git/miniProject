"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Typed config. Every key is optional so missing sources degrade gracefully."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SkillMatch"
    environment: str = "dev"
    log_level: str = "INFO"
    log_json: bool = False

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'skillmatch.db').as_posix()}"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Auth
    jwt_secret: str = "change-me-in-.env"
    jwt_access_minutes: int = 30
    jwt_refresh_days: int = 14

    # Ingestion
    enable_scheduler: bool = True
    ingest_interval_hours: int = 12

    # Embeddings
    index_dir: str = str(BACKEND_DIR / "data" / "faiss")
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_fallback_model: str = "all-MiniLM-L6-v2"
    bias_aware_default: bool = True

    # Scoring weights (overwritten after learning in Phase 6)
    w_alpha: float = 0.4
    w_beta: float = 0.4
    w_gamma: float = 0.2
    w_delta: float = 0.15

    # Job source keys (all optional)
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    jooble_key: str | None = None
    rapidapi_key: str | None = None
    serpapi_key: str | None = None

    # Email
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@skillmatch.local"

    def source_keys_status(self) -> dict[str, bool]:
        """Which keyed sources are configured (never exposes the values)."""
        return {
            "adzuna": bool(self.adzuna_app_id and self.adzuna_app_key),
            "jooble": bool(self.jooble_key),
            "jsearch": bool(self.rapidapi_key),
            "serpapi": bool(self.serpapi_key),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
