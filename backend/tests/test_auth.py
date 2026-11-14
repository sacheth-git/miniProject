"""Auth, role guards, ownership and multi-tenant isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import ratelimit
from app.core.db import SessionLocal
from app.main import app
from app.models.user import User
from tests.conftest import make_client

anon = TestClient(app)


def _register(email: str, pw: str = "passw0rd!", **kw) -> dict:  # type: ignore[no-untyped-def, type-arg]
    return anon.post("/auth/register", json={"email": email, "password": pw, **kw}).json()


def test_register_login_refresh_logout() -> None:
    r = anon.post("/auth/register", json={"email": "Asha@Example.com", "password": "secret123", "full_name": "Asha"})
    assert r.status_code == 201
    tok = r.json()
    assert tok["user"]["email"] == "asha@example.com" and tok["user"]["role"] == "job_seeker"
    assert anon.post("/auth/register", json={"email": "asha@example.com", "password": "secret123"}).status_code == 409
    assert anon.post("/auth/register", json={"email": "b@example.com", "password": "short1"}).status_code == 422
    assert anon.post("/auth/register", json={"email": "c@example.com", "password": "lettersonly"}).status_code == 422
    assert anon.post("/auth/register", json={"email": "not-an-email", "password": "secret123"}).status_code == 422

    assert anon.post("/auth/login", json={"email": "asha@example.com", "password": "wrong-pass1"}).status_code == 401
    login = anon.post("/auth/login", json={"email": "ASHA@example.com", "password": "secret123"}).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}
    assert anon.get("/auth/me", headers=h).json()["full_name"] == "Asha"

    new = anon.post("/auth/refresh", json={"refresh_token": login["refresh_token"]}).json()
    assert new["access_token"]
    # A refresh token is not an access token, and vice versa.
    assert anon.get("/auth/me", headers={"Authorization": f"Bearer {login['refresh_token']}"}).status_code == 401
    assert anon.post("/auth/refresh", json={"refresh_token": login["access_token"]}).status_code == 401

    assert anon.post("/auth/logout", headers=h).status_code == 204
    assert anon.get("/auth/me", headers=h).status_code == 401  # all sessions revoked
    assert anon.post("/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_login_rate_limit() -> None:
    ratelimit.reset()
    _register("rl@example.com")
    for _ in range(ratelimit.MAX_FAILS):
        assert anon.post("/auth/login", json={"email": "rl@example.com", "password": "nope12345"}).status_code == 401
    r = anon.post("/auth/login", json={"email": "rl@example.com", "password": "passw0rd!"})
    assert r.status_code == 429  # blocked even with the right password
    ratelimit.reset()


def test_unauthenticated_and_role_guards() -> None:
    for method, path in [("get", "/resume/me"), ("get", "/match/x"), ("get", "/applications?candidate_id=x"),
                         ("get", "/gap/x"), ("get", "/tpo/students"), ("get", "/admin/sources/status")]:
        assert getattr(anon, method)(path).status_code == 401, path
    assert anon.get("/jobs").status_code == 200  # guests can browse listings

    seeker, _ = make_client("job_seeker")
    tpo, _ = make_client("tpo")
    assert seeker.get("/tpo/students").status_code == 403
    assert seeker.get("/admin/sources/status").status_code == 403
    assert tpo.post("/resume/upload", files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 403
    assert tpo.get("/resume/me").status_code == 403
    assert anon.post("/auth/register", json={"email": "t@x.com", "password": "passw0rd1", "role": "tpo"}).status_code == 422


def test_resume_ownership(sample_pdfs) -> None:  # type: ignore[no-untyped-def]
    alice, _ = make_client("job_seeker")
    bob, _ = make_client("job_seeker")
    assert alice.get("/resume/me").status_code == 404
    cid = alice.post("/resume/upload", files={"file": ("a.pdf", sample_pdfs["meera_data.pdf"].read_bytes(), "application/pdf")}).json()["id"]
    assert alice.get("/resume/me").json()["id"] == cid
    assert alice.get("/auth/me").json()["candidate_id"] == cid
    # Bob cannot read, edit, delete, track against or deep-link Alice's resume.
    assert bob.get(f"/resume/{cid}").status_code == 404
    assert bob.put(f"/resume/{cid}/skills", json={"add": ["Go"]}).status_code == 404
    assert bob.delete(f"/resume/{cid}").status_code == 404
    assert bob.get(f"/applications?candidate_id={cid}").status_code == 404
    assert bob.get(f"/deeplinks/{cid}").status_code == 404
    assert alice.get(f"/resume/{cid}").status_code == 200


def test_multi_tenant_isolation_and_consent() -> None:
    tpo_a, ua = make_client("tpo", institution_name="Alpha Institute of Technology")
    tpo_b, _ = make_client("tpo", institution_name="Beta College")
    inst_a = tpo_a.get("/tpo/institution").json()
    assert inst_a["name"] == "Alpha Institute of Technology" and inst_a["code"] == "AIT" and len(inst_a["invite_code"]) >= 6

    # Joining needs consent.
    stu, _ = make_client("job_seeker")
    assert stu.post("/auth/join-institution", json={"invite_code": inst_a["invite_code"], "consent": False}).status_code == 422
    assert stu.post("/auth/join-institution", json={"invite_code": "NOPE0000", "consent": True}).status_code == 404
    joined = stu.post("/auth/join-institution", json={"invite_code": inst_a["invite_code"].lower(), "consent": True, "roll_no": "1AI21CS001"}).json()
    assert joined["role"] == "student" and joined["institution_name"] == inst_a["name"] and joined["consent"] is True

    # Sign up with an invite code works too.
    stu2, u2 = make_client("student", invite_code=inst_a["invite_code"], consent=True)
    assert u2["institution_id"] == inst_a["id"]

    roster_a = tpo_a.get("/tpo/students").json()
    assert {r["roll_no"] for r in roster_a} >= {"1AI21CS001"}
    sid = next(r["user_id"] for r in roster_a if r["roll_no"] == "1AI21CS001")

    # Cross-institution: TPO B sees nothing of institution A and gets 403 on direct access.
    assert tpo_b.get("/tpo/students").json() == []
    r = tpo_b.get(f"/tpo/students/{sid}")
    assert r.status_code == 403 and "another institution" in r.json()["detail"]
    assert tpo_a.get(f"/tpo/students/{sid}").status_code == 200

    # A student can't join a second institution.
    inst_b = tpo_b.get("/tpo/institution").json()
    assert stu.post("/auth/join-institution", json={"invite_code": inst_b["invite_code"], "consent": True}).status_code == 409

    # Consent withdrawal hides resume-derived data from the TPO.
    c = stu.get("/student/consent").json()
    assert c["consent"] is True and c["tpo_can_see"]
    w = stu.delete("/student/consent").json()
    assert w["consent"] is False and w["tpo_can_see"] == []
    detail = tpo_a.get(f"/tpo/students/{sid}").json()
    assert detail["consent"] is False and detail["skills"] is None
    assert stu.post("/student/consent").json()["consent"] is True
    assert make_client("job_seeker")[0].get("/student/consent").status_code == 403


def test_forced_password_reset_and_account_deletion(sample_pdfs) -> None:  # type: ignore[no-untyped-def]
    client, u = make_client("job_seeker")
    with SessionLocal() as db:
        db.get(User, u["id"]).must_reset_password = True  # type: ignore[union-attr]
        db.commit()
    assert client.get("/resume/me").status_code == 403  # must set a new password first
    assert client.post("/auth/change-password", json={"current_password": "bad", "new_password": "n3wpassword"}).status_code == 401
    tok = client.post("/auth/change-password", json={"current_password": "passw0rd!", "new_password": "n3wpassword"}).json()
    assert tok["user"]["must_reset_password"] is False
    assert client.get("/auth/me").status_code == 401  # old token revoked by the password change
    fresh = TestClient(app, headers={"Authorization": f"Bearer {tok['access_token']}"})
    cid = fresh.post("/resume/upload", files={"file": ("a.pdf", sample_pdfs["arjun_ece.pdf"].read_bytes(), "application/pdf")}).json()["id"]
    assert fresh.delete("/auth/me").status_code == 204
    assert anon.post("/auth/login", json={"email": u["email"], "password": "n3wpassword"}).status_code == 401
    from app.models.candidate import Candidate

    with SessionLocal() as db:
        assert db.get(Candidate, cid) is None
