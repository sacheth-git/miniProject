from app.core.db import SessionLocal
from app.models.job import Job



def _job(jid: str) -> None:
    with SessionLocal() as db:
        db.merge(Job(id=jid, source="lever", source_job_id=f"t:{jid}", title="Data Analyst", company="Acme",
                     company_norm="acme", description="SQL", location="Pune", apply_url=f"https://e.com/{jid}",
                     apply_options=[], required_skills=[], preferred_skills=[]))
        db.commit()


def test_tracker_lifecycle(sample_pdfs, seeker) -> None:  # type: ignore[no-untyped-def]
    client = seeker
    cid = client.post("/resume/upload", files={"file": ("m.pdf", sample_pdfs["meera_data.pdf"].read_bytes(), "application/pdf")}).json()["id"]
    _job("trk-1")
    r = client.post("/applications", json={"candidate_id": cid, "job_id": "trk-1"})
    assert r.status_code == 201 and r.json()["status"] == "Saved" and r.json()["title"] == "Data Analyst"
    aid = r.json()["id"]
    # Same job again: moves status, no duplicate row.
    r = client.post("/applications", json={"candidate_id": cid, "job_id": "trk-1", "status": "Applied", "applied_via": "LinkedIn"})
    assert r.status_code == 200 and r.json()["id"] == aid and r.json()["applied_at"] and r.json()["applied_via"] == "LinkedIn"
    r = client.patch(f"/applications/{aid}", json={"status": "Interview", "notes": "Round 1 on Monday"})
    body = r.json()
    assert [h["status"] for h in body["status_history"]] == ["Saved", "Applied", "Interview"]
    assert body["notes"] == "Round 1 on Monday" and body["job_active"] is True
    assert len(client.get("/applications", params={"candidate_id": cid}).json()) == 1
    assert client.patch(f"/applications/{aid}", json={"status": "Hired!"}).status_code == 422
    assert client.post("/applications", json={"candidate_id": cid, "job_id": "nope"}).status_code == 404
    assert client.delete(f"/applications/{aid}").status_code == 204
    assert client.get("/applications", params={"candidate_id": cid}).json() == []
    assert client.get("/applications/statuses").json()[0] == "Saved"


def test_bias_toggle_reprocesses(sample_pdfs, seeker) -> None:  # type: ignore[no-untyped-def]
    client = seeker
    cid = client.post("/resume/upload", files={"file": ("u.pdf", sample_pdfs["uday_ml.pdf"].read_bytes(), "application/pdf")}).json()["id"]
    client.put(f"/resume/{cid}/skills", json={"add": ["Kubernetes"]})
    off = client.put(f"/resume/{cid}/settings", json={"bias_aware": False}).json()
    assert off["bias_aware"] is False and off["masked_text"] is None
    assert "Uday" in off["sections"]["header"]
    assert "Kubernetes" in {s["name"] for s in off["skills"]}  # user-added skill kept
    on = client.put(f"/resume/{cid}/settings", json={"bias_aware": True}).json()
    assert "Uday" not in (on["masked_text"] or "")
    client.delete(f"/resume/{cid}")
