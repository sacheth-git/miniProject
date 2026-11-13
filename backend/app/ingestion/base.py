"""Source interface and the raw job record every source produces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.ingestion.http import HttpClient


@dataclass
class ApplyOption:
    publisher: str
    url: str
    is_direct: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"publisher": self.publisher, "url": self.url, "is_direct": self.is_direct}


@dataclass
class RawJob:
    """Source-shaped job before normalisation. Descriptions may be HTML."""

    source: str
    source_job_id: str
    title: str
    company: str
    description: str
    apply_url: str
    source_url: str | None = None
    location: str | None = None
    remote: bool | None = None
    job_type: str | None = None  # source's own employment-type string
    posted_at: datetime | None = None
    apply_options: list[ApplyOption] = field(default_factory=list)
    experience_months: int | None = None  # when the source provides it
    country: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class SourceUnavailable(RuntimeError):
    """Source cannot run (e.g. API key missing). Not an error: it is skipped."""


class JobSource(ABC):
    name: str = "base"
    requires_keys: tuple[str, ...] = ()

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def available(self) -> tuple[bool, str]:
        return True, ""

    @abstractmethod
    def fetch(self) -> list[RawJob]:
        """Return raw jobs. Per-item problems are logged, not raised."""
