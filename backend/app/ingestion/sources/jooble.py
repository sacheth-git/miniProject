"""Jooble REST API (JOOBLE_KEY)."""

from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob
from app.ingestion.http import SourceHTTPError
from app.ingestion.sources.keyed import DEFAULT_LOCATION, DEFAULT_QUERIES

log = get_logger(__name__)
URL = "https://jooble.org/api/{key}"


def parse(data: dict) -> list[RawJob]:  # type: ignore[type-arg]
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        url = j.get("link") or ""
        if not url:
            continue
        try:
            posted = datetime.fromisoformat(j["updated"].split(".")[0]) if j.get("updated") else None
        except ValueError:
            posted = None
        out.append(
            RawJob(
                source="jooble",
                source_job_id=str(j.get("id")),
                title=(j.get("title") or "").strip(),
                company=(j.get("company") or "").strip(),
                description=j.get("snippet") or "",
                apply_url=url,
                source_url=url,
                location=j.get("location"),
                job_type=j.get("type"),
                posted_at=posted,
                apply_options=[ApplyOption(j.get("source") or "Jooble", url, False)],
            )
        )
    return out


class JoobleSource(JobSource):
    name = "jooble"
    requires_keys = ("JOOBLE_KEY",)

    def available(self) -> tuple[bool, str]:
        ok = bool(get_settings().jooble_key)
        return ok, "" if ok else "JOOBLE_KEY not set"

    def fetch(self) -> list[RawJob]:
        key = get_settings().jooble_key
        jobs: list[RawJob] = []
        for q in DEFAULT_QUERIES:
            body = {"keywords": q, "location": DEFAULT_LOCATION, "page": "1"}
            try:
                # The key is in the URL path; cache under a key-free URL.
                data = self.http.request_json(
                    "POST", URL.format(key=key), json_body=body, cache_key_params={"_jooble": q}
                )
            except SourceHTTPError as exc:
                log.warning("jooble %r failed: %s", q, exc.status)
                continue
            jobs.extend(parse(data))
        return jobs
