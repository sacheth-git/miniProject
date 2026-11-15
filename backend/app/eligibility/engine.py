"""Hard eligibility filters with an explicit reason for every failure."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Any

from app.placement_policy.policy import Policy, policy_reasons

OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq, "!=": operator.ne}
CUSTOM_FIELDS = {
    "cgpa", "active_backlogs", "history_backlogs", "tenth_pct", "twelfth_pct", "diploma_pct", "batch_year", "branch",
}
LABELS = {
    "cgpa": "CGPA", "active_backlogs": "Active backlogs", "history_backlogs": "Backlog history", "tenth_pct": "10th %",
    "twelfth_pct": "12th %", "diploma_pct": "Diploma %", "batch_year": "Batch", "branch": "Branch",
}


@dataclass
class StudentFacts:
    """What the engine needs about a student (decoupled from ORM rows for testing)."""

    branch: str | None
    batch_year: int | None
    cgpa: float | None
    active_backlogs: int
    history_backlogs: int
    tenth_pct: float | None
    twelfth_pct: float | None
    diploma_pct: float | None
    placed_status: str = "unplaced"
    current_offer_ctc: float | None = None
    consent: bool = True
    consent_pending: bool = False  # bulk-created, hasn't signed in and agreed yet
    has_resume: bool = True


@dataclass
class Rules:
    allowed_branches: list[str] = field(default_factory=list)
    batch_years: list[int] = field(default_factory=list)
    min_cgpa: float | None = None
    max_active_backlogs: int | None = None
    max_history_backlogs: int | None = None
    min_tenth: float | None = None
    min_twelfth: float | None = None
    custom_rules: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DriveFacts:
    category: str = "regular"
    ctc_lpa: float | None = None


@dataclass
class Verdict:
    eligible: bool
    reasons: list[str]


def _g(x: float) -> str:
    return f"{x:g}"


REASON_GROUPS = [
    ("Consent pending", "Consent pending"), ("Consent withdrawn", "Consent withdrawn"),
    ("Branch", "Branch not allowed"), ("Batch", "Batch not allowed"), ("CGPA", "CGPA below cutoff"),
    ("Active backlogs", "Active backlogs"), ("Backlog history", "Backlog history"), ("10th", "10th % below cutoff"),
    ("12th", "12th / diploma below cutoff"), ("Diploma", "12th / diploma below cutoff"),
    ("Already accepted", "Accepted an offer"), ("One-offer", "One-offer rule"), ("Dream rule", "Dream rule"),
    ("Fails rule", "Custom rule"),
]


def reason_group(reason: str) -> str:
    """Bucket a reason for summary counts ("CGPA 6.4 < 7" -> "CGPA below cutoff")."""
    for prefix, label in REASON_GROUPS:
        if reason.startswith(prefix):
            return "Missing record" if "not on record" in reason else label
    return reason.split(":")[0]


def validate_custom_rule(rule: dict[str, Any]) -> None:
    if rule.get("field") not in CUSTOM_FIELDS:
        raise ValueError(f"Unknown field {rule.get('field')!r}; choose from {sorted(CUSTOM_FIELDS)}")
    if rule.get("op") not in OPS:
        raise ValueError(f"Unknown operator {rule.get('op')!r}; choose from {sorted(OPS)}")
    if "value" not in rule:
        raise ValueError("Custom rule needs a value")


def evaluate(s: StudentFacts, r: Rules, d: DriveFacts, policy: Policy) -> Verdict:
    reasons: list[str] = []
    if not s.consent:
        reasons.append(
            "Consent pending: student hasn't signed in and agreed to share their profile yet"
            if s.consent_pending
            else "Consent withdrawn: student is excluded from shortlists"
        )
    if r.allowed_branches:
        allowed = {b.upper() for b in r.allowed_branches}
        if not s.branch:
            reasons.append("Branch not on record")
        elif s.branch.upper() not in allowed:
            reasons.append(f"Branch {s.branch} not allowed ({', '.join(sorted(allowed))})")
    if r.batch_years:
        if s.batch_year is None:
            reasons.append("Batch year not on record")
        elif s.batch_year not in r.batch_years:
            reasons.append(f"Batch {s.batch_year} not in {', '.join(map(str, sorted(r.batch_years)))}")
    if r.min_cgpa is not None:
        if s.cgpa is None:
            reasons.append("CGPA not on record")
        elif s.cgpa < r.min_cgpa:
            reasons.append(f"CGPA {_g(s.cgpa)} < {_g(r.min_cgpa)}")
    if r.max_active_backlogs is not None and s.active_backlogs > r.max_active_backlogs:
        reasons.append(f"Active backlogs {s.active_backlogs} > {r.max_active_backlogs}")
    if r.max_history_backlogs is not None and s.history_backlogs > r.max_history_backlogs:
        reasons.append(f"Backlog history {s.history_backlogs} > {r.max_history_backlogs}")
    if r.min_tenth is not None:
        if s.tenth_pct is None:
            reasons.append("10th % not on record")
        elif s.tenth_pct < r.min_tenth:
            reasons.append(f"10th {_g(s.tenth_pct)}% < {_g(r.min_tenth)}%")
    if r.min_twelfth is not None:
        best = max((x for x in (s.twelfth_pct, s.diploma_pct) if x is not None), default=None)
        if best is None:
            reasons.append("12th / diploma % not on record")
        elif best < r.min_twelfth:
            label = "12th" if s.twelfth_pct is not None and best == s.twelfth_pct else "Diploma"
            reasons.append(f"{label} {_g(best)}% < {_g(r.min_twelfth)}%")
    for rule in r.custom_rules:
        f, op, val = rule.get("field"), rule.get("op"), rule.get("value")
        actual = getattr(s, f, None) if f in CUSTOM_FIELDS else None
        label = rule.get("label") or f"{LABELS.get(f, f)} {op} {val}"
        if actual is None:
            reasons.append(f"{LABELS.get(f, f)} not on record ({label})")
        elif op in OPS and not OPS[op](actual, val):
            reasons.append(f"Fails rule: {label} (is {actual})")
    reasons += policy_reasons(policy, s.placed_status, s.current_offer_ctc, d.category, d.ctc_lpa)
    return Verdict(eligible=not reasons, reasons=reasons)
