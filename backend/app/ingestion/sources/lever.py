"""Lever public Postings API (no key)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob
from app.ingestion.http import SourceHTTPError
from app.ingestion.sources.ats import Board, boards_for

log = get_logger(__name__)
URL = "https://api.lever.co/v0/postings/{token}"


def _lists_html(lists: list[dict]) -> str:  # type: ignore[type-arg]
    parts = []
    for item in lists or []:
        parts.append(f"<h3>{item.get('text', '')}</h3>{item.get('content', '')}")
    return "\n".join(parts)


def parse_board(board: Board, data: list[dict]) -> list[RawJob]:  # type: ignore[type-arg]
    out: list[RawJob] = []
    for j in data:
        cats = j.get("categories") or {}
        hosted = j.get("hostedUrl") or ""
        apply = j.get("applyUrl") or hosted
        if not apply:
            continue
        created = j.get("createdAt")
        desc = "\n".join(
            p for p in [j.get("description") or "", _lists_html(j.get("lists") or []), j.get("additional") or ""] if p
        )
        workplace = (j.get("workplaceType") or "").lower()
        out.append(
            RawJob(
                source="lever",
                source_job_id=f"{board.token}:{j['id']}",
                title=(j.get("text") or "").strip(),
                company=board.name,
                description=desc,
                apply_url=apply,
                source_url=hosted or apply,
                location=cats.get("location"),
                remote=True if workplace == "remote" else (False if workplace == "on-site" else None),
                job_type=cats.get("commitment"),
                posted_at=datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None,
                apply_options=[ApplyOption(f"{board.name} careers (Lever)", apply, True)],
                country=j.get("country"),
            )
        )
    return out


class LeverSource(JobSource):
    name = "lever"

    def fetch(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        for board in boards_for("lever"):
            try:
                data = self.http.get_json(URL.format(token=board.token), params={"mode": "json"})
            except SourceHTTPError as exc:
                log.warning("lever board %s failed: %s", board.token, exc)
                continue
            jobs.extend(parse_board(board, data if isinstance(data, list) else []))
        return jobs
