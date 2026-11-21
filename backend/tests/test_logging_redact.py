"""API keys never reach log output."""

from __future__ import annotations

import logging

from app.core.logging import RedactSecrets, redact


def test_redact_query_path_and_header_keys() -> None:
    assert redact("GET https://serpapi.com/search.json?q=x&api_key=abc123def456") == "GET https://serpapi.com/search.json?q=x&api_key=[redacted]"
    assert redact("POST https://jooble.org/api/1234-abcd-5678 200") == "POST https://jooble.org/api/[redacted] 200"
    assert "s3cr3t" not in redact("app_id=1&app_key=s3cr3t")
    assert "zzz999" not in redact("{'X-RapidAPI-Key': 'zzz999'}")
    assert redact("nothing secret here") == "nothing secret here"


def test_filter_rewrites_formatted_record() -> None:
    rec = logging.LogRecord("httpx", logging.INFO, __file__, 1, "HTTP Request: %s", ("GET https://x?api_key=topsecret",), None)
    RedactSecrets().filter(rec)
    assert "topsecret" not in rec.getMessage()
