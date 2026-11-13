"""Job vector index: FAISS (inner product on L2-normalised vectors = cosine).

Holds, for every active canonical job:
  doc  - embedding of title + description (retrieval and full-JD similarity)
  resp - embedding of the responsibilities section (falls back to doc)
plus corpus IDF for JD skills. Built from the embedding cache, saved to
data/faiss/, loaded lazily once per process.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.embeddings.documents import job_document
from app.embeddings.encoder import Encoder
from app.models.job import Job
from app.skills.jd_skill_weighter import compute_idf

log = get_logger(__name__)

MIN_RESP_CHARS = 40


def index_dir() -> Path:
    return Path(get_settings().index_dir)


def responsibilities_text(title: str, responsibilities: str) -> str | None:
    r = responsibilities.strip()
    return f"{title}\n{r[:3000]}" if len(r) >= MIN_RESP_CHARS else None


@dataclass
class JobIndex:
    ids: list[str]
    doc: np.ndarray  # (n, d)
    resp: np.ndarray  # (n, d)
    idf: dict[str, float]
    model_name: str
    built_at: float
    _faiss: faiss.Index | None = None

    def __post_init__(self) -> None:
        self.pos = {jid: i for i, jid in enumerate(self.ids)}
        self._faiss = faiss.IndexFlatIP(self.doc.shape[1]) if len(self.ids) else None
        if self._faiss is not None:
            self._faiss.add(np.ascontiguousarray(self.doc, dtype=np.float32))

    def __len__(self) -> int:
        return len(self.ids)

    def search(self, q: np.ndarray, k: int, allowed: list[int] | None = None) -> list[tuple[str, float]]:
        """Top-k (job_id, cosine). `allowed` restricts to index positions (filtered search)."""
        if not self.ids:
            return []
        q = np.ascontiguousarray(q.reshape(1, -1), dtype=np.float32)
        if allowed is not None:
            if not allowed:
                return []
            idx = np.asarray(allowed)
            sims = self.doc[idx] @ q[0]
            top = np.argsort(-sims)[:k]
            return [(self.ids[int(idx[t])], float(sims[t])) for t in top]
        assert self._faiss is not None
        scores, pos = self._faiss.search(q, min(k, len(self.ids)))
        return [(self.ids[int(p)], float(s)) for p, s in zip(pos[0], scores[0]) if p >= 0]

    # ---- persistence ----
    def save(self, directory: Path | None = None) -> None:
        directory = directory or index_dir()
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "doc.npy", self.doc)
        np.save(directory / "resp.npy", self.resp)
        meta = {"ids": self.ids, "idf": self.idf, "model_name": self.model_name, "built_at": self.built_at}
        (directory / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path | None = None) -> JobIndex | None:
        directory = directory or index_dir()
        meta_path = directory / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return cls(
            ids=meta["ids"],
            doc=np.load(directory / "doc.npy"),
            resp=np.load(directory / "resp.npy"),
            idf=meta["idf"],
            model_name=meta["model_name"],
            built_at=meta["built_at"],
        )


def build_index(db: Session, encoder: Encoder) -> JobIndex:
    rows = db.execute(
        select(Job.id, Job.title, Job.description, Job.responsibilities, Job.required_skills, Job.preferred_skills)
        .where(Job.is_active.is_(True), Job.is_duplicate.is_(False), Job.owner_id.is_(None))
        .order_by(Job.id)
    ).all()
    ids = [r.id for r in rows]
    t0 = time.perf_counter()
    doc = encoder.encode([job_document(r.title, r.description) for r in rows]) if rows else np.zeros((0, encoder.dim), np.float32)
    resp = doc.copy()
    resp_pos = [(i, t) for i, r in enumerate(rows) if (t := responsibilities_text(r.title, r.responsibilities)) is not None]
    if resp_pos:
        vecs = encoder.encode([t for _, t in resp_pos])
        for (i, _), v in zip(resp_pos, vecs):
            resp[i] = v
    idf = compute_idf([s["skill_id"] for s in (r.required_skills or []) + (r.preferred_skills or [])] for r in rows)
    log.info("Built job index: %d jobs, %d with responsibilities, %.0fs", len(ids), len(resp_pos), time.perf_counter() - t0)
    return JobIndex(ids, doc, resp, idf, encoder.model_name, time.time())


_lock = threading.Lock()
_index: JobIndex | None = None


def get_index() -> JobIndex | None:
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = JobIndex.load()
                if _index is not None:
                    log.info("Loaded job index: %d jobs (model %s)", len(_index), _index.model_name)
    return _index


def set_index(index: JobIndex | None) -> None:
    global _index
    with _lock:
        _index = index
