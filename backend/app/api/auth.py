"""Registration, login, token refresh, account, institution join and consent."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import ratelimit
from app.auth.deps import get_current_user, require_roles, student_profile_of
from app.auth.security import (
    MIN_PASSWORD,
    TokenError,
    access_token,
    decode,
    hash_password,
    needs_rehash,
    refresh_token,
    verify_password,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging import get_logger
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.user import Institution, StudentProfile, User
from app.services import resume_store

router = APIRouter(prefix="/auth", tags=["auth"])
student_router = APIRouter(prefix="/student", tags=["student"])
log = get_logger(__name__)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD, max_length=128)
    full_name: str = Field(default="", max_length=200)
    role: Literal["student", "job_seeker", "tpo"] = "job_seeker"
    institution_name: str | None = Field(default=None, max_length=200, description="TPO only: creates the institution")
    invite_code: str | None = Field(default=None, max_length=16, description="Student only: join on sign-up")
    consent: bool = Field(default=False, description="Student only: share profile and resume with the TPO")


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=MIN_PASSWORD, max_length=128)


class JoinIn(BaseModel):
    invite_code: str = Field(max_length=16)
    consent: bool
    roll_no: str | None = Field(default=None, max_length=40)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_admin: bool
    must_reset_password: bool
    institution_id: str | None
    institution_name: str | None
    consent: bool | None  # students only
    consent_status: str | None  # pending | given | withdrawn (students only)
    candidate_id: str | None  # latest resume


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class ConsentOut(BaseModel):
    institution_name: str | None
    consent: bool
    consent_given_at: datetime | None
    consent_withdrawn_at: datetime | None
    tpo_can_see: list[str]


TPO_VISIBLE = [
    "Name, email, roll number, branch, batch",
    "CGPA, backlogs, 10th / 12th / diploma marks",
    "Your resume, extracted skills and experience",
    "Your match score and skill gap for campus drives",
    "Your campus drive applications and stages",
]


def _check_password_strength(pw: str) -> None:
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password needs at least one letter and one number")


def user_out(db: Session, u: User) -> UserOut:
    inst = db.get(Institution, u.institution_id) if u.institution_id else None
    prof = student_profile_of(db, u) if u.role == "student" else None
    cand = db.scalars(select(Candidate.id).where(Candidate.user_id == u.id).order_by(Candidate.created_at.desc())).first()
    return UserOut(
        id=u.id, email=u.email, full_name=u.full_name, role=u.role, is_admin=u.is_admin,
        must_reset_password=u.must_reset_password, institution_id=u.institution_id,
        institution_name=inst.name if inst else None, consent=prof.has_consent if prof else None,
        consent_status=("given" if prof.has_consent else "withdrawn" if prof.consent_withdrawn_at else "pending") if prof else None,
        candidate_id=cand,
    )


def _tokens(db: Session, u: User) -> TokenOut:
    return TokenOut(
        access_token=access_token(u.id, u.token_version, u.role),
        refresh_token=refresh_token(u.id, u.token_version),
        user=user_out(db, u),
    )


def _institution_code(db: Session, name: str) -> str:
    small = {"of", "and", "the", "for", "in", "at", "de"}
    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in small]
    base = "".join(w[0] for w in words).upper()[:6] or "INST"
    code, n = base, 1
    while db.scalars(select(Institution).where(Institution.code == code)).first():
        n += 1
        code = f"{base}{n}"
    return code


def _join(db: Session, user: User, inst: Institution, consent: bool, roll_no: str | None = None) -> StudentProfile:
    if not consent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "To join, you must agree to share your profile and resume with your placement office",
        )
    if user.role not in ("student", "job_seeker"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only student accounts can join an institution")
    if user.institution_id and user.institution_id != inst.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already belong to another institution")
    prof = student_profile_of(db, user)
    now = datetime.now(timezone.utc)
    if prof is None:
        prof = StudentProfile(user_id=user.id, institution_id=inst.id, roll_no=roll_no)
        db.add(prof)
    prof.consent_given_at, prof.consent_withdrawn_at = now, None
    if roll_no and not prof.roll_no:
        prof.roll_no = roll_no
    user.role, user.institution_id = "student", inst.id
    return prof


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    _check_password_strength(body.password)
    if db.scalars(select(User).where(func.lower(User.email) == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(),
        role=body.role, is_admin=email in {e.lower() for e in get_settings().admin_emails},
    )
    db.add(user)
    if body.role == "tpo":
        if not body.institution_name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "institution_name is required for a TPO account")
        inst = Institution(name=body.institution_name.strip(), code=_institution_code(db, body.institution_name))
        db.add(inst)
        db.flush()
        user.institution_id = inst.id
    db.flush()
    if body.role == "student" and body.invite_code:
        inst = db.scalars(select(Institution).where(Institution.invite_code == body.invite_code.strip().upper())).first()
        if inst is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite code not recognised")
        _join(db, user, inst, body.consent)
    db.commit()
    db.refresh(user)
    log.info("Registered %s user %s", user.role, user.id)
    return _tokens(db, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    key = f"{email}|{request.client.host if request.client else '-'}"
    if ratelimit.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in 15 minutes.")
    user = db.scalars(select(User).where(func.lower(User.email) == email)).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        ratelimit.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")
    ratelimit.reset(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()
    return _tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> TokenOut:
    try:
        data = decode(body.refresh_token, "refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = db.get(User, data["sub"])
    if user is None or not user.is_active or user.token_version != data.get("ver"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session ended; sign in again")
    return _tokens(db, user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_out(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Sign out everywhere: invalidates every access and refresh token."""
    user.token_version += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/change-password", response_model=TokenOut)
def change_password(body: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TokenOut:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    _check_password_strength(body.new_password)
    user.password_hash = hash_password(body.new_password)
    user.must_reset_password = False
    user.token_version += 1  # other sessions end
    db.commit()
    return _tokens(db, user)


@router.post("/join-institution", response_model=UserOut)
def join_institution(body: JoinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    inst = db.scalars(select(Institution).where(Institution.invite_code == body.invite_code.strip().upper())).first()
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite code not recognised")
    _join(db, user, inst, body.consent, body.roll_no)
    db.commit()
    return user_out(db, user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Delete the account and every resume, match, import and tracker entry it owns."""
    if user.role == "tpo":
        raise HTTPException(status.HTTP_409_CONFLICT, "Transfer or close the institution before deleting a TPO account")
    cand_ids = list(db.scalars(select(Candidate.id).where(Candidate.user_id == user.id)))
    if cand_ids:
        db.execute(delete(Job).where(Job.owner_id.in_(cand_ids)))
        db.execute(delete(Candidate).where(Candidate.id.in_(cand_ids)))
    db.delete(user)
    db.commit()
    for cid in cand_ids:
        resume_store.delete(cid)
    log.info("Deleted account %s and %d resume(s)", user.id, len(cand_ids))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- student consent ----------------

def _consent_out(db: Session, user: User) -> ConsentOut:
    prof = student_profile_of(db, user)
    inst = db.get(Institution, user.institution_id) if user.institution_id else None
    return ConsentOut(
        institution_name=inst.name if inst else None,
        consent=bool(prof and prof.has_consent),
        consent_given_at=prof.consent_given_at if prof else None,
        consent_withdrawn_at=prof.consent_withdrawn_at if prof else None,
        tpo_can_see=TPO_VISIBLE if prof and prof.has_consent else [],
    )


@student_router.get("/consent", response_model=ConsentOut)
def get_consent(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)) -> ConsentOut:
    return _consent_out(db, user)


@student_router.post("/consent", response_model=ConsentOut)
def give_consent(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)) -> ConsentOut:
    prof = student_profile_of(db, user)
    if prof is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Join an institution first")
    prof.consent_given_at, prof.consent_withdrawn_at = datetime.now(timezone.utc), None
    db.commit()
    return _consent_out(db, user)


@student_router.delete("/consent", response_model=ConsentOut)
def withdraw_consent(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)) -> ConsentOut:
    """Withdraw consent: the TPO no longer sees your resume and you are left out of shortlists."""
    prof = student_profile_of(db, user)
    if prof is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have not joined an institution")
    prof.consent_withdrawn_at = datetime.now(timezone.utc)
    db.commit()
    return _consent_out(db, user)
