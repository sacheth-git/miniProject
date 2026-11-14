"""In-process login throttle: 10 failed attempts per email+IP per 15 minutes."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

WINDOW = 15 * 60
MAX_FAILS = 10

_fails: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _prune(q: deque[float], now: float) -> None:
    while q and now - q[0] > WINDOW:
        q.popleft()


def blocked(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        q = _fails[key]
        _prune(q, now)
        return len(q) >= MAX_FAILS


def record_failure(key: str) -> None:
    with _lock:
        _fails[key].append(time.monotonic())


def reset(key: str | None = None) -> None:
    with _lock:
        if key is None:
            _fails.clear()
        else:
            _fails.pop(key, None)
