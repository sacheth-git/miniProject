"""Institution placement policy (one-offer rule, dream rule, block after accept).

Placed status: "unplaced" | "offered" (has an offer, not accepted) | "placed" (accepted).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.user import DEFAULT_POLICY


@dataclass(frozen=True)
class Policy:
    one_offer_rule: bool = True
    dream_multiplier: float = 1.5
    block_after_accept: bool = True

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None) -> Policy:
        s = {**DEFAULT_POLICY, **(settings or {})}
        return cls(
            one_offer_rule=bool(s.get("one_offer_rule", True)),
            dream_multiplier=float(s.get("dream_multiplier", 1.5)),
            block_after_accept=bool(s.get("block_after_accept", True)),
        )


def _fmt(x: float) -> str:
    return f"{x:g}"


def policy_reasons(
    policy: Policy,
    placed_status: str,
    current_offer_ctc: float | None,
    drive_category: str,
    drive_ctc: float | None,
) -> list[str]:
    """Reasons a student is blocked from a drive by placement policy ([] = allowed).

    - block_after_accept: an accepted offer blocks every drive, dream drives included.
    - one_offer_rule: a student holding an offer may only apply to dream drives
      that pay >= dream_multiplier x their best offer.
    """
    if placed_status not in ("offered", "placed"):
        return []
    if placed_status == "placed" and policy.block_after_accept:
        return ["Already accepted an offer (placement policy blocks further drives)"]
    dream_ok = (
        drive_category == "dream"
        and drive_ctc is not None
        and (current_offer_ctc is None or drive_ctc >= policy.dream_multiplier * current_offer_ctc)
    )
    if policy.one_offer_rule and not dream_ok:
        if drive_category == "dream" and drive_ctc is not None and current_offer_ctc is not None:
            need = policy.dream_multiplier * current_offer_ctc
            return [f"Dream rule: drive CTC {_fmt(drive_ctc)} LPA < {_fmt(policy.dream_multiplier)} x current offer {_fmt(current_offer_ctc)} LPA = {_fmt(round(need, 2))} LPA"]
        return ["One-offer rule: already holds an offer (only dream drives allowed)"]
    return []
