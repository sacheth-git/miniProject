"""Registry of job sources (legal, official APIs only)."""

from __future__ import annotations

from app.ingestion.base import JobSource
from app.ingestion.http import HttpClient
from app.ingestion.sources.adzuna import AdzunaSource
from app.ingestion.sources.ashby import AshbySource
from app.ingestion.sources.greenhouse import GreenhouseSource
from app.ingestion.sources.jooble import JoobleSource
from app.ingestion.sources.jsearch import JSearchSource
from app.ingestion.sources.lever import LeverSource
from app.ingestion.sources.remotive import RemotiveSource
from app.ingestion.sources.serpapi import SerpApiSource

SOURCE_CLASSES: dict[str, type[JobSource]] = {
    c.name: c
    for c in (
        GreenhouseSource, LeverSource, AshbySource, RemotiveSource,
        AdzunaSource, JoobleSource, JSearchSource, SerpApiSource,
    )
}


def build_sources(http: HttpClient, names: list[str] | None = None) -> list[JobSource]:
    wanted = names or list(SOURCE_CLASSES)
    unknown = set(wanted) - set(SOURCE_CLASSES)
    if unknown:
        raise ValueError(f"Unknown sources: {sorted(unknown)}")
    return [SOURCE_CLASSES[n](http) for n in wanted]
