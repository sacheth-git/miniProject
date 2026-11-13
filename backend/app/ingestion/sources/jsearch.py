"""JSearch on RapidAPI (RAPIDAPI_KEY).

The only route for LinkedIn / Indeed / Naukri / Glassdoor listings: JSearch aggregates
Google for Jobs and returns each listing's `apply_options` (one per publisher). All of
them are kept so the Apply button can offer "Apply on LinkedIn / Naukri / Company site".
"""

from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob
from app.ingestion.http import SourceHTTPError
from app.ingestion.sources.keyed import DEFAULT_LOCATION, DEFAULT_QUERIES

log = get_logger(__name__)
HOST = "jsearch.p.rapidapi.com"
URL = f"https://{HOST}/search"


def _highlights(h: dict) -> str:  # type: ignore[type-arg]
    parts = []
    for title, items in (h or {}).items():
        if items:
            parts.append(f"<h3>{title}</h3><ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
    return "\n".join(parts)


def parse(data: dict) -> list[RawJob]:  # type: ignore[type-arg]
    out: list[RawJob] = []
    for j in data.get("data", []) or []:
        options = [
            ApplyOption(o.get("publisher") or "Apply", o["apply_link"], bool(o.get("is_direct")))
            for o in j.get("apply_options") or []
            if o.get("apply_link")
        ]
        apply = j.get("job_apply_link") or (options[0].url if options else "")
        if not apply:
            continue
        if not options:
            options = [ApplyOption(j.get("job_publisher") or "Apply", apply, bool(j.get("job_apply_is_direct")))]
        ts = j.get("job_posted_at_datetime_utc")
        try:
            posted = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
        except ValueError:
            posted = None
        loc = ", ".join(p for p in [j.get("job_city"), j.get("job_state"), j.get("job_country")] if p)
        exp = (j.get("job_required_experience") or {}).get("required_experience_in_months")
        desc = (j.get("job_description") or "") + "\n" + _highlights(j.get("job_highlights") or {})
        out.append(
            RawJob(
                source="jsearch",
                source_job_id=str(j.get("job_id")),
                title=(j.get("job_title") or "").strip(),
                company=(j.get("employer_name") or "").strip(),
                description=desc,
                apply_url=apply,
                source_url=j.get("job_google_link") or apply,
                location=loc or j.get("job_location"),
                remote=j.get("job_is_remote"),
                job_type=j.get("job_employment_type"),
                posted_at=posted,
                apply_options=options,
                experience_months=int(exp) if isinstance(exp, (int, float)) else None,
                country=j.get("job_country"),
                extra={"publisher": j.get("job_publisher")},
            )
        )
    return out


class JSearchSource(JobSource):
    name = "jsearch"
    requires_keys = ("RAPIDAPI_KEY",)

    def available(self) -> tuple[bool, str]:
        ok = bool(get_settings().rapidapi_key)
        return ok, "" if ok else "RAPIDAPI_KEY not set"

    def fetch(self) -> list[RawJob]:
        key = get_settings().rapidapi_key or ""
        headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": HOST}
        jobs: list[RawJob] = []
        for q in DEFAULT_QUERIES:
            params = {"query": f"{q} in {DEFAULT_LOCATION}", "page": "1", "num_pages": "1", "date_posted": "month", "country": "in"}
            try:
                data = self.http.get_json(URL, params=params, headers=headers)
            except SourceHTTPError as exc:
                log.warning("jsearch %r failed: %s", q, exc.status)
                if exc.status in (401, 403, 429):
                    break  # bad key or quota exhausted: stop spending calls
                continue
            jobs.extend(parse(data))
        return jobs
