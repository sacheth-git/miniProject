"""Cross-posting dedup.

Two jobs are the same posting if: same normalised company AND title cosine > 0.92
AND description cosine > 0.95. Connected components share a dedup_group_id; apply
options are merged across the group, and one canonical member (direct employer
source first, then newest) stays visible while the rest are flagged is_duplicate.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np

from app.embeddings.documents import job_document, job_title_text

TITLE_THRESHOLD = 0.92
DESC_THRESHOLD = 0.95
SOURCE_PRIORITY = {
    "greenhouse": 0, "lever": 0, "ashby": 0,
    "jsearch": 1, "serpapi": 2, "adzuna": 3, "jooble": 4, "remotive": 5, "import": 6,
}


class Encodes(Protocol):
    def encode(self, texts: list[str], batch_size: int = ...) -> np.ndarray: ...


class _UF:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _merge_options(groups: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for opts in groups:
        for o in opts:
            if o.get("url") and o["url"] not in seen:
                seen.add(o["url"])
                merged.append(o)
    merged.sort(key=lambda o: not o.get("is_direct", False))
    return merged


def _canonical_key(job: Any) -> tuple[int, float]:
    ts = job.posted_at.timestamp() if job.posted_at else 0.0
    return SOURCE_PRIORITY.get(job.source, 9), -ts


def dedup_jobs(jobs: Sequence[Any], encoder: Encodes) -> dict[str, int]:
    """Assign dedup_group_id / is_duplicate / merged apply_options in place.

    `jobs` are ORM Job rows (or objects with the same attributes). Returns stats.
    """
    by_company: dict[str, list[Any]] = defaultdict(list)
    for j in jobs:
        by_company[j.company_norm].append(j)

    candidates = [g for g in by_company.values() if len(g) > 1]
    flat = [j for g in candidates for j in g]
    title_vecs: dict[str, np.ndarray] = {}
    if flat:
        for j, t in zip(flat, encoder.encode([job_title_text(j.title) for j in flat])):
            title_vecs[j.id] = t

    # Stage 1: title pairs above threshold (cheap: titles are short).
    title_pairs: dict[str, list[tuple[int, int]]] = {}
    need_desc: dict[str, Any] = {}
    for company, group in by_company.items():
        if len(group) < 2:
            continue
        T = np.stack([title_vecs[j.id] for j in group])
        pairs = [(int(a), int(b)) for a, b in np.argwhere(np.triu(T @ T.T > TITLE_THRESHOLD, k=1))]
        if pairs:
            title_pairs[company] = pairs
            for a, b in pairs:
                need_desc[group[a].id], need_desc[group[b].id] = group[a], group[b]

    # Stage 2: descriptions only for jobs that have a title match.
    desc_vecs: dict[str, np.ndarray] = {}
    if need_desc:
        jobs_nd = list(need_desc.values())
        for j, d in zip(jobs_nd, encoder.encode([job_document(j.title, j.description) for j in jobs_nd])):
            desc_vecs[j.id] = d

    groups_merged = dup_count = 0
    for company, group in by_company.items():
        uf = _UF(len(group))
        for a, b in title_pairs.get(company, []):
            if float(desc_vecs[group[a].id] @ desc_vecs[group[b].id]) > DESC_THRESHOLD:
                uf.union(a, b)
        comps: dict[int, list[Any]] = defaultdict(list)
        for i, j in enumerate(group):
            comps[uf.find(i)].append(j)
        for members in comps.values():
            members.sort(key=_canonical_key)
            canonical = members[0]
            gid = canonical.id
            if len(members) > 1:
                groups_merged += 1
                merged = _merge_options([m.apply_options for m in members])
            for k, m in enumerate(members):
                m.dedup_group_id = gid
                m.is_duplicate = k > 0
                if len(members) > 1:
                    m.apply_options = merged
            dup_count += len(members) - 1
    return {"jobs": len(jobs), "groups_merged": groups_merged, "duplicates": dup_count}
