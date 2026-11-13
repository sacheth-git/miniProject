"""Adzuna Jobs API (ADZUNA_APP_ID / ADZUNA_APP_KEY)."""

from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.base import ApplyOption, JobSource, RawJob
from app.ingestion.http import SourceHTTPError
from app.ingestion.sources.keyed import DEFAULT_QUERIES

log = get_logger(__name__)
URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
COUNTRIES = ("in",)
PAGES = 2
CONTRACT = {"permanent": "full-time", "contract": "contract"}


def parse(data: dict, country: str) -> list[RawJob]:  # type: ignore[type-arg]
    out: list[RawJob] = []
    for j in data.get("results", []):
        url = j.get("redirect_url") or ""
        if not url:
            continue
        try:
            posted = datetime.fromisoformat(j["created"].replace("Z", "+00:00")) if j.get("created") else None
        except ValueError:
            posted = None
        out.append(
            RawJob(
                source="adzuna",
                source_job_id=str(j.get("id")),
                title=(j.get("title") or "").strip(),
                company=((j.get("company") or {}).get("display_name") or "").strip(),
                description=j.get("description") or "",
                apply_url=url,
                source_url=url,
                location=(j.get("location") or {}).get("display_name"),
                job_type=CONTRACT.get(j.get("contract_type") or "") or j.get("contract_time"),
                posted_at=posted,
                apply_options=[ApplyOption("Adzuna", url, False)],
                country=country.upper(),
            )
        )
    return out


class AdzunaSource(JobSource):
    name = "adzuna"
    requires_keys = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")

    def available(self) -> tuple[bool, str]:
        s = get_settings()
        ok = bool(s.adzuna_app_id and s.adzuna_app_key)
        return ok, "" if ok else "ADZUNA_APP_ID / ADZUNA_APP_KEY not set"

    def fetch(self) -> list[RawJob]:
        s = get_settings()
        jobs: list[RawJob] = []
        for country in COUNTRIES:
            for q in DEFAULT_QUERIES:
                for page in range(1, PAGES + 1):
                    params = {"what": q, "results_per_page": 50, "max_days_old": 30, "content-type": "application/json"}
                    try:
                        data = self.http.get_json(
                            URL.format(country=country, page=page),
                            params={**params, "app_id": s.adzuna_app_id, "app_key": s.adzuna_app_key},
                            cache_key_params={**params, "_c": country, "_p": page},
                        )
                    except SourceHTTPError as exc:
                        log.warning("adzuna %s/%s p%d failed: %s", country, q, page, exc)
                        break
                    batch = parse(data, country)
                    jobs.extend(batch)
                    if len(batch) < 50:
                        break
        return jobs
