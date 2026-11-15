"""TPO workflow end to end: bulk import -> drive -> eligibility -> ranked shortlist -> export -> audit."""

from __future__ import annotations

import csv
import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.core.db import SessionLocal
from app.main import app
from app.models.user import StudentProfile, User
from tests.conftest import make_client

JD = """Machine Learning Engineer (campus hire)
Responsibilities
- Build and deploy machine learning models in Python
- Work with SQL data pipelines
Requirements
- Python, Machine Learning, SQL
- Deep Learning with PyTorch or TensorFlow
Nice to have
- Docker, NLP
"""


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Roll No", "Name", "Email", "Branch", "Batch", "CGPA", "Backlogs", "10th", "12th", "Gender"])
    w.writerows(rows)
    return buf.getvalue().encode()


@pytest.fixture(scope="module")
def campus(sample_pdfs):  # type: ignore[no-untyped-def]
    tpo, tpo_user = make_client("tpo", institution_name="Demo Institute of Technology")
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("resumes/1DI22CS001.pdf", sample_pdfs["uday_ml.pdf"].read_bytes())  # ML profile
        zf.writestr("1DI22CS002.pdf", sample_pdfs["meera_data.pdf"].read_bytes())  # data analyst
        zf.writestr("1DI22ME003.pdf", sample_pdfs["rahul_mech.pdf"].read_bytes())  # mechanical
        zf.writestr("1DI22EC004.pdf", sample_pdfs["arjun_ece.pdf"].read_bytes())  # embedded
        zf.writestr("notes.txt", "ignored")
    rows = [
        ["1DI22CS001", "Aarav Rao", "aarav@demo.edu", "CSE", "2026", "8.6", "0", "91", "88", "male"],
        ["1DI22CS002", "Diya Iyer", "diya@demo.edu", "CSE", "2026", "7.9", "0", "89", "85", "female"],
        ["1DI22ME003", "Kabir Shetty", "kabir@demo.edu", "MECH", "2026", "7.2", "0", "80", "78", "male"],
        ["1DI22EC004", "Isha Nair", "isha@demo.edu", "ECE", "2026", "6.4", "1", "75", "70", "female"],
        ["1DI22CS005", "No Resume", "nores@demo.edu", "CSE", "2026", "7.5", "0", "80", "80", ""],
        ["1DI22CS006", "Bad Cgpa", "bad@demo.edu", "CSE", "2026", "11.2", "0", "80", "80", ""],
        ["1DI22CS001", "Dup Roll", "dup@demo.edu", "CSE", "2026", "8.0", "0", "80", "80", ""],
        ["1DI22CS007", "Bad Email", "not-an-email", "CSE", "2026", "8.0", "0", "80", "80", ""],
    ]
    files = {"csv_file": ("students.csv", _csv(rows), "text/csv"), "resumes_zip": ("r.zip", zbuf.getvalue(), "application/zip")}
    preview = tpo.post("/tpo/students/import/preview", files=files)
    assert preview.status_code == 200, preview.text
    return tpo, tpo_user, preview.json()


def test_import_preview_flags_problems(campus) -> None:  # type: ignore[no-untyped-def]
    _, _, p = campus
    by_roll = {}
    for r in p["rows"]:
        by_roll.setdefault(r["roll_no"], []).append(r)
    assert p["total"] == 8 and p["errors"] == 3 and p["warnings"] == 1 and p["ok"] == 4
    assert by_roll["1DI22CS005"][0]["status"] == "warning" and "No resume" in by_roll["1DI22CS005"][0]["warnings"][0]
    assert "CGPA 11.2 is outside 0-10" in by_roll["1DI22CS006"][0]["errors"]
    assert "Duplicate roll number (also on line 2)" in by_roll["1DI22CS001"][1]["errors"]
    assert any("Email" in e for e in by_roll["1DI22CS007"][0]["errors"])
    assert p["with_resume"] == 4 and p["creates"] == 5


def test_import_rejects_bad_files() -> None:
    tpo, _ = make_client("tpo")
    r = tpo.post("/tpo/students/import/preview", files={"csv_file": ("s.csv", b"name,email\nA,a@x.com\n", "text/csv")})
    assert r.status_code == 422 and "missing column" in r.json()["detail"]
    r = tpo.post("/tpo/students/import/preview", files={"csv_file": ("s.csv", _csv([["R1", "A", "a@x.com", "CSE", "2026", "8", "0", "80", "80", ""]]), "text/csv"),
                                                         "resumes_zip": ("r.zip", b"not a zip", "application/zip")})
    assert r.status_code == 422 and "ZIP" in r.json()["detail"]


@pytest.fixture(scope="module")
def imported(campus):  # type: ignore[no-untyped-def]
    tpo, tpo_user, p = campus
    r = tpo.post(f"/tpo/students/import/{p['job_id']}/commit")
    assert r.status_code == 202, r.text
    for _ in range(240):
        st = tpo.get(f"/tpo/students/import/{p['job_id']}").json()
        if st["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert st["status"] == "done", st
    # Students sign in and agree (simulated): consent given for all but one.
    with SessionLocal() as db:
        for prof in db.query(StudentProfile).filter(StudentProfile.institution_id == tpo_user["institution_id"]):
            if prof.roll_no != "1DI22CS005":
                from datetime import datetime, timezone

                prof.consent_given_at = datetime.now(timezone.utc)
        db.commit()
    return tpo, tpo_user, p, st


def test_commit_creates_accounts_and_credentials(imported) -> None:  # type: ignore[no-untyped-def]
    tpo, _, p, st = imported
    assert st["created"] == 5 and st["resumes_parsed"] == 4 and st["errors"] == [] and st["credentials_available"]
    assert tpo.post(f"/tpo/students/import/{p['job_id']}/commit").status_code == 409  # can't run twice
    creds = tpo.get(f"/tpo/students/import/{p['job_id']}/credentials")
    assert creds.status_code == 200
    rows = list(csv.DictReader(io.StringIO(creds.content.decode("utf-8-sig"))))
    assert {r["roll_no"] for r in rows} == {"1DI22CS001", "1DI22CS002", "1DI22ME003", "1DI22EC004", "1DI22CS005"}
    assert tpo.get(f"/tpo/students/import/{p['job_id']}/credentials").status_code == 410  # shown once
    # New accounts must reset their temporary password.
    login = TestClient(app).post("/auth/login", json={"email": rows[0]["email"], "password": rows[0]["temporary_password"]}).json()
    assert login["user"]["must_reset_password"] is True and login["user"]["role"] == "student"
    roster = tpo.get("/tpo/students").json()
    assert len(roster) == 5 and sum(r["has_resume"] for r in roster) == 4
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "kabir@demo.edu").one()
        assert u.must_reset_password


@pytest.fixture(scope="module")
def drive(imported):  # type: ignore[no-untyped-def]
    tpo, *_ = imported
    body = {"company": "Nimbus Analytics", "role": "ML Engineer", "job_type": "fte", "jd_text": JD, "ctc_lpa": 9.5,
            "location": "Bengaluru", "rounds": ["Online test", "Technical interview", "HR"], "category": "regular",
            "status": "open", "rules": {"allowed_branches": ["CSE", "ECE", "MECH"], "min_cgpa": 7.0, "max_active_backlogs": 0}}
    r = tpo.post("/tpo/drives", json=body)
    assert r.status_code == 201, r.text
    return tpo, r.json()


def test_drive_skills_auto_extracted(drive) -> None:  # type: ignore[no-untyped-def]
    _, d = drive
    names = {s["name"]: s for s in d["skills"]}
    assert {"Python", "Machine Learning", "SQL", "PyTorch"} <= set(names)
    assert names["Python"]["type"] == "required" and names["Docker"]["type"] == "preferred"
    assert 0.5 <= names["Python"]["weight"] <= 1.5 and names["Docker"]["weight"] <= 0.75


def test_eligibility_with_reasons(drive) -> None:  # type: ignore[no-untyped-def]
    tpo, d = drive
    e = tpo.get(f"/tpo/drives/{d['id']}/eligibility").json()
    by = {s["roll_no"]: s for s in e["students"]}
    assert by["1DI22CS001"]["eligible"] and by["1DI22CS002"]["eligible"] and by["1DI22ME003"]["eligible"]
    assert set(by["1DI22EC004"]["reasons"]) == {"CGPA 6.4 < 7", "Active backlogs 1 > 0"}
    assert by["1DI22CS005"]["reasons"][0].startswith("Consent pending")
    assert e["eligible"] == 3 and e["total"] == 5
    # Tightening the rules is audited and re-evaluated.
    r = tpo.put(f"/tpo/drives/{d['id']}/eligibility", json={"allowed_branches": ["CSE", "ECE", "MECH"], "min_cgpa": 7.5, "max_active_backlogs": 0}).json()
    assert {s["roll_no"]: s["reasons"] for s in r["students"]}["1DI22ME003"] == ["CGPA 7.2 < 7.5"]
    tpo.put(f"/tpo/drives/{d['id']}/eligibility", json={"allowed_branches": ["CSE", "ECE", "MECH"], "min_cgpa": 7.0, "max_active_backlogs": 0})


def test_ranked_shortlist_blind_and_selection(drive) -> None:  # type: ignore[no-untyped-def]
    tpo, d = drive
    sl = tpo.get(f"/tpo/drives/{d['id']}/shortlist").json()
    assert sl["blind"] is True and "officer makes every shortlist decision" in sl["note"]
    rows = sl["rows"]
    assert [r["roll_no"] for r in rows][0] == "1DI22CS001"  # the ML resume ranks first for an ML drive
    assert rows[-1]["roll_no"] == "1DI22ME003"  # mechanical profile last
    assert all(r["name"] is None and r["email"] is None for r in rows)
    # Top-3 by weight x similarity: rare skills (PyTorch, ML) outrank common ones (Python).
    assert {"Machine Learning", "PyTorch"} & set(rows[0]["matched_skills"])
    assert rows[0]["match_percent"] > rows[-1]["match_percent"]
    assert "gender" not in rows[0] and "candidate_id" not in rows[0]
    named = tpo.get(f"/tpo/drives/{d['id']}/shortlist", params={"blind": False}).json()["rows"]
    assert named[0]["name"] == "Aarav Rao"

    r = tpo.post(f"/tpo/drives/{d['id']}/shortlist", json={"mode": "top", "n": 2}).json()
    assert r["changed"] == 2 and r["shortlisted"] == 2
    ids = [x["user_id"] for x in r["rows"]]
    r = tpo.post(f"/tpo/drives/{d['id']}/shortlist", json={"mode": "manual", "remove": [ids[1]], "add": [ids[2]]}).json()
    assert {x["roll_no"] for x in r["rows"] if x["shortlisted"]} == {"1DI22CS001", "1DI22ME003"}
    ineligible = next(s["user_id"] for s in tpo.get(f"/tpo/drives/{d['id']}/eligibility").json()["students"] if not s["eligible"])
    bad = tpo.post(f"/tpo/drives/{d['id']}/shortlist", json={"mode": "manual", "add": [ineligible]})
    assert bad.status_code == 422
    assert tpo.post(f"/tpo/drives/{d['id']}/shortlist", json={"mode": "top"}).status_code == 422

    ex = tpo.get(f"/tpo/drives/{d['id']}/students/{ids[0]}/explain").json()
    assert ex["rank"] == 1 and ex["name"] is None and ex["explanation"]["summary"].startswith("Matches ")

    audit = tpo.get("/tpo/audit", params={"action": "shortlist"}).json()
    actions = [a["action"] for a in audit["items"]]
    assert actions.count("shortlist.add") == 3 and actions.count("shortlist.remove") == 1
    assert audit["items"][0]["actor_email"].endswith("@test.example")


def test_exports(drive) -> None:  # type: ignore[no-untyped-def]
    tpo, d = drive
    x = tpo.get(f"/tpo/drives/{d['id']}/shortlist/export", params={"format": "xlsx"})
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    ws = load_workbook(io.BytesIO(x.content)).active
    header = [c.value for c in ws[4]]
    assert header[:3] == ["Rank", "Roll no.", "Name"] and ws.max_row == 6  # 3 title rows + header + 2 students
    c = tpo.get(f"/tpo/drives/{d['id']}/shortlist/export", params={"format": "csv", "blind": True, "columns": "rank,roll_no,name,match_percent"})
    lines = c.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "Rank,Roll no.,Match %" and len(lines) == 3  # name dropped in blind mode
    pdf = tpo.get(f"/tpo/drives/{d['id']}/shortlist/export", params={"format": "pdf"})
    assert pdf.content.startswith(b"%PDF")
    z = tpo.get(f"/tpo/drives/{d['id']}/shortlist/export", params={"format": "zip", "blind": True})
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert len(names) == 2 and all(n.endswith(".pdf") and "Aarav" not in n for n in names)
    ranked = tpo.get(f"/tpo/drives/{d['id']}/shortlist/export", params={"format": "csv", "scope": "ranked"})
    assert len(ranked.content.decode("utf-8-sig").splitlines()) == 4
    assert any(a["action"] == "shortlist.export" for a in tpo.get("/tpo/audit").json()["items"])


def test_skill_weight_edits_change_scores(drive) -> None:  # type: ignore[no-untyped-def]
    tpo, d = drive
    before = {r["roll_no"]: r["match_percent"] for r in tpo.get(f"/tpo/drives/{d['id']}/shortlist").json()["rows"]}
    skills = [dict(s, weight=0.0) if s["name"] != "Embedded Systems" else s for s in d["skills"]]
    skills.append({"skill_id": "solidworks", "name": "SolidWorks", "type": "required", "weight": 3.0})
    r = tpo.put(f"/tpo/drives/{d['id']}", json={"skills": skills})
    assert r.status_code == 200
    after = {r["roll_no"]: r["match_percent"] for r in tpo.get(f"/tpo/drives/{d['id']}/shortlist").json()["rows"]}
    assert after["1DI22ME003"] > before["1DI22ME003"]  # the SolidWorks student gains
    assert after["1DI22CS001"] < before["1DI22CS001"]
    assert tpo.get("/tpo/audit", params={"action": "drive.skills"}).json()["total"] == 1
    tpo.put(f"/tpo/drives/{d['id']}", json={"skills": d["skills"]})


def test_cross_institution_isolation(drive) -> None:  # type: ignore[no-untyped-def]
    tpo, d = drive
    other, _ = make_client("tpo")
    for path in [f"/tpo/drives/{d['id']}", f"/tpo/drives/{d['id']}/eligibility", f"/tpo/drives/{d['id']}/shortlist",
                 f"/tpo/drives/{d['id']}/shortlist/export"]:
        assert other.get(path).status_code == 403, path
    assert other.get("/tpo/drives").json() == []
    assert other.get("/tpo/audit").json()["total"] == 0
    stu, _ = make_client("job_seeker")
    assert stu.get(f"/tpo/drives/{d['id']}").status_code == 403


def test_policy_and_dream_drive(drive) -> None:  # type: ignore[no-untyped-def]
    tpo, d = drive
    assert tpo.get("/tpo/settings/policy").json()["dream_multiplier"] == 1.5
    with SessionLocal() as db:
        prof = db.query(StudentProfile).filter(StudentProfile.roll_no == "1DI22CS002").one()
        prof.placed_status, prof.current_best_offer_ctc = "offered", 6.0
        db.commit()
    dream = tpo.post("/tpo/drives", json={"company": "Orbit", "role": "Data Scientist", "jd_text": JD, "ctc_lpa": 8.0,
                                          "category": "dream"}).json()
    reasons = {s["roll_no"]: s["reasons"] for s in tpo.get(f"/tpo/drives/{dream['id']}/eligibility").json()["students"]}
    assert reasons["1DI22CS002"] == ["Dream rule: drive CTC 8 LPA < 1.5 x current offer 6 LPA = 9 LPA"]
    assert tpo.put("/tpo/settings/policy", json={"one_offer_rule": True, "dream_multiplier": 1.2, "block_after_accept": True}).status_code == 200
    reasons = {s["roll_no"]: s["reasons"] for s in tpo.get(f"/tpo/drives/{dream['id']}/eligibility").json()["students"]}
    assert reasons["1DI22CS002"] == []  # 8 >= 1.2 x 6
    regular = {s["roll_no"]: s["reasons"] for s in tpo.get(f"/tpo/drives/{d['id']}/eligibility").json()["students"]}
    assert regular["1DI22CS002"] == ["One-offer rule: already holds an offer (only dream drives allowed)"]
    assert tpo.get("/tpo/audit", params={"action": "policy"}).json()["total"] == 1
    # Only drafts can be deleted.
    assert tpo.delete(f"/tpo/drives/{d['id']}").status_code == 409


def test_extract_jd_from_upload(sample_pdfs) -> None:  # type: ignore[no-untyped-def]
    tpo, _ = make_client("tpo")
    r = tpo.post("/tpo/drives/extract-jd", files={"file": ("jd.txt", JD.encode(), "text/plain")})
    assert r.status_code == 200 and {"Python", "SQL"} <= {s["name"] for s in r.json()["skills"]}
    r = tpo.post("/tpo/drives/extract-jd", files={"file": ("jd.pdf", sample_pdfs["uday_ml.pdf"].read_bytes(), "application/pdf")})
    assert r.status_code == 200 and "Machine Learning" in r.json()["text"]
    assert tpo.post("/tpo/drives/extract-jd", data={"text": "short"}).status_code == 422
