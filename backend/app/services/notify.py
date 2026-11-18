"""In-app notifications plus email (SMTP from .env; printed to the console in dev)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.campus import Notification
from app.models.user import User

log = get_logger(__name__)
_outbox: list[dict[str, str]] = []  # dev/test: emails "sent" without SMTP


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not s.smtp_host:
        _outbox.append({"to": to, "subject": subject, "body": body})
        log.info("EMAIL (dev, not sent) to=%s subject=%r", to, subject)
        print(f"\n--- email to {to} ---\nSubject: {subject}\n\n{body}\n---", flush=True)
        return True
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("Email to %s failed: %s", to, exc)
        return False


def outbox() -> list[dict[str, str]]:
    return _outbox


def notify(
    db: Session,
    user: User,
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
    dedupe_key: str | None = None,
    email: bool = True,
) -> Notification | None:
    """Create one notification (skipped if `dedupe_key` was already sent to this user). Caller commits."""
    if dedupe_key and db.scalars(
        select(Notification.id).where(Notification.user_id == user.id, Notification.dedupe_key == dedupe_key)
    ).first():
        return None
    n = Notification(user_id=user.id, kind=kind, title=title[:200], body=body, link=link, dedupe_key=dedupe_key)
    db.add(n)
    if email:
        n.emailed = send_email(user.email, f"HireX: {title}", f"{body}\n\nOpen HireX to see details.")
    return n
