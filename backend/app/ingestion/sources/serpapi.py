"""SerpApi Google Jobs API (SERPAPI_KEY). Optional alternative to JSearch."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob
from app.ingestion.http import SourceHTTPError
from app.ingestion.sources.keyed import DEFAULT_LOCATION, DEFAULT_QUERIES

log = get_logger(__name__)
URL = "https://serpapi.com/search.json"


def parse(data: dict) -> list[RawJob]:  # type: ignore[type-arg]
    out: list[RawJob] = []
    for j in data.get("jobs_results", []) or []:
        options = [ApplyOption(o.get("title") or "Apply", o["link"]) for o in j.get("apply_options") or [] if o.get("link")]
        if not options:
            continue
        ext = j.get("detected_extensions") or {}
        highlights = "\n".join(
            f"<h3>{h.get('title', '')}</h3><ul>" + "".join(f"<li>{i}</li>" for i in h.get("items", [])) + "</ul>"
            for h in j.get("job_highlights") or []
        )
        out.append(
            RawJob(
                source="serpapi",
                source_job_id=str(j.get("job_id"))[:200],
                title=(j.get("title") or "").strip(),
                company=(j.get("company_name") or "").strip(),
                description=(j.get("description") or "") + "\n" + highlights,
                apply_url=options[0].url,
                source_url=j.get("share_link") or options[0].url,
                location=j.get("location"),
                remote=bool(ext.get("work_from_home")) or None,
                job_type=ext.get("schedule_type"),
                apply_options=options,
                extra={"via": j.get("via"), "posted_at_text": ext.get("posted_at")},
            )
        )
    return out


# Each page is one search from the monthly quota (free plan is small): 10 queries x 2 pages = 20 per run.
PAGES = 2

class SerpApiSource(JobSource):
    name = "serpapi"
    requires_keys = ("SERPAPI_KEY",)

    def available(self) -> tuple[bool, str]:
        ok = bool(get_settings().serpapi_key)
        return ok, "" if ok else "SERPAPI_KEY not set"

    def fetch(self) -> list[RawJob]:
        key = get_settings().serpapi_key
        jobs: list[RawJob] = []
        for q in DEFAULT_QUERIES:
            params: dict[str, str] = {"engine": "google_jobs", "q": q, "location": DEFAULT_LOCATION, "hl": "en"}
            for _ in range(PAGES):
                try:
                    data = self.http.get_json(URL, params={**params, "api_key": key}, cache_key_params=params)
                except SourceHTTPError as exc:
                    log.warning("serpapi %r failed: %s", q, exc.status)
                    if exc.status in (401, 403, 429):
                        return jobs  # bad key or quota used up: stop spending searches
                    break
                jobs.extend(parse(data))
                token = (data.get("serpapi_pagination") or {}).get("next_page_token")
                if not token:
                    break
                params = {**params, "next_page_token": token}
        return jobs
