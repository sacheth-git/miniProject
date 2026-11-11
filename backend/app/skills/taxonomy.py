"""Skill taxonomy loader (curated tech list + ESCO technical skills)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.config import BACKEND_DIR

DEFAULT_PATH = BACKEND_DIR / "data" / "taxonomy" / "skills.json"


def normalize_form(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def slugify(name: str) -> str:
    s = name.lower().replace("+", "plus").replace("#", "sharp").replace(".", "dot")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    category: str
    esco_uri: str | None = None
    source: str = "curated"
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def forms(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


class Taxonomy:
    def __init__(self, skills: list[Skill]) -> None:
        self.skills = skills
        self.by_id: dict[str, Skill] = {s.id: s for s in skills}
        self._by_form: dict[str, Skill] = {}
        for s in skills:  # first writer wins: curated entries come first
            for f in s.forms:
                self._by_form.setdefault(normalize_form(f), s)

    def __len__(self) -> int:
        return len(self.skills)

    def get(self, skill_id: str) -> Skill | None:
        return self.by_id.get(skill_id)

    def lookup(self, text: str) -> Skill | None:
        """Exact (case-insensitive) lookup by canonical name or alias."""
        return self._by_form.get(normalize_form(text))

    def resolve_or_custom(self, text: str) -> Skill:
        """Return the taxonomy skill for `text`, or an ad-hoc custom skill."""
        hit = self.lookup(text)
        if hit is not None:
            return hit
        name = text.strip()
        return Skill(id=f"custom-{slugify(name)}", name=name, category="custom", source="user")


def load_taxonomy_file(path: Path) -> Taxonomy:
    raw = json.loads(path.read_text(encoding="utf-8"))
    skills = [
        Skill(
            id=r["id"],
            name=r["name"],
            category=r.get("category", ""),
            esco_uri=r.get("esco_uri"),
            source=r.get("source", "curated"),
            aliases=tuple(r.get("aliases", [])),
        )
        for r in raw
    ]
    return Taxonomy(skills)


@lru_cache
def get_taxonomy() -> Taxonomy:
    if not DEFAULT_PATH.exists():
        raise FileNotFoundError(
            f"{DEFAULT_PATH} missing. Run: .\\.venv\\Scripts\\python.exe scripts\\build_taxonomy.py"
        )
    return load_taxonomy_file(DEFAULT_PATH)
