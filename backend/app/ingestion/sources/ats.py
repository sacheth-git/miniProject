"""Shared helpers for ATS board sources: load the verified company seed list."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import BACKEND_DIR

SEED_PATH = BACKEND_DIR / "data" / "seeds" / "companies.yaml"


@dataclass(frozen=True)
class Board:
    token: str
    ats: str
    name: str


def _display_name(token: str) -> str:
    return token.replace("-", " ").replace("_", " ").title()


@lru_cache
def load_boards(path: Path = SEED_PATH) -> tuple[Board, ...]:
    if not path.exists():
        return ()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return tuple(
        Board(token=c["token"], ats=c["ats"], name=c.get("name") or _display_name(c["token"]))
        for c in data.get("companies", [])
    )


def boards_for(ats: str) -> list[Board]:
    return [b for b in load_boards() if b.ats == ats]
