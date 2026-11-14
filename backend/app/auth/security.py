"""Password hashing (argon2) and JWT access / refresh tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()
ALGO = "HS256"
MIN_PASSWORD = 8


class TokenError(Exception):
    pass


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


def _encode(sub: str, typ: str, ver: int, ttl: timedelta, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "typ": typ, "ver": ver, "iat": now, "exp": now + ttl, **(extra or {})}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGO)


def access_token(user_id: str, ver: int, role: str) -> str:
    return _encode(user_id, "access", ver, timedelta(minutes=get_settings().jwt_access_minutes), {"role": role})


def refresh_token(user_id: str, ver: int) -> str:
    return _encode(user_id, "refresh", ver, timedelta(days=get_settings().jwt_refresh_days))


def decode(token: str, typ: str) -> dict[str, Any]:
    try:
        data = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc
    if data.get("typ") != typ:
        raise TokenError(f"Expected a {typ} token")
    return data
