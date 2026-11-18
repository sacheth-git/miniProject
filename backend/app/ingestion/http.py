"""Shared HTTP client for job sources: retries with backoff, per-host rate limit, 6 h cache."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import BACKEND_DIR
from app.core.logging import get_logger

log = get_logger(__name__)

CACHE_DIR = BACKEND_DIR / "data" / "cache" / "http"
DEFAULT_TTL = 6 * 3600
USER_AGENT = "HireX/0.1 (academic job-matching project; official public APIs only)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class SourceHTTPError(RuntimeError):
    def __init__(self, url: str, status: int | None, message: str) -> None:
        super().__init__(f"{message} ({status}) for {url}")
        self.url = url
        self.status = status


class HttpClient:
    def __init__(
        self,
        cache_dir: Path | None = CACHE_DIR,
        ttl: int = DEFAULT_TTL,
        min_interval: float = 0.25,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.min_interval = min_interval
        self.retries = retries
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            transport=transport,
        )
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self._client.close()

    # ---- cache ----
    def _cache_path(self, method: str, url: str, params: dict[str, Any] | None, body: Any) -> Path | None:
        if self.cache_dir is None:
            return None
        key = json.dumps([method, url, sorted((params or {}).items()), body], sort_keys=True, default=str)
        return self.cache_dir / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def _cache_read(self, path: Path | None) -> Any | None:
        if path is None or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.ttl:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Ignoring unreadable cache file %s: %s", path.name, exc)
            return None

    # ---- rate limit ----
    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            wait = self._last_call.get(host, 0) + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call[host] = time.monotonic()

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        cache_key_params: dict[str, Any] | None = None,
    ) -> Any:
        """GET/POST returning parsed JSON. `cache_key_params` replaces params in the
        cache key so secrets (API keys) never land in cache file names."""
        cpath = self._cache_path(method, url, cache_key_params if cache_key_params is not None else params, json_body) if use_cache else None
        cached = self._cache_read(cpath)
        if cached is not None:
            return cached

        last: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle(url)
            try:
                resp = self._client.request(method, url, params=params, json=json_body, headers=headers)
            except httpx.TransportError as exc:
                last = exc
                log.warning("%s %s transport error (attempt %d): %s", method, url, attempt + 1, exc)
            else:
                if resp.status_code in RETRY_STATUS and attempt < self.retries:
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                    log.warning("%s %s -> %d, retrying in %.0fs", method, url, resp.status_code, delay)
                    time.sleep(min(delay, 30))
                    continue
                if resp.status_code >= 400:
                    raise SourceHTTPError(url, resp.status_code, "HTTP error")
                try:
                    data = resp.json()
                except json.JSONDecodeError as exc:
                    raise SourceHTTPError(url, resp.status_code, "Invalid JSON") from exc
                if cpath is not None:
                    cpath.write_text(json.dumps(data), encoding="utf-8")
                return data
            time.sleep(min(2**attempt, 30))
        raise SourceHTTPError(url, None, f"Failed after retries: {last}")

    def get_json(self, url: str, **kw: Any) -> Any:
        return self.request_json("GET", url, **kw)

    def post_json(self, url: str, body: Any, **kw: Any) -> Any:
        return self.request_json("POST", url, json_body=body, **kw)

    def check_url(self, url: str) -> int | None:
        """Status code for a link check (HEAD, falling back to GET). None on network error."""
        self._throttle(url)
        try:
            r = self._client.head(url, headers={"Accept": "*/*"})
            if r.status_code in (405, 403, 400):
                r = self._client.get(url, headers={"Accept": "*/*"})
            return r.status_code
        except httpx.HTTPError as exc:
            log.warning("Link check failed for %s: %s", url, exc)
            return None
