"""FastAPI auth dependencies: current user, role guards, ownership and tenant checks."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import TokenError, decode
from app.core.db import get_db
from app.models.candidate import Candidate
from app.models.user import StudentProfile, User

bearer = HTTPBearer(auto_error=False)
SEEKER_ROLES = ("student", "job_seeker")


def _unauthorized(msg: str = "Not signed in") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise _unauthorized()
    try:
        data = decode(creds.credentials, "access")
    except TokenError as exc:
        raise _unauthorized(str(exc)) from exc
    user = db.get(User, data["sub"])
    if user is None or not user.is_active or user.token_version != data.get("ver"):
        raise _unauthorized("Session ended; sign in again")
    return user


def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User | None:
    if creds is None:
        return None
    return get_current_user(creds, db)


def require_roles(*roles: str) -> Callable[[User], User]:
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot access this")
        if user.must_reset_password:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Set a new password first")
        return user

    return dep


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


def owned_candidate(candidate_id: str, user: User = Depends(require_roles(*SEEKER_ROLES)), db: Session = Depends(get_db)) -> Candidate:
    """A candidate profile the signed-in student / job seeker owns. Others' ids look like 404."""
    cand = db.get(Candidate, candidate_id)
    if cand is None or cand.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    return cand


def ensure_same_institution(user: User, institution_id: str | None) -> None:
    """Tenant guard: TPOs see only their own institution's data."""
    if user.institution_id is None or institution_id != user.institution_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This record belongs to another institution")


def tpo_user(user: User = Depends(require_roles("tpo"))) -> User:
    if user.institution_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "TPO account has no institution")
    return user


def student_profile_of(db: Session, user: User) -> StudentProfile | None:
    return db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
