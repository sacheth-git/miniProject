"""Embed all active jobs (resumable via the embedding cache) and build the FAISS index.

Usage (from backend/): .\\.venv\\Scripts\\python.exe scripts\\build_index.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.embeddings.encoder import get_encoder  # noqa: E402
from app.embeddings.faiss_index import build_index  # noqa: E402


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    t0 = time.perf_counter()
    with SessionLocal() as db:
        index = build_index(db, get_encoder())
    index.save()
    print(f"index: {len(index)} jobs, {len(index.idf)} skills with idf, saved in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
