"""Placement analytics, skill-gap heatmap, fairness and recruiter share links."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.campus.lifecycle import decide_offer, move_stage, record_offer
from app.core.db import SessionLocal
from app.main import app
from app.models.campus import Drive, DriveApplication
from app.models.candidate import Candidate
from app.models.share import ShareLink
from app.models.user import StudentProfile, User
from app.skills.taxonomy import get_taxonomy
from tests.conftest import make_client

JD = "Requirements\n- Python, SQL, Docker\nNice to have\n- Git"


def _student(db, inst: str, i: int, branch: str, gender: str, skills: list[str], consent: bool = True) -> User:  # type: ignore[no-untyped-def]
    u = User(email=f"an{i}-{inst[:6]}@t.example", password_hash="x", full_name=f"Student {i}", role="student", institution_id=inst)
    db.add(u)
    db.flush()
    db.add(StudentProfile(user_id=u.id, institution_id=inst, roll_no=f"R{i:03d}", branch=branch, batch_year=2026, cgpa=8.0,
                          gender=gender, consent_given_at=datetime.now(timezone.utc) if consent else None))
    tax = get_taxonomy()
    sk = [{"skill_id": tax.lookup(s).id, "name": tax.lookup(s).name, "confidence": 0.95, "evidence": f"used {s}",  # type: ignore[union-attr]
           "section": "skills", "method": "phrase", "mentions": 1} for s in skills]
    text = f"Skills: {', '.join(skills)}. Built projects with {' and '.join(skills)}."
    db.add(Candidate(user_id=u.id, filename="r.pdf", raw_text=text, masked_text=text, sections={"skills": text, "projects": text},
                     skills=sk, years_experience=0.0, education_level="bachelors", education_rank=3, bias_aware=True, pages=1))
    return u


@pytest.fixture(scope="module")
def campus():  # type: ignore[no-untyped-def]
    tpo_client, tpo_user = make_client("tpo", institution_name="Analytics College")
    inst = tpo_user["institution_id"]
    with SessionLocal() as db:
        users = []
        for i in range(24):  # 12 female, 12 male; CSE knows Python+SQL, half know Docker; ECE knows SQL only
            branch = "CSE" if i < 16 else "ECE"
            skills = (["Python", "SQL"] + (["Docker"] if i % 2 == 0 else [])) if branch == "CSE" else ["SQL"]
            users.append(_student(db, inst, i, branch, "female" if i % 2 else "male", skills))
        _student(db, inst, 99, "CSE", "male", ["Python"], consent=False)  # never in resume-derived stats
        db.commit()
        ids = [u.id for u in users]
    d = tpo_client.post("/tpo/drives", json={"company": "Acme", "role": "Backend", "jd_text": JD, "ctc_lpa": 8, "status": "open",
                                             "rounds": ["Interview"], "deadline": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()}).json()
    # Shortlist the top 6 (system ranking), make 2 offers, 1 accepted.
    r = tpo_client.post(f"/tpo/drives/{d['id']}/shortlist", json={"mode": "top", "n": 6}).json()
    chosen = [x["user_id"] for x in r["rows"] if x["shortlisted"]]
    with SessionLocal() as db:
        tpo = db.get(User, tpo_user["id"])
        drive = db.get(Drive, d["id"])
        for uid in chosen[:2]:
            app_ = db.query(DriveApplication).filter_by(drive_id=drive.id, student_id=uid).one()
            move_stage(db, tpo, drive, app_, "Interview")
            record_offer(db, tpo, drive, uid, 8.0)
        db.commit()
        o = db.query(__import__("app.models.campus", fromlist=["Offer"]).Offer).filter_by(student_id=chosen[0]).one()
        decide_offer(db, db.get(User, chosen[0]), o, True)
        db.commit()
    return tpo_client, d, ids, chosen


def test_summary_kpis_and_funnel(campus) -> None:  # type: ignore[no-untyped-def]
    tpo, d, ids, chosen = campus
    s = tpo.get("/tpo/analytics/summary").json()
    assert s["students"] == 25 and s["placed"] == 1 and s["offered"] == 1
    assert s["ctc"] == {"count": 1, "highest": 8.0, "median": 8.0, "average": 8.0}
    assert {r["branch"]: r["students"] for r in s["by_branch"]} == {"CSE": 17, "ECE": 8}
    assert s["companies"] == [{"company": "Acme", "offers": 2, "accepted": 1, "avg_ctc": 8.0}]
    f = s["funnel"]["drives"][0]
    assert (f["eligible"], f["shortlisted"], f["offered"], f["accepted"]) == (24, 6, 2, 1)  # consent-less student excluded
    assert s["funnel"]["total"]["accepted"] == 1


def test_skill_gap_heatmap_and_recommendations(campus) -> None:  # type: ignore[no-untyped-def]
    tpo, *_ = campus
    g = tpo.get("/tpo/analytics/skill-gap").json()
    assert {s["name"] for s in g["skills"]} >= {"Python", "SQL", "Docker"}
    assert "Git" not in {s["name"] for s in g["skills"]}  # preferred skills are not "demanded"
    cell = {(c["branch"], c["skill"]): c for c in g["cells"]}
    assert cell[("CSE", "Python")]["missing_pct"] == 0 and cell[("CSE", "Docker")]["missing_pct"] == 50
    assert cell[("ECE", "Python")]["missing_pct"] == 100 and cell[("ECE", "SQL")]["missing_pct"] == 0
    assert cell[("CSE", "Python")]["students"] == 16  # the student without consent is excluded
    texts = [r["text"] for r in g["recommendations"]]
    assert "100% of ECE students lack Python, required by 1 drive" in texts
    assert "50% of CSE students lack Docker, required by 1 drive" in texts


def test_unplaced_with_best_fit(campus) -> None:  # type: ignore[no-untyped-def]
    tpo, d, ids, chosen = campus
    u = tpo.get("/tpo/analytics/unplaced").json()
    roll = {x["roll_no"] for x in u}
    assert len(u) == 22 and "R099" not in roll  # 24 - placed - offered; no consent excluded
    with_fit = [x for x in u if x["best_drives"]]
    assert with_fit and with_fit[0]["best_drives"][0]["company"] == "Acme"
    assert all(x["user_id"] not in chosen[:2] for x in u)


def test_fairness_with_suppression(campus) -> None:  # type: ignore[no-untyped-def]
    tpo, *_ = campus
    f = tpo.get("/tpo/analytics/fairness").json()
    assert f["drives_used"] == 1 and f["min_group"] == 10
    g = {r["group"]: r for r in f["gender"]["rows"]}
    assert g["female"]["eligible"] == 12 and g["male"]["eligible"] == 12
    assert g["female"]["system_rate"] + g["male"]["system_rate"] == pytest.approx(100 * 6 / 12)
    b = {r["group"]: r for r in f["branch"]["rows"]}
    assert b["ECE"]["suppressed"] and b["ECE"]["system_rate"] is None  # 8 < 10
    assert not b["CSE"]["suppressed"]
    assert f["gender"]["system_parity"] is not None and "blind and named" in f["note"]


def test_share_link_lifecycle(campus) -> None:  # type: ignore[no-untyped-def]
    tpo, d, *_ = campus
    anon = TestClient(app)
    link = tpo.post(f"/tpo/drives/{d['id']}/share-link", json={"expires_in_days": 3, "blind": True, "label": "Acme HR"}).json()
    token = link["token"]
    with SessionLocal() as db:
        row = db.get(ShareLink, link["id"])
        assert row.token_hash != token and token not in str(row.as_dict())  # only the hash is stored
    view = anon.get(f"/share/{token}").json()
    assert view["company"] == "Acme" and view["blind"] and len(view["rows"]) == 6
    assert all("name" not in r and "email" not in r for r in view["rows"])
    assert {c["key"] for c in view["columns"]} >= {"rank", "roll_no", "match_percent"}
    named = tpo.post(f"/tpo/drives/{d['id']}/share-link", json={"blind": False, "columns": ["rank", "name", "match_percent"]}).json()
    assert anon.get(f"/share/{named['token']}").json()["rows"][0]["name"].startswith("Student ")
    links = tpo.get(f"/tpo/drives/{d['id']}/share-links").json()
    assert links[-1]["views"] == 1 and "token" not in links[-1]

    other, _ = make_client("tpo")
    assert other.post(f"/tpo/drives/{d['id']}/share-link", json={}).status_code == 403
    assert other.delete(f"/tpo/share-links/{link['id']}").status_code == 403
    assert tpo.delete(f"/tpo/share-links/{link['id']}").status_code == 204
    assert anon.get(f"/share/{token}").status_code == 410
    with SessionLocal() as db:
        db.get(ShareLink, named["id"]).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)  # type: ignore[union-attr]
        db.commit()
    assert anon.get(f"/share/{named['token']}").status_code == 410
    assert anon.get("/share/not-a-token").status_code == 404
    assert {a["action"] for a in tpo.get("/tpo/audit").json()["items"]} >= {"share.create", "share.revoke"}


def test_unplaced_jobs_requires_consent(campus) -> None:  # type: ignore[no-untyped-def]
    tpo, d, ids, _ = campus
    with SessionLocal() as db:
        no_consent = db.query(StudentProfile).filter_by(roll_no="R099").one().user_id
    assert tpo.get(f"/tpo/analytics/unplaced/{no_consent}/jobs").status_code == 403
    assert tpo.get(f"/tpo/analytics/unplaced/{ids[5]}/jobs").status_code == 200
    other, _ = make_client("tpo")
    assert other.get(f"/tpo/analytics/unplaced/{ids[5]}/jobs").status_code == 403
    assert other.get("/tpo/analytics/summary").json()["students"] == 0
