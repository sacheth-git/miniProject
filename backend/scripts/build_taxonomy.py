"""Build data/taxonomy/skills.json from the curated list plus ESCO technical skills.

ESCO data comes from the public ESCO API (open data, European Commission):
skills under the ICT and engineering ISCED-F fields are pulled once and cached in
data/taxonomy/esco_raw.json so later builds work offline.

Usage (from backend/):
    .\\.venv\\Scripts\\python.exe scripts\\build_taxonomy.py            # uses cache if present
    .\\.venv\\Scripts\\python.exe scripts\\build_taxonomy.py --refresh  # re-download ESCO
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

BACKEND = Path(__file__).resolve().parents[1]
TAX_DIR = BACKEND / "data" / "taxonomy"
CURATED = TAX_DIR / "curated_skills.yaml"
ESCO_RAW = TAX_DIR / "esco_raw.json"
OUT = TAX_DIR / "skills.json"

API = "https://ec.europa.eu/esco/api"
# ISCED-F fields with technical / digital skills.
ISCED_FIELDS = {
    "0611": "computer use",
    "0612": "database and network design and administration",
    "0613": "software and applications development and analysis",
    "0619": "information and communication technologies not elsewhere classified",
    "0688": "ict interdisciplinary",
    "0541": "mathematics",
    "0542": "statistics",
    "0713": "electricity and energy",
    "0714": "electronics and automation",
    "0715": "mechanics and metal trades",
    "0716": "motor vehicles, ships and aircraft",
    "0732": "building and civil engineering",
    "0711": "chemical engineering and processes",
    "0722": "materials (glass, paper, plastic and wood)",
    "0533": "physics",
}
MAX_WORDS = 4
GENERIC_ALIASES = {
    "testing", "design", "data", "software", "programming", "development", "analysis",
    "engineering", "management", "computer", "network", "system", "systems", "tools",
    "information", "web", "internet", "office", "maintenance", "operation",
}
PAREN = re.compile(r"\s*\(([^)]*)\)\s*$")


def slug(name: str) -> str:
    s = name.lower().replace("+", "plus").replace("#", "sharp").replace(".", "dot")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def norm(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


def _get(client: httpx.Client, path: str, params: dict[str, str]) -> dict[str, Any]:
    for attempt in range(4):
        try:
            r = client.get(f"{API}{path}", params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            wait = 2**attempt
            print(f"  retry {attempt + 1} after {exc!r} (sleep {wait}s)", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"ESCO request failed: {path} {params}")


def download_esco(existing: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Fetch skills for ISCED fields not already in `existing` (incremental)."""
    out: dict[str, dict[str, Any]] = {e["uri"]: e for e in (existing or [])}
    have_codes = {e["isced"] for e in out.values()}
    with httpx.Client(headers={"User-Agent": "HireX-academic-project"}) as client:
        for code, title in ISCED_FIELDS.items():
            if code in have_codes:
                continue
            concept = _get(
                client,
                "/resource/concept",
                {"uri": f"http://data.europa.eu/esco/isced-f/{code}", "language": "en"},
            )
            children = concept.get("_links", {}).get("narrowerSkill", []) or []
            print(f"ISCED-F {code} ({title}): {len(children)} skills")
            for child in children:
                uri = child["uri"]
                if uri in out:
                    continue
                try:
                    detail = _get(client, "/resource/skill", {"uri": uri, "language": "en"})
                except RuntimeError as exc:
                    print(f"  WARNING skipped {child.get('title')!r}: {exc}", file=sys.stderr)
                    continue
                links = detail.get("_links", {})
                skill_type = [t.get("title") for t in (links.get("hasSkillType") or [])]
                out[uri] = {
                    "uri": uri,
                    "label": detail.get("preferredLabel", {}).get("en", child.get("title")),
                    "alt": detail.get("alternativeLabel", {}).get("en", []) or [],
                    "skill_type": skill_type,
                    "isced": code,
                }
                time.sleep(0.1)  # be polite to the public API
    return list(out.values())


def load_curated() -> list[dict[str, Any]]:
    data = yaml.safe_load(CURATED.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    for category, items in data.items():
        for raw in items:
            name, _, alias_str = str(raw).partition("|")
            name = name.strip()
            aliases = [a.strip() for a in alias_str.split(",") if a.strip()]
            entries.append(
                {
                    "id": slug(name),
                    "name": name,
                    "aliases": aliases,
                    "category": category,
                    "esco_uri": None,
                    "source": "curated",
                }
            )
    return entries


def esco_to_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    label: str = item["label"]
    m = PAREN.search(label)
    base = PAREN.sub("", label).strip() if m else label
    if len(base.split()) > MAX_WORDS:
        return None
    aliases = [label] if m else []
    for alt in item["alt"]:
        a = PAREN.sub("", alt).strip()
        if not a or norm(a) in GENERIC_ALIASES or len(a) < 3 or len(a.split()) > MAX_WORDS:
            continue
        # ESCO alt labels include plain words ("board", "wiring", "standard"). Keep a
        # one-word alias only if it looks like a product/tech name (caps or digits).
        if len(a.split()) == 1 and a.islower() and not any(c.isdigit() for c in a):
            continue
        aliases.append(a)
    return {
        "id": "esco-" + item["uri"].rsplit("/", 1)[-1][:8] + "-" + slug(base)[:40],
        "name": base,
        "aliases": sorted(set(aliases) - {base}),
        "category": f"esco_{item['isced']}",
        "esco_uri": item["uri"],
        "source": "esco",
    }


def merge(curated: list[dict[str, Any]], esco: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_form: dict[str, dict[str, Any]] = {}
    for e in curated:
        for form in [e["name"], *e["aliases"]]:
            by_form.setdefault(norm(form), e)
    merged = list(curated)
    linked = added = 0
    for item in esco:
        entry = esco_to_entry(item)
        if entry is None:
            continue
        forms = [entry["name"], *entry["aliases"]]
        hit = next((by_form[norm(f)] for f in forms if norm(f) in by_form), None)
        if hit is not None:
            if hit["esco_uri"] is None:
                hit["esco_uri"] = entry["esco_uri"]
                linked += 1
            continue
        merged.append(entry)
        added += 1
        for f in forms:
            by_form.setdefault(norm(f), entry)
    print(f"curated={len(curated)} esco_linked={linked} esco_added={added} total={len(merged)}")
    return merged


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download ESCO data")
    args = ap.parse_args()
    cached = [] if args.refresh or not ESCO_RAW.exists() else json.loads(ESCO_RAW.read_text(encoding="utf-8"))
    esco = download_esco(cached)
    if len(esco) != len(cached):
        ESCO_RAW.write_text(json.dumps(esco, indent=1, ensure_ascii=False), encoding="utf-8")
    merged = merge(load_curated(), esco)
    OUT.write_text(json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
