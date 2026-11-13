"""Test doubles: deterministic encoder and a routed mock HTTP transport."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import numpy as np


class FakeEncoder:
    """Hashed bag-of-words vectors: identical texts -> cosine 1, different -> lower."""

    dim = 256
    model_name = "fake"

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", t.lower()):
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


def routed_transport(routes: dict[str, Any | Callable[[httpx.Request], httpx.Response]]) -> httpx.MockTransport:
    """Map URL substrings to JSON payloads (or handlers). Unmatched -> 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for frag, payload in routes.items():
            if frag in url:
                if callable(payload):
                    return payload(request)
                return httpx.Response(200, content=json.dumps(payload), headers={"content-type": "application/json"})
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)
