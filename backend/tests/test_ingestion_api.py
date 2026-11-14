"""End to end: mocked sources -> pipeline -> DB -> /jobs, /admin, /import, /deeplinks."""

from __future__ import annotations

from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.ingestion import pipeline
from app.ingestion.http import HttpClient
from app.ingestion.sources import ashby, greenhouse, lever
from app.ingestion.sources.ats import Board
from app.ingestion.user_import import clean_job_url, parse_alert_email
from app.main import app
from tests.fakes import FakeEncoder, routed_transport
from tests.test_sources import ASHBY, GREENHOUSE, LEVER, REMOTIVE

client = TestClient(app)


@pytest.fixture()
def ingested(monkeypatch: pytest.MonkeyPatch, phrase_extractor):  # type: ignore[no-untyped-def]
    s = get_settings()
    for attr in ("adzuna_app_id", "adzuna_app_key", "jooble_key", "rapidapi_key", "serpapi_key"):
        monkeypatch.setattr(s, attr, None)
    boards = {a: [Board("acme", a, "Acme")] for a in ("greenhouse", "lever", "ashby")}
    for mod in (greenhouse, lever, ashby):
        monkeypatch.setattr(mod, "boards_for", lambda ats: boards[ats])
    gh = {"jobs": [*GREENHOUSE["jobs"], {**GREENHOUSE["jobs"][0], "id": 13, "title": "Senior Backend Engineer",
                                         "location": {"name": "Remote"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/13"}]}
    http = HttpClient(cache_dir=None, min_interval=0, retries=0, transport=routed_transport({
        "boards-api.greenhouse.io": gh, "api.lever.co": LEVER, "api.ashbyhq.com": ASHBY, "remotive.com": REMOTIVE,
    }))
    with SessionLocal() as db:
        report = pipeline.run_ingestion(db, http=http, extractor=phrase_extractor, encoder=FakeEncoder())
    http.close()
    return report


def test_pipeline_and_status(ingested, admin_client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/admin/sources/status").status_code == 401  # admin only
    runs = {r.source: r for r in ingested.runs}
    assert runs["greenhouse"].created == 2 and runs["lever"].created == 1 and runs["ashby"].created == 1
    assert runs["jsearch"].status == "skipped"
    st = admin_client.get("/admin/sources/status").json()
    by = {s["source"]: s for s in st["sources"]}
    assert by["greenhouse"]["active_jobs"] == 2 and by["greenhouse"]["last_status"] == "ok"
    assert by["jsearch"]["configured"] is False and by["jsearch"]["last_status"] == "skipped"
    assert st["total_active"] >= 5


def test_jobs_listing_filters(ingested) -> None:  # type: ignore[no-untyped-def]
    page = client.get("/jobs", params={"limit": 50}).json()
    assert page["total"] >= 5
    gh = next(j for j in page["items"] if j["title"] == "Backend Engineer")
    assert {s["name"] for s in gh["required_skills"]} >= {"Python", "Apache Kafka"}
    assert client.get("/jobs", params={"type": "internship"}).json()["total"] == 1
    assert client.get("/jobs", params={"remote": True, "source": "greenhouse"}).json()["total"] == 1
    hits = client.get("/jobs", params={"location": "india", "role": "backend"}).json()["items"]
    assert len(hits) == 1, [(h["title"], h["location"], h["country"]) for h in hits]
    # Unknown experience passes any filter; the senior role (min 4 yrs) is excluded by max_exp=1.
    assert client.get("/jobs", params={"max_exp": 1, "source": "greenhouse"}).json()["total"] == 1
    assert client.get("/jobs", params={"min_exp": 3, "source": "greenhouse"}).json()["total"] == 2
    assert client.get("/jobs", params={"type": "gig"}).status_code == 422
    detail = client.get(f"/jobs/{gh['id']}").json()
    assert "Python and Kafka" in detail["description"]
    assert client.get("/jobs/nope").status_code == 404


def test_reingest_deactivates_closed_jobs(ingested, monkeypatch: pytest.MonkeyPatch, phrase_extractor) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(greenhouse, "boards_for", lambda ats: [Board("acme", "greenhouse", "Acme")])
    http = HttpClient(cache_dir=None, min_interval=0, retries=0,
                      transport=routed_transport({"boards-api.greenhouse.io": GREENHOUSE}))
    with SessionLocal() as db:
        rep = pipeline.run_ingestion(db, ["greenhouse"], http=http, extractor=phrase_extractor, encoder=FakeEncoder())
    http.close()
    assert rep.runs[0].deactivated == 1  # job 13 vanished from the feed


def test_import_text_is_private_and_deleted_with_candidate(sample_pdfs, seeker) -> None:  # type: ignore[no-untyped-def]
    owner, guest = seeker, client
    cid = owner.post("/resume/upload", files={"file": ("u.pdf", sample_pdfs["uday_ml.pdf"].read_bytes(), "application/pdf")}).json()["id"]
    body = {"text": "We need a Python developer with Django and PostgreSQL skills.\nMust know Docker.",
            "url": "https://careers.example.com/jobs/42?utm_source=x", "title": "Python Developer",
            "company": "Example Co", "candidate_id": cid}
    r = owner.post("/import/text", json=body)
    assert r.status_code == 201, r.text
    job = r.json()["jobs"][0]
    assert {"Python", "Django", "PostgreSQL", "Docker"} <= {s["name"] for s in job["required_skills"]}
    ids_public = {j["id"] for j in guest.get("/jobs", params={"limit": 100}).json()["items"]}
    ids_owner = {j["id"] for j in owner.get("/jobs", params={"limit": 100, "candidate_id": cid}).json()["items"]}
    ids_spoof = {j["id"] for j in guest.get("/jobs", params={"limit": 100, "candidate_id": cid}).json()["items"]}
    assert job["id"] not in ids_spoof  # knowing the id is not enough
    assert guest.get(f"/jobs/{job['id']}").status_code == 404
    assert job["id"] not in ids_public and job["id"] in ids_owner

    links = owner.get(f"/deeplinks/{cid}").json()
    assert links["role"] == "Machine Learning Engineer"
    platforms = {link["platform"] for link in links["links"]}
    assert platforms == {"LinkedIn", "Naukri", "Indeed"}
    assert all(link["url"].startswith("https://") for link in links["links"])

    assert owner.delete(f"/resume/{cid}").status_code == 204
    assert owner.get(f"/jobs/{job['id']}").status_code == 404
    assert owner.get(f"/deeplinks/{cid}").status_code == 404


def _alert_email() -> bytes:
    msg = EmailMessage()
    msg["Subject"] = "Your job alert"
    msg["From"] = "jobs-noreply@linkedin.com"
    msg.set_content("plain fallback")
    msg.add_alternative(
        """<html><body>
        <a href="https://www.linkedin.com/comm/jobs/view/3912345678/?trackingId=abc&refId=x">Machine Learning Engineer</a>
        <p>Nimbus Analytics</p><p>Bengaluru</p>
        <a href="https://www.naukri.com/job-listings-data-analyst-acme-pune-1-3-years-0710?src=alert">Data Analyst</a>
        <span>Acme</span>
        <a href="https://www.linkedin.com/comm/psettings/email">Unsubscribe</a>
        <a href="https://www.linkedin.com/comm/jobs/view/3912345678/?trackingId=dup">Machine Learning Engineer</a>
        </body></html>""",
        subtype="html",
    )
    return bytes(msg)


def test_parse_alert_email() -> None:
    jobs = parse_alert_email(_alert_email())
    assert [(j.title, j.publisher) for j in jobs] == [("Machine Learning Engineer", "LinkedIn"), ("Data Analyst", "Naukri")]
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/3912345678/"
    assert jobs[0].company == "Nimbus Analytics"
    assert clean_job_url("https://in.indeed.com/rc/clk?jk=0123abcd4567&from=x") == "https://in.indeed.com/viewjob?jk=0123abcd4567"
    assert clean_job_url("https://acme.com/careers/1?utm_source=a&id=7") == "https://acme.com/careers/1?id=7"
    assert clean_job_url("mailto:x@y.z") is None


def test_import_email_endpoint(sample_pdfs, seeker) -> None:  # type: ignore[no-untyped-def]
    assert seeker.post("/import/email", files=[("files", ("a.eml", _alert_email(), "message/rfc822"))]).status_code == 409
    seeker.post("/resume/upload", files={"file": ("u.pdf", sample_pdfs["uday_ml.pdf"].read_bytes(), "application/pdf")})
    files = [("files", ("alert.eml", _alert_email(), "message/rfc822")), ("files", ("junk.eml", b"not an email", "message/rfc822"))]
    r = seeker.post("/import/email", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 2
    assert body["jobs"][0]["apply_options"][0]["publisher"] == "LinkedIn"
    assert any("junk.eml" in s for s in body["skipped_files"])


def test_admin_ingest_validates(admin_client, seeker) -> None:  # type: ignore[no-untyped-def]
    assert seeker.post("/admin/ingest", json={"sources": ["greenhouse"]}).status_code == 403
    assert admin_client.post("/admin/ingest", json={"sources": ["linkedin_scraper"]}).status_code == 422
