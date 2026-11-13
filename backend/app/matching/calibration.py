"""Cosine calibration per embedding model.

Raw cosines from different sentence encoders live on different scales. bge-small
puts unrelated skill names at 0.56-0.65 and near-equivalents at 0.70-0.84, so the
spec's "similarity below 0.5 counts as 0" rule would credit everything. We map
cosine c to clip((c - floor) / (ceil - floor), 0, 1) with per-model constants
measured on probe pairs (see docs/report.md, "Calibration"). The map is monotonic,
so it never changes a ranking by a single similarity; it only makes thresholds
and the weighted combination meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Calibration:
    skill_floor: float
    doc_floor: float
    doc_ceil: float

    def skill(self, c: np.ndarray | float) -> np.ndarray:
        return np.clip((np.asarray(c, dtype=np.float32) - self.skill_floor) / (1.0 - self.skill_floor), 0.0, 1.0)

    def doc(self, c: np.ndarray | float) -> np.ndarray:
        return np.clip((np.asarray(c, dtype=np.float32) - self.doc_floor) / (self.doc_ceil - self.doc_floor), 0.0, 1.0)


CALIBRATIONS: dict[str, Calibration] = {
    # Skills, probe pairs: React~SolidWorks 0.618, Docker~Communication 0.582 (unrelated);
    # PostgreSQL~MySQL 0.836, ML~DL 0.811 (near-equivalent).
    # Documents, measured on the live corpus (12,548 JDs vs 3 sample resumes): raw cosine
    # p10 0.52-0.59, p50 0.58-0.65, p99 0.67-0.74, max 0.74-0.80. Long JDs share boilerplate,
    # so the floor sits near the corpus median and the ceiling near the maximum.
    "bge": Calibration(skill_floor=0.62, doc_floor=0.60, doc_ceil=0.80),
    # MiniLM spreads wider. Not yet measured on the corpus; re-measure before relying on it.
    "minilm": Calibration(skill_floor=0.35, doc_floor=0.25, doc_ceil=0.70),
}
DEFAULT = Calibration(skill_floor=0.5, doc_floor=0.3, doc_ceil=0.8)


def calibration_for(model_name: str) -> Calibration:
    name = model_name.lower()
    if "bge" in name or name == "finetuned":
        return CALIBRATIONS["bge"]
    if "minilm" in name:
        return CALIBRATIONS["minilm"]
    return DEFAULT
