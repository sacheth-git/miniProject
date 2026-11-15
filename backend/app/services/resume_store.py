"""Original resume PDFs on disk (needed for the TPO's resume ZIP export). Private, deletable."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import BACKEND_DIR

STORE = BACKEND_DIR / "data" / "resumes"
_SAFE = re.compile(r"^[a-f0-9]{32}$")


def path_for(candidate_id: str) -> Path:
    if not _SAFE.match(candidate_id):
        raise ValueError("Invalid candidate id")
    return STORE / f"{candidate_id}.pdf"


def save(candidate_id: str, data: bytes) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    p = path_for(candidate_id)
    p.write_bytes(data)
    return p


def load(candidate_id: str) -> bytes | None:
    p = path_for(candidate_id)
    return p.read_bytes() if p.exists() else None


def delete(candidate_id: str) -> None:
    try:
        path_for(candidate_id).unlink(missing_ok=True)
    except ValueError:
        pass
