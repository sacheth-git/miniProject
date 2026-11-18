"""Every source adapter against a recorded-shape payload (no network)."""

from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings
from app.ingestion.http import HttpClient, SourceHTTPError
from app.ingestion.sources import SOURCE_CLASSES, build_sources
from app.ingestion.sources import adzuna, ashby, greenhouse, jooble, jsearch, lever, remotive, serpapi
from app.ingestion.sources.ats import Board
from tests.fakes import routed_transport

BOARD = Board("acme", "x", "Acme")

GREENHOUSE = {
    "jobs": [
        {
            "id": 11, "title": "Backend Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/11",
            "location": {"name": "Bengaluru, India"}, "updated_at": "2026-10-01T10:00:00Z",
            "content": "&lt;p&gt;Python and Kafka&lt;/p&gt;", "company_name": "Acme Inc Job Board",
            "metadata": [{"name": "Employment Type", "value": "Full-time"}],
        },
        {"id": 12, "title": "No url", "absolute_url": None},
    ]
}
LEVER = [
    {
        "id": "abc", "text": "Data Analyst Intern", "hostedUrl": "https://jobs.lever.co/acme/abc",
        "applyUrl": "https://jobs.lever.co/acme/abc/apply", "createdAt": 1767225600000,
        "categories": {"location": "Pune", "commitment": "Internship"}, "workplaceType": "remote",
        "description": "<p>SQL</p>", "lists": [{"text": "Requirements", "content": "<li>Excel</li>"}],
        "additional": "", "country": "IN",
    }
]
ASHBY = {
    "jobs": [
        {
            "id": "a1", "title": "ML Engineer", "jobUrl": "https://jobs.ashbyhq.com/acme/a1",
            "applyUrl": "https://jobs.ashbyhq.com/acme/a1/application", "location": "Remote",
            "secondaryLocations": [{"location": "Hyderabad"}], "isRemote": True, "employmentType": "FullTime",
            "publishedAt": "2026-10-02T00:00:00.000+00:00", "descriptionHtml": "<p>PyTorch</p>", "isListed": True,
        },
        {"id": "a2", "title": "Hidden", "jobUrl": "https://x", "isListed": False},
    ]
}
REMOTIVE = {
    "jobs": [
        {"id": 7, "url": "https://remotive.com/remote-jobs/7", "title": "DevOps Engineer", "company_name": "Rem",
         "publication_date": "2026-10-03T00:00:00", "candidate_required_location": "India", "job_type": "full_time",
         "description": "<p>Docker</p>", "category": "DevOps", "tags": ["docker"]}
    ]
}
ADZUNA = {"results": [{"id": "9", "redirect_url": "https://adzuna.in/land/9", "title": "Data Scientist",
                       "company": {"display_name": "Adz"}, "description": "Python", "location": {"display_name": "Mumbai"},
                       "contract_type": "permanent", "created": "2026-10-04T00:00:00Z"}]}
JOOBLE = {"jobs": [{"id": 5, "link": "https://jooble.org/desc/5", "title": "Frontend Developer", "company": "Joo",
                    "snippet": "React", "location": "Chennai", "type": "Full-time", "updated": "2026-10-05T00:00:00.0000000",
                    "source": "naukri.com"}]}
JSEARCH = {
    "data": [
        {
            "job_id": "js1", "employer_name": "Flipkart", "job_title": "SDE Intern", "job_publisher": "LinkedIn",
            "job_apply_link": "https://www.linkedin.com/jobs/view/1", "job_description": "Java and DSA",
            "job_is_remote": False, "job_city": "Bengaluru", "job_country": "IN", "job_employment_type": "INTERN",
            "job_posted_at_datetime_utc": "2026-10-06T00:00:00.000Z",
            "apply_options": [
                {"publisher": "LinkedIn", "apply_link": "https://www.linkedin.com/jobs/view/1", "is_direct": False},
                {"publisher": "Naukri", "apply_link": "https://www.naukri.com/job-listings-sde-1", "is_direct": False},
                {"publisher": "Flipkart Careers", "apply_link": "https://flipkartcareers.com/1", "is_direct": True},
            ],
            "job_required_experience": {"required_experience_in_months": None},
            "job_highlights": {"Qualifications": ["Java"], "Responsibilities": ["Build"]},
        }
    ]
}
SERPAPI = {"jobs_results": [{"job_id": "s1", "title": "QA Engineer", "company_name": "Ser", "location": "Noida",
                             "description": "Selenium", "detected_extensions": {"schedule_type": "Full-time"},
                             "apply_options": [{"title": "Naukri", "link": "https://www.naukri.com/job-listings-qa-2"}]},
                            {"job_id": "s2", "title": "No options", "apply_options": []}]}


def test_parsers_produce_raw_jobs() -> None:
    gh = greenhouse.parse_board(BOARD, GREENHOUSE)
    assert len(gh) == 1 and gh[0].description == "<p>Python and Kafka</p>" and gh[0].job_type == "Full-time"
    assert gh[0].company == "Acme Inc" and gh[0].apply_options[0].is_direct
    # Apply opens Greenhouse's hosted application form; the careers page stays as the second option.
    assert gh[0].apply_url.startswith("https://job-boards.greenhouse.io/embed/job_app?for=")
    assert gh[0].apply_options[0].url == gh[0].apply_url and len(gh[0].apply_options) == 2

    lv = lever.parse_board(BOARD, LEVER)
    assert lv[0].remote is True and "Excel" in lv[0].description and lv[0].posted_at is not None

    ab = ashby.parse_board(BOARD, ASHBY)
    assert len(ab) == 1 and ab[0].location == "Remote, Hyderabad"

    assert remotive.parse(REMOTIVE)[0].remote is True
    assert adzuna.parse(ADZUNA, "in")[0].job_type == "full-time"
    assert jooble.parse(JOOBLE)[0].apply_options[0].publisher == "naukri.com"

    js = jsearch.parse(JSEARCH)[0]
    # Employer's own page first (is_direct), so Apply skips the job-board hop.
    assert [o.publisher for o in js.apply_options] == ["Flipkart Careers", "LinkedIn", "Naukri"]
    assert js.apply_url == js.apply_options[0].url
    assert "Qualifications" in js.description and js.location == "Bengaluru, IN"

    sp = serpapi.parse(SERPAPI)
    assert len(sp) == 1 and sp[0].apply_url.startswith("https://www.naukri.com")


def test_keyed_sources_skip_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    for attr in ("adzuna_app_id", "adzuna_app_key", "jooble_key", "rapidapi_key", "serpapi_key"):
        monkeypatch.setattr(s, attr, None)
    http = HttpClient(cache_dir=None)
    try:
        status = {src.name: src.available() for src in build_sources(http)}
    finally:
        http.close()
    for name in ("adzuna", "jooble", "jsearch", "serpapi"):
        ok, why = status[name]
        assert ok is False and "not set" in why
    for name in ("greenhouse", "lever", "ashby", "remotive"):
        assert status[name] == (True, "")


def test_keyed_sources_fetch_with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "adzuna_app_id", "id")
    monkeypatch.setattr(s, "adzuna_app_key", "k")
    monkeypatch.setattr(s, "jooble_key", "jk")
    monkeypatch.setattr(s, "rapidapi_key", "rk")
    monkeypatch.setattr(s, "serpapi_key", "sk")
    seen_headers: dict[str, str] = {}

    def jsearch_handler(req: httpx.Request) -> httpx.Response:
        seen_headers.update(req.headers)
        return httpx.Response(200, json=JSEARCH)

    http = HttpClient(cache_dir=None, min_interval=0, transport=routed_transport({
        "api.adzuna.com": ADZUNA, "jooble.org/api": JOOBLE, "jsearch.p.rapidapi.com": jsearch_handler, "serpapi.com": SERPAPI,
    }))
    try:
        assert len(adzuna.AdzunaSource(http).fetch()) >= 1
        assert len(jooble.JoobleSource(http).fetch()) >= 1
        assert len(jsearch.JSearchSource(http).fetch()) >= 1
        assert len(serpapi.SerpApiSource(http).fetch()) >= 1
    finally:
        http.close()
    assert seen_headers["x-rapidapi-key"] == "rk"


def test_jsearch_stops_on_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "rapidapi_key", "rk")
    calls = {"n": 0}

    def quota(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json={"message": "quota"})

    http = HttpClient(cache_dir=None, min_interval=0, retries=0, transport=routed_transport({"jsearch": quota}))
    try:
        assert jsearch.JSearchSource(http).fetch() == []
    finally:
        http.close()
    assert calls["n"] == 1  # does not burn the remaining queries


def test_ats_sources_iterate_boards(monkeypatch: pytest.MonkeyPatch) -> None:
    boards = {"greenhouse": [Board("acme", "greenhouse", "Acme")], "lever": [Board("acme", "lever", "Acme")],
              "ashby": [Board("acme", "ashby", "Acme"), Board("gone", "ashby", "Gone")]}
    for mod in (greenhouse, lever, ashby):
        monkeypatch.setattr(mod, "boards_for", lambda ats: boards[ats])
    http = HttpClient(cache_dir=None, min_interval=0, retries=0, transport=routed_transport({
        "boards-api.greenhouse.io/v1/boards/acme": GREENHOUSE, "api.lever.co/v0/postings/acme": LEVER,
        "posting-api/job-board/acme": ASHBY, "remotive.com/api": REMOTIVE,
    }))
    try:
        assert len(greenhouse.GreenhouseSource(http).fetch()) == 1
        assert len(lever.LeverSource(http).fetch()) == 1
        assert len(ashby.AshbySource(http).fetch()) == 1  # "gone" board 404s, logged and skipped
        assert len(remotive.RemotiveSource(http).fetch()) == 1
    finally:
        http.close()


def test_http_client_retries_and_caches(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.ingestion.http.time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, json={"ok": 1})

    http = HttpClient(cache_dir=tmp_path, min_interval=0, transport=routed_transport({"example": flaky}))
    try:
        assert http.get_json("https://example.com/a", params={"key": "secret"}, cache_key_params={}) == {"ok": 1}
        assert http.get_json("https://example.com/a", params={"key": "secret"}, cache_key_params={}) == {"ok": 1}
        assert calls["n"] == 2  # second call served from cache
        assert not any("secret" in p.name or "secret" in p.read_text() for p in tmp_path.iterdir())
        with pytest.raises(SourceHTTPError):
            http.get_json("https://other.org/missing")
    finally:
        http.close()


def test_registry() -> None:
    assert set(SOURCE_CLASSES) == {"greenhouse", "lever", "ashby", "remotive", "adzuna", "jooble", "jsearch", "serpapi"}
    with pytest.raises(ValueError):
        build_sources(HttpClient(cache_dir=None), ["linkedin_scraper"])
