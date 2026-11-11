"""Shared spaCy pipeline, loaded once."""

from __future__ import annotations

from functools import lru_cache

import spacy
from spacy.language import Language

from app.core.logging import get_logger

log = get_logger(__name__)


@lru_cache
def get_nlp() -> Language:
    try:
        nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    except OSError as exc:
        raise RuntimeError(
            "spaCy model missing. Run: .\\.venv\\Scripts\\python.exe -m spacy download en_core_web_sm"
        ) from exc
    nlp.max_length = 400_000
    log.info("Loaded spaCy pipeline: %s", nlp.pipe_names)
    return nlp
