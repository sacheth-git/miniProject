"""Search queries shared by the keyed aggregator sources."""

from __future__ import annotations

# Kept short on purpose: JSearch / SerpApi free tiers have small monthly quotas.
DEFAULT_QUERIES: tuple[str, ...] = (
    "software engineer",
    "software engineer intern",
    "data scientist",
    "machine learning engineer",
    "data analyst",
    "frontend developer",
    "backend developer",
    "devops engineer",
    "embedded engineer",
    "mechanical design engineer",
)
DEFAULT_LOCATION = "India"
