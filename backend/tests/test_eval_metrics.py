"""Evaluation metrics and the proxy-label rule (eval/common.py)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from common import job_family, mrr, ndcg_at, precision_at, proxy_label, recall_at  # noqa: E402


def test_metrics_on_known_ranking() -> None:
    labels = np.array([3, 0, 2, 0, 1], dtype=float)
    order = np.array([1, 0, 2, 3, 4])  # first hit at rank 2
    assert precision_at(order, labels, 2) == 0.5
    assert recall_at(order, labels, 3) == 1.0  # both relevant (>= 2) found by rank 3
    assert mrr(order, labels) == 0.5
    perfect = np.argsort(-labels, kind="stable")
    assert ndcg_at(perfect, labels, 5) == pytest.approx(1.0)
    assert 0 < ndcg_at(order, labels, 5) < 1
    assert ndcg_at(order, np.zeros(5), 5) == 0.0


@pytest.mark.parametrize(
    ("family", "title", "label"),
    [
        ("ml", "Machine Learning Engineer", 3),
        ("ml", "Senior Machine Learning Engineer", 1),
        ("ml", "Data Scientist", 1),  # adjacent family
        ("backend", "Software Engineer", 2),  # generic software title
        ("mech", "Software Engineer", 0),
        ("frontend", "Full Stack Developer", 1),
        ("embedded", "Account Executive", 0),
        ("data_analyst", "Data Analyst - HR", 3),
    ],
)
def test_proxy_label(family: str, title: str, label: int) -> None:
    assert proxy_label(family, title) == label


def test_job_family_order() -> None:
    assert job_family("Full Stack Developer") == "fullstack"  # before the generic developer rule
    assert job_family("Firmware Engineer") == "embedded"
    assert job_family("Sales Manager") is None
