"""Full drive lifecycle: creation -> apply -> shortlist -> rounds -> offer -> accept, with policy rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.campus.lifecycle import deadline_reminders
from app.core.db import SessionLocal
from app.models.campus import Drive
from app.models.user import StudentProfile
from app.services.notify import outbox
from tests.conftest import make_client

JD = """Responsibilities
- Build machine learning models in Python
Requirements
- Python, Machine Learning, SQL
Nice to have
- Docker"""
SOON = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _set_profile(uid: str, **kw) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        p = db.query(StudentProfile).filter(StudentProfile.user_id == uid).one()
        for k, v in kw.items():
            setattr(p, k, v)
        db.commit()


@pytest.fixture(scope="module")
def world(sample_pdfs):  # type: ignore[no-untyped-def]
    tpo, _ = make_client("tpo", institution_name="Lifecycle College")
    code = tpo.get("/tpo/institution").json()["invite_code"]
    people = {}
    for key, pdf, cgpa in [("asha", "uday_ml.pdf", 8.5), ("ben", "meera_data.pdf", 6.0), ("chitra", "priya_fullstack.pdf", 7.8)]:
        c, u = make_client("student", invite_code=code, consent=True)
        assert c.post("/resume/upload", files={"file": (pdf, sample_pdfs[pdf].read_bytes(), "application/pdf")}).status_code == 201
        _set_profile(u["id"], roll_no=key.upper(), branch="CSE", batch_year=2026, cgpa=cgpa, tenth_pct=85, twelfth_pct=80)
        people[key] = (c, u)
    outbox().clear()
    body = {"company": "Nimbus", "role": "ML Engineer", "jd_text": JD, "ctc_lpa": 8.0, "status": "open", "deadline": SOON,
            "rounds": ["Online test", "Interview"], "rules": {"min_cgpa": 7.0}}
    drive = tpo.post("/tpo/drives", json=body).json()
    return tpo, people, drive


def test_new_drive_notifies_eligible_students(world) -> None:  # type: ignore[no-untyped-def]
    tpo, people, drive = world
    asha, ben = people["asha"][0], people["ben"][0]
    n = asha.get("/student/notifications").json()
    assert n["unread"] >= 1 and n["items"][0]["title"] == "New drive: Nimbus" and n["items"][0]["link"] == f"/campus/{drive['id']}"
    assert ben.get("/student/notifications").json()["unread"] == 0  # not eligible (CGPA 6.0)
    assert any(m["subject"] == "SkillMatch: New drive: Nimbus" for m in outbox())
    assert asha.post("/student/notifications/read").json()["marked"] >= 1
    assert asha.get("/student/notifications").json()["unread"] == 0


def test_student_drive_list_and_apply(world) -> None:  # type: ignore[no-untyped-def]
    tpo, people, drive = world
    asha, ben, chitra = (people[k][0] for k in ("asha", "ben", "chitra"))
    cards = asha.get("/student/drives").json()
    card = next(c for c in cards if c["id"] == drive["id"])
    assert card["eligible"] and card["match_percent"] is not None and "Python" in card["matched_skills"] + card["missing_required"]
    assert "rank" not in card  # peer rank never shown to students
    bcard = next(c for c in ben.get("/student/drives").json() if c["id"] == drive["id"])
    assert not bcard["eligible"] and bcard["reasons"] == ["CGPA 6 < 7"]
    r = ben.post(f"/student/drives/{drive['id']}/apply")
    assert r.status_code == 409 and "CGPA 6 < 7" in r.json()["detail"]

    d = asha.post(f"/student/drives/{drive['id']}/apply").json()
    assert d["applied"] and d["stage"] == "Applied" and d["timeline"][0]["stage"] == "Applied"
    assert asha.post(f"/student/drives/{drive['id']}/apply").status_code == 409  # already applied
    assert chitra.post(f"/student/drives/{drive['id']}/apply").status_code == 200
    w = chitra.post(f"/student/drives/{drive['id']}/withdraw").json()
    assert w["stage"] == "Withdrawn" and not w["applied"]
    assert chitra.post(f"/student/drives/{drive['id']}/apply").json()["stage"] == "Applied"  # re-apply before deadline


def test_rounds_results_csv_and_offer_accept(world) -> None:  # type: ignore[no-untyped-def]
    tpo, people, drive = world
    (asha, ua), (chitra, uc) = people["asha"], people["chitra"]
    did = drive["id"]
    assert tpo.post(f"/tpo/drives/{did}/shortlist", json={"mode": "manual", "add": [ua["id"], uc["id"]]}).status_code == 200
    k = tpo.get(f"/tpo/drives/{did}/stages").json()
    assert k["stages"] == ["Applied", "Shortlisted", "Online test", "Interview", "Offer", "Accepted", "Rejected", "Withdrawn"]
    assert {c["roll_no"] for c in k["columns"]["Shortlisted"]} == {"ASHA", "CHITRA"}

    r = tpo.post(f"/tpo/drives/{did}/stages", json={"student_ids": [ua["id"], uc["id"]], "stage": "Online test"}).json()
    assert r["moved"] == 2
    assert tpo.post(f"/tpo/drives/{did}/stages", json={"student_ids": [ua["id"]], "stage": "Offer"}).status_code == 422
    assert tpo.post(f"/tpo/drives/{did}/stages", json={"student_ids": [ua["id"]], "stage": "Lunch"}).status_code == 422

    csv_body = "Roll No,Result\nASHA,Pass\nCHITRA,fail\nNOBODY,pass\n"
    res = tpo.post(f"/tpo/drives/{did}/stages/results", data={"round_name": "Online test"},
                   files={"file": ("results.csv", csv_body.encode(), "text/csv")}).json()
    assert res["passed"] == 1 and res["failed"] == 1 and res["next_stage"] == "Interview" and len(res["problems"]) == 1
    cols = tpo.get(f"/tpo/drives/{did}/stages").json()["columns"]
    assert [c["roll_no"] for c in cols["Interview"]] == ["ASHA"] and [c["roll_no"] for c in cols["Rejected"]] == ["CHITRA"]
    assert any(n["title"] == "Nimbus: Rejected" for n in chitra.get("/student/notifications").json()["items"])

    assert tpo.post("/tpo/offers", json={"drive_id": did, "student_id": uc["id"]}).status_code == 409  # rejected student
    offer = tpo.post("/tpo/offers", json={"drive_id": did, "student_id": ua["id"]}).json()
    assert offer["status"] == "pending" and offer["ctc_lpa"] == 8.0
    assert tpo.post("/tpo/offers", json={"drive_id": did, "student_id": ua["id"]}).status_code == 409  # one per drive
    d = asha.get(f"/student/drives/{did}").json()
    assert d["stage"] == "Offer" and d["offer"]["status"] == "pending"
    assert [t["stage"] for t in d["timeline"]] == ["Applied", "Shortlisted", "Online test", "Interview", "Offer"]
    assert any(n["kind"] == "offer" for n in asha.get("/student/notifications").json()["items"])
    world[1]["offer_id"] = offer["id"]


def test_one_offer_and_dream_rules_then_accept(world) -> None:  # type: ignore[no-untyped-def]
    tpo, people, drive = world
    asha, ua = people["asha"]
    regular = tpo.post("/tpo/drives", json={"company": "Kaveri", "role": "Analyst", "jd_text": JD, "ctc_lpa": 6, "status": "open", "deadline": SOON}).json()
    low_dream = tpo.post("/tpo/drives", json={"company": "Orbit", "role": "DS", "jd_text": JD, "ctc_lpa": 10, "status": "open", "category": "dream", "deadline": SOON}).json()
    dream = tpo.post("/tpo/drives", json={"company": "Lakeview", "role": "DS", "jd_text": JD, "ctc_lpa": 14, "status": "open", "category": "dream", "deadline": SOON}).json()

    # Holding an 8 LPA offer: regular drives are closed to Asha; dream drives need >= 1.5 x 8 = 12 LPA.
    r = asha.post(f"/student/drives/{regular['id']}/apply")
    assert r.status_code == 409 and "One-offer rule" in r.json()["detail"]
    r = asha.post(f"/student/drives/{low_dream['id']}/apply")
    assert r.status_code == 409 and "Dream rule: drive CTC 10 LPA < 1.5 x current offer 8 LPA = 12 LPA" in r.json()["detail"]
    assert asha.post(f"/student/drives/{dream['id']}/apply").status_code == 200

    # The TPO can't record a regular-drive offer for her either.
    chitra_like = people["chitra"][1]
    tpo.post(f"/tpo/drives/{regular['id']}/shortlist", json={"mode": "manual", "add": [chitra_like["id"]]})

    # Accepting ends other campus processes (block after accept).
    out = asha.post(f"/student/offers/{people['offer_id']}/accept").json()
    assert out["stage"] == "Accepted" and out["offer"]["status"] == "accepted"
    dcard = asha.get(f"/student/drives/{dream['id']}").json()
    assert dcard["stage"] == "Withdrawn" and dcard["timeline"][-1]["note"].startswith("Accepted another offer")
    r = asha.post(f"/student/drives/{dream['id']}/apply")
    assert r.status_code == 409 and "Already accepted an offer" in r.json()["detail"]
    assert asha.post(f"/student/offers/{people['offer_id']}/accept").status_code == 409
    roster = {s["roll_no"]: s for s in tpo.get("/tpo/students").json()}
    assert roster["ASHA"]["placed_status"] == "placed"
    offers = tpo.get("/tpo/offers").json()
    assert offers[0]["status"] == "accepted" and offers[0]["roll_no"] == "ASHA"
    assert {a["action"] for a in tpo.get("/tpo/audit").json()["items"]} >= {"offer.create", "offer.accept", "stage.move", "stage.results_upload"}


def test_decline_and_tpo_recorded_decision(world, sample_pdfs) -> None:  # type: ignore[no-untyped-def]
    tpo, people, _ = world
    code = tpo.get("/tpo/institution").json()["invite_code"]
    dev, ud = make_client("student", invite_code=code, consent=True)
    dev.post("/resume/upload", files={"file": ("a.pdf", sample_pdfs["arjun_ece.pdf"].read_bytes(), "application/pdf")})
    _set_profile(ud["id"], roll_no="DEV", branch="ECE", batch_year=2026, cgpa=8.0)
    d = tpo.post("/tpo/drives", json={"company": "Volt", "role": "Firmware", "jd_text": JD, "ctc_lpa": 7, "status": "open", "deadline": SOON, "rounds": []}).json()
    dev.post(f"/student/drives/{d['id']}/apply")
    tpo.post(f"/tpo/drives/{d['id']}/shortlist", json={"mode": "manual", "add": [ud["id"]]})
    o = tpo.post("/tpo/offers", json={"drive_id": d["id"], "student_id": ud["id"], "ctc_lpa": 7.5}).json()
    assert {s["roll_no"]: s for s in tpo.get("/tpo/students").json()}["DEV"]["placed_status"] == "offered"
    declined = tpo.patch(f"/tpo/offers/{o['id']}", json={"status": "declined"}).json()
    assert declined["status"] == "declined"
    assert {s["roll_no"]: s for s in tpo.get("/tpo/students").json()}["DEV"]["placed_status"] == "unplaced"


def test_deadline_withdraw_reminders_and_deletion_block(world) -> None:  # type: ignore[no-untyped-def]
    tpo, people, _ = world
    chitra, uc = people["chitra"]
    soon = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    d = tpo.post("/tpo/drives", json={"company": "Quick", "role": "SDE", "jd_text": JD, "ctc_lpa": 6, "status": "open", "deadline": soon}).json()
    with SessionLocal() as db:
        assert deadline_reminders(db) >= 1
        assert deadline_reminders(db) == 0  # once per drive
    assert any(n["kind"] == "deadline" for n in chitra.get("/student/notifications").json()["items"])

    assert chitra.post(f"/student/drives/{d['id']}/apply").status_code == 200
    r = chitra.delete("/auth/me")
    assert r.status_code == 409 and "active campus drive application" in r.json()["detail"]
    with SessionLocal() as db:  # deadline passes
        db.get(Drive, d["id"]).deadline = datetime.now(timezone.utc) - timedelta(hours=1)  # type: ignore[union-attr]
        db.commit()
    assert chitra.post(f"/student/drives/{d['id']}/withdraw").status_code == 409
    late = tpo.post("/tpo/drives", json={"company": "Late", "role": "SDE", "jd_text": JD, "status": "open",
                                         "deadline": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}).json()
    r = chitra.post(f"/student/drives/{late['id']}/apply")
    assert r.status_code == 409 and "deadline" in r.json()["detail"]
    draft = tpo.post("/tpo/drives", json={"company": "Hidden", "role": "SDE", "jd_text": JD}).json()
    assert chitra.get(f"/student/drives/{draft['id']}").status_code == 404  # drafts are invisible


def test_readiness_and_unified_tracker(world) -> None:  # type: ignore[no-untyped-def]
    _, people, drive = world
    asha, _ = people["asha"]
    r = asha.get("/student/readiness").json()
    assert 0 <= r["score"] <= 1 and r["completeness"] > 0 and 0 < len(r["actions"]) <= 3
    assert {c["label"] for c in r["checks"]["resume"]} >= {"Bullet points", "Quantified results"}
    cid = asha.get("/resume/me").json()["id"]
    jobs = asha.get("/jobs", params={"limit": 1}).json()["items"]
    if jobs:
        asha.post("/applications", json={"candidate_id": cid, "job_id": jobs[0]["id"], "status": "Applied"})
    t = asha.get("/student/tracker").json()
    labels = {x["source_label"] for x in t}
    assert "Campus drive" in labels and (not jobs or "Open market" in labels)
    assert any(x["kind"] == "campus" and x["stage"] == "Accepted" for x in t)


def test_cross_institution_and_roles(world) -> None:  # type: ignore[no-untyped-def]
    tpo, people, drive = world
    other_tpo, _ = make_client("tpo")
    assert other_tpo.get(f"/tpo/drives/{drive['id']}/stages").status_code == 403
    assert other_tpo.post("/tpo/offers", json={"drive_id": drive["id"], "student_id": people["asha"][1]["id"]}).status_code == 403
    outsider, _ = make_client("student", invite_code=other_tpo.get("/tpo/institution").json()["invite_code"], consent=True)
    assert outsider.get(f"/student/drives/{drive['id']}").status_code == 404
    seeker, _ = make_client("job_seeker")
    assert seeker.get("/student/drives").status_code == 403
    assert seeker.get("/student/notifications").status_code == 200  # job seekers have notifications too
    assert people["asha"][0].post(f"/student/offers/{people['offer_id']}/decline").status_code == 409
