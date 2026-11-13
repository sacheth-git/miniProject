"""Ashby public Job Posting API (no key)."""

from __future__ import annotations

from datetime import datetime

from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob
from app.ingestion.http import SourceHTTPError
from app.ingestion.sources.ats import Board, boards_for

log = get_logger(__name__)
URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_board(board: Board, data: dict) -> list[RawJob]:  # type: ignore[type-arg]
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        job_url = j.get("jobUrl") or ""
        apply = j.get("applyUrl") or job_url
        if not apply:
            continue
        loc = j.get("location") or ""
        secondary = [s.get("location") for s in j.get("secondaryLocations") or [] if s.get("location")]
        out.append(
            RawJob(
                source="ashby",
                source_job_id=f"{board.token}:{j.get('id') or job_url}",
                title=(j.get("title") or "").strip(),
                company=board.name,
                description=j.get("descriptionHtml") or j.get("descriptionPlain") or "",
                apply_url=apply,
                source_url=job_url or apply,
                location=", ".join([loc, *secondary]) if secondary else loc,
                remote=j.get("isRemote"),
                job_type=j.get("employmentType"),
                posted_at=_dt(j.get("publishedAt")),
                apply_options=[ApplyOption(f"{board.name} careers (Ashby)", apply, True)],
            )
        )
    return out


class AshbySource(JobSource):
    name = "ashby"

    def fetch(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        for board in boards_for("ashby"):
            try:
                data = self.http.get_json(URL.format(token=board.token))
            except SourceHTTPError as exc:
                log.warning("ashby board %s failed: %s", board.token, exc)
                continue
            jobs.extend(parse_board(board, data))
        return jobs
