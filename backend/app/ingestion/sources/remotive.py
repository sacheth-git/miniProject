"""Remotive public API (no key). Remotive asks for <= 4 calls/day and a link back;
one call per run plus the 6 h cache keeps us within that, and every job links to Remotive."""

from __future__ import annotations

from datetime import datetime

from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob

log = get_logger(__name__)
URL = "https://remotive.com/api/remote-jobs"


def parse(data: dict) -> list[RawJob]:  # type: ignore[type-arg]
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        url = j.get("url") or ""
        if not url:
            continue
        try:
            posted = datetime.fromisoformat(j["publication_date"]) if j.get("publication_date") else None
        except ValueError:
            posted = None
        out.append(
            RawJob(
                source="remotive",
                source_job_id=str(j.get("id")),
                title=(j.get("title") or "").strip(),
                company=(j.get("company_name") or "").strip(),
                description=j.get("description") or "",
                apply_url=url,
                source_url=url,
                location=j.get("candidate_required_location") or "Remote",
                remote=True,
                job_type=j.get("job_type"),
                posted_at=posted,
                apply_options=[ApplyOption("Remotive", url, False)],
                extra={"category": j.get("category"), "tags": j.get("tags") or []},
            )
        )
    return out


class RemotiveSource(JobSource):
    name = "remotive"

    def fetch(self) -> list[RawJob]:
        return parse(self.http.get_json(URL))
