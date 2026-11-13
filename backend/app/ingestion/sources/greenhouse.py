"""Greenhouse public Job Board API (no key)."""

from __future__ import annotations

import html
import re
from datetime import datetime

from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob
from app.ingestion.http import SourceHTTPError
from app.ingestion.sources.ats import Board, boards_for

log = get_logger(__name__)
URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
# Some boards report their company as "Rubrik Job Board" / "Acme Careers".
BOARD_SUFFIX = re.compile(r"\s*[-|]?\s*(job board|careers?( page| site)?|jobs)\s*$", re.I)


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
        url = j.get("absolute_url") or ""
        if not url:
            continue
        meta = {m.get("name", "").lower(): m.get("value") for m in j.get("metadata") or [] if isinstance(m, dict)}
        emp = next((str(v) for k, v in meta.items() if "employment" in k or "job type" in k), None)
        out.append(
            RawJob(
                source="greenhouse",
                source_job_id=f"{board.token}:{j['id']}",
                title=j.get("title", "").strip(),
                company=BOARD_SUFFIX.sub("", j.get("company_name") or board.name).strip() or board.name,
                description=html.unescape(j.get("content") or ""),
                apply_url=url,
                source_url=url,
                location=(j.get("location") or {}).get("name"),
                job_type=emp,
                posted_at=_dt(j.get("first_published") or j.get("updated_at")),
                apply_options=[ApplyOption(f"{board.name} careers (Greenhouse)", url, True)],
            )
        )
    return out


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def fetch(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        for board in boards_for("greenhouse"):
            try:
                data = self.http.get_json(URL.format(token=board.token), params={"content": "true"})
            except SourceHTTPError as exc:
                log.warning("greenhouse board %s failed: %s", board.token, exc)
                continue
            jobs.extend(parse_board(board, data))
        return jobs
