"""Audit trail for TPO actions (shortlist edits, rule changes, stage changes, imports, exports)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.campus import AuditLog
from app.models.user import User

log = get_logger(__name__)


def audit(
    db: Session,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    institution_id: str | None = None,
) -> AuditLog:
    """Record one action. The caller commits (so the log and the change land together)."""
    row = AuditLog(
        institution_id=institution_id or (actor.institution_id if actor else None),
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else "system",
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    db.add(row)
    log.info("audit %s %s/%s by %s", action, entity, entity_id, row.actor_email)
    return row
