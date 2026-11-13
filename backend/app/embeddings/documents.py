"""Canonical texts that get embedded, so ingestion and matching share cache keys."""

from __future__ import annotations

import hashlib

JOB_DOC_CHARS = 4000


def job_document(title: str, description: str) -> str:
    return f"{title}\n{description[:JOB_DOC_CHARS]}"


def job_title_text(title: str) -> str:
    return title.strip().lower()


def text_ref(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
