"""Sentence encoder: lazy-loaded once, embeddings cached by text hash in SQLite."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.core.config import BACKEND_DIR, REPO_ROOT, get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = get_logger(__name__)

CACHE_PATH = BACKEND_DIR / "data" / "cache" / "embeddings.sqlite"
FINETUNED_DIR = REPO_ROOT / "models" / "finetuned"
_CHUNK = 500
_PERSIST_EVERY = 256


def _key(model: str, text: str) -> str:
    return hashlib.sha1(f"{model}\x00{text}".encode("utf-8")).hexdigest()


class Encoder:
    def __init__(
        self,
        model_name: str,
        fallback_name: str | None = None,
        cache_path: Path | None = CACHE_PATH,
    ) -> None:
        self.requested = model_name
        self.fallback = fallback_name
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(cache_path, check_same_thread=False)
            self._db.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB NOT NULL)")
            self._db.commit()

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load()
        return self._model

    def _load(self) -> SentenceTransformer:
        from sentence_transformers import SentenceTransformer

        candidates = [self.requested]
        if FINETUNED_DIR.exists():
            candidates.insert(0, str(FINETUNED_DIR))
        if self.fallback:
            candidates.append(self.fallback)
        last_exc: Exception | None = None
        for name in candidates:
            try:
                model = SentenceTransformer(name, device="cpu")
                self.model_name = name if name != str(FINETUNED_DIR) else "finetuned"
                log.info("Loaded embedding model %s (dim=%d)", self.model_name, self.dim_of(model))
                return model
            except Exception as exc:  # network/model errors: try the next candidate
                log.warning("Could not load embedding model %s: %s", name, exc)
                last_exc = exc
        raise RuntimeError("No embedding model could be loaded") from last_exc

    @staticmethod
    def dim_of(model: SentenceTransformer) -> int:
        dim = model.get_sentence_embedding_dimension()
        return int(dim) if dim is not None else 0

    @property
    def dim(self) -> int:
        return self.dim_of(self.model)

    def _cache_get(self, keys: list[str]) -> dict[str, np.ndarray]:
        if self._db is None:
            return {}
        found: dict[str, np.ndarray] = {}
        for i in range(0, len(keys), _CHUNK):
            chunk = keys[i : i + _CHUNK]
            q = f"SELECT k, v FROM emb WHERE k IN ({','.join('?' * len(chunk))})"
            with self._lock:
                rows = self._db.execute(q, chunk).fetchall()
            for k, v in rows:
                found[k] = np.frombuffer(v, dtype=np.float32)
        return found

    def _cache_put(self, items: list[tuple[str, np.ndarray]]) -> None:
        if self._db is None or not items:
            return
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO emb (k, v) VALUES (?, ?)",
                [(k, v.astype(np.float32).tobytes()) for k, v in items],
            )
            self._db.commit()

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """L2-normalised float32 embeddings, shape (len(texts), dim)."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        model = self.model  # ensures model_name is final before keys are built
        keys = [_key(self.model_name, t) for t in texts]
        cached = self._cache_get(list(set(keys)))
        missing = [i for i, k in enumerate(keys) if k not in cached]
        if missing:
            uniq: dict[str, str] = {}
            for i in missing:
                uniq.setdefault(keys[i], texts[i])
            items = list(uniq.items())
            # Persist every chunk so an interrupted bulk run resumes where it stopped.
            for start in range(0, len(items), _PERSIST_EVERY):
                chunk = items[start : start + _PERSIST_EVERY]
                vecs = model.encode(
                    [t for _, t in chunk],
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                ).astype(np.float32)
                new = [(k, v) for (k, _), v in zip(chunk, vecs)]
                self._cache_put(new)
                cached.update(new)
                if len(items) > _PERSIST_EVERY:
                    log.info("Encoded %d/%d new texts", min(start + _PERSIST_EVERY, len(items)), len(items))
        return np.stack([cached[k] for k in keys]).astype(np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


@lru_cache
def get_encoder() -> Encoder:
    s = get_settings()
    return Encoder(s.embedding_model, s.embedding_fallback_model)
