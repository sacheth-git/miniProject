"""Structured logging setup."""

from __future__ import annotations

import logging
import re
import sys

from pythonjsonlogger.json import JsonFormatter

# API keys travel in query strings (SerpApi, Adzuna) or the URL path (Jooble). Never let them reach a log.
_SECRET_PATTERNS = (
    re.compile(r"((?:api_key|app_key|app_id|key)=)[^&\s\"']+", re.I),
    re.compile(r"(jooble\.org/api/)[^/?\s\"']+", re.I),
    re.compile(r"((?:x-rapidapi-key)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+", re.I),
)


def redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(r"\1[redacted]", text)
    return text


class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        clean = redact(msg)
        if clean != msg:
            record.msg, record.args = clean, None
        return True


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(
            JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
    handler.addFilter(RedactSecrets())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # httpx logs every request URL at INFO, keys included; our own source logs say what was fetched.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
