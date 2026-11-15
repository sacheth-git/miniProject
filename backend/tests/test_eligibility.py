"""Eligibility engine and placement policy (pure functions)."""

import pytest

from app.eligibility.engine import DriveFacts, Rules, StudentFacts, evaluate, validate_custom_rule
from app.placement_policy.policy import Policy, policy_reasons

P = Policy()


def s(**kw) -> StudentFacts:  # type: ignore[no-untyped-def]
    base = dict(branch="CSE", batch_year=2026, cgpa=8.0, active_backlogs=0, history_backlogs=0,
                tenth_pct=85.0, twelfth_pct=80.0, diploma_pct=None)
    base.update(kw)
    return StudentFacts(**base)  # type: ignore[arg-type]


def test_eligible_when_no_rules() -> None:
    v = evaluate(s(), Rules(), DriveFacts(), P)
    assert v.eligible and v.reasons == []


@pytest.mark.parametrize(
    ("student", "rules", "reason"),
    [
        (s(cgpa=6.8), Rules(min_cgpa=7.0), "CGPA 6.8 < 7"),
        (s(branch="ECE"), Rules(allowed_branches=["CSE", "IT"]), "Branch ECE not allowed (CSE, IT)"),
        (s(batch_year=2025), Rules(batch_years=[2026]), "Batch 2025 not in 2026"),
        (s(active_backlogs=2), Rules(max_active_backlogs=0), "Active backlogs 2 > 0"),
        (s(history_backlogs=3), Rules(max_history_backlogs=1), "Backlog history 3 > 1"),
        (s(tenth_pct=58.5), Rules(min_tenth=60), "10th 58.5% < 60%"),
        (s(twelfth_pct=55.0), Rules(min_twelfth=60), "12th 55% < 60%"),
        (s(cgpa=None), Rules(min_cgpa=6), "CGPA not on record"),
        (s(branch=None), Rules(allowed_branches=["CSE"]), "Branch not on record"),
    ],
)
def test_each_rule_gives_a_reason(student: StudentFacts, rules: Rules, reason: str) -> None:
    v = evaluate(student, rules, DriveFacts(), P)
    assert not v.eligible and v.reasons == [reason]


def test_diploma_counts_for_twelfth_and_reasons_accumulate() -> None:
    assert evaluate(s(twelfth_pct=None, diploma_pct=72), Rules(min_twelfth=60), DriveFacts(), P).eligible
    v = evaluate(s(twelfth_pct=None, diploma_pct=50), Rules(min_twelfth=60), DriveFacts(), P)
    assert v.reasons == ["Diploma 50% < 60%"]
    assert evaluate(s(twelfth_pct=None), Rules(min_twelfth=60), DriveFacts(), P).reasons == ["12th / diploma % not on record"]
    v = evaluate(s(cgpa=6.0, branch="MECH"), Rules(min_cgpa=7, allowed_branches=["CSE"]), DriveFacts(), P)
    assert len(v.reasons) == 2


def test_branch_match_is_case_insensitive() -> None:
    assert evaluate(s(branch="cse"), Rules(allowed_branches=["CSE"]), DriveFacts(), P).eligible


def test_consent() -> None:
    assert "Consent withdrawn" in evaluate(s(consent=False), Rules(), DriveFacts(), P).reasons[0]
    assert "Consent pending" in evaluate(s(consent=False, consent_pending=True), Rules(), DriveFacts(), P).reasons[0]


def test_custom_rules() -> None:
    r = Rules(custom_rules=[{"field": "cgpa", "op": ">=", "value": 8.5, "label": "CGPA at least 8.5 for this role"}])
    assert evaluate(s(cgpa=8.0), r, DriveFacts(), P).reasons == ["Fails rule: CGPA at least 8.5 for this role (is 8.0)"]
    assert evaluate(s(cgpa=9.0), r, DriveFacts(), P).eligible
    r2 = Rules(custom_rules=[{"field": "diploma_pct", "op": ">", "value": 60}])
    assert "not on record" in evaluate(s(), r2, DriveFacts(), P).reasons[0]
    with pytest.raises(ValueError):
        validate_custom_rule({"field": "gender", "op": "==", "value": "f"})  # never allowed as a filter
    with pytest.raises(ValueError):
        validate_custom_rule({"field": "cgpa", "op": "~", "value": 1})
    with pytest.raises(ValueError):
        validate_custom_rule({"field": "cgpa", "op": ">="})


def test_placement_policy() -> None:
    reg, dream = DriveFacts("regular", 6.0), DriveFacts("dream", 15.0)
    # Unplaced: anything goes.
    assert evaluate(s(), Rules(), dream, P).eligible
    # Holding an 8 LPA offer: regular drives blocked, dream needs >= 1.5 x 8 = 12 LPA.
    offered = s(placed_status="offered", current_offer_ctc=8.0)
    assert evaluate(offered, Rules(), reg, P).reasons == ["One-offer rule: already holds an offer (only dream drives allowed)"]
    assert evaluate(offered, Rules(), dream, P).eligible
    low_dream = DriveFacts("dream", 10.0)
    assert evaluate(offered, Rules(), low_dream, P).reasons == [
        "Dream rule: drive CTC 10 LPA < 1.5 x current offer 8 LPA = 12 LPA"
    ]
    # Accepted: blocked everywhere, even dream.
    accepted = s(placed_status="placed", current_offer_ctc=8.0)
    assert "Already accepted" in evaluate(accepted, Rules(), dream, P).reasons[0]
    # Policy switches.
    lenient = Policy(one_offer_rule=False, block_after_accept=False)
    assert evaluate(accepted, Rules(), reg, lenient).eligible
    assert policy_reasons(Policy(dream_multiplier=2.0), "offered", 8.0, "dream", 15.0)  # 15 < 16
    assert Policy.from_settings({"dream_multiplier": "2"}).dream_multiplier == 2.0
    assert Policy.from_settings(None) == Policy()
