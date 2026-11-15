"""Drive lifecycle: stages, student apply/withdraw, offers (with placement policy), notifications.

Stages for a drive: Applied -> Shortlisted -> <each round, in order> -> Offer -> Accepted,
plus Rejected (TPO) and Withdrawn (student). Offer is reached only by recording an offer,
Accepted only when the student accepts it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.campus.drives import evaluate_drive
from app.models.campus import Drive, DriveApplication, Offer
from app.models.user import Institution, StudentProfile, User
from app.placement_policy.policy import Policy, policy_reasons
from app.services.audit import audit
from app.services.notify import notify

FINAL = {"Accepted", "Rejected", "Withdrawn"}
TPO_SET = {"Offer", "Accepted", "Withdrawn"}  # reached through offers / the student, not a manual move


def drive_stages(drive: Drive) -> list[str]:
    rounds = [r for r in (drive.rounds or []) if r not in {"Applied", "Shortlisted", "Offer", "Accepted", "Rejected", "Withdrawn"}]
    return ["Applied", "Shortlisted", *rounds, "Offer", "Accepted", "Rejected", "Withdrawn"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _history(app: DriveApplication, stage: str, by: str, note: str = "") -> None:
    entry = {"stage": stage, "at": _now().isoformat(), "by": by}
    if note:
        entry["note"] = note
    app.stage_history = [*(app.stage_history or []), entry]


def _stage_notify(db: Session, student: User, drive: Drive, stage: str, note: str = "") -> None:
    text = {
        "Shortlisted": "You've been shortlisted.",
        "Rejected": "The company has closed your application.",
        "Offer": "You have an offer! Review and accept it in SkillMatch.",
        "Accepted": "Offer accepted. Congratulations!",
        "Withdrawn": "Your application was withdrawn.",
    }.get(stage, f"You've moved to the '{stage}' round.")
    notify(db, student, "stage", f"{drive.company}: {stage}", f"{drive.role} at {drive.company}. {text} {note}".strip(),
           link=f"/campus/{drive.id}", dedupe_key=f"stage:{drive.id}:{stage}")


def move_stage(db: Session, actor: User, drive: Drive, app: DriveApplication, stage: str, note: str = "") -> bool:
    """TPO moves one application. Returns False when it is already there."""
    stages = drive_stages(drive)
    if stage not in stages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown stage '{stage}' for this drive ({', '.join(stages)})")
    if stage in TPO_SET:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{stage}' is set by recording an offer or by the student")
    if app.stage in {"Accepted", "Withdrawn"}:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Application is {app.stage}; it can't be moved")
    if app.stage == stage:
        return False
    before = app.stage
    app.stage = stage
    _history(app, stage, actor.email, note)
    audit(db, actor, "stage.move", "drive", drive.id, before={"student_id": app.student_id, "stage": before},
          after={"student_id": app.student_id, "stage": stage, "note": note})
    student = db.get(User, app.student_id)
    if student is not None:
        _stage_notify(db, student, drive, stage, note)
    return True


# ---------------- student apply / withdraw ----------------

def apply(db: Session, student: User, drive: Drive) -> DriveApplication:
    if drive.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "This drive is not open for applications")
    deadline = _aware(drive.deadline)
    if deadline is not None and _now() > deadline:
        raise HTTPException(status.HTTP_409_CONFLICT, "The application deadline has passed")
    rec = next((r for r in evaluate_drive(db, drive) if r.user.id == student.id), None)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Drive not found")
    if not rec.verdict.eligible:
        raise HTTPException(status.HTTP_409_CONFLICT, "Not eligible: " + "; ".join(rec.verdict.reasons))
    if rec.candidate is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload your resume before applying")
    app = rec.application
    if app is not None and app.stage not in ("Withdrawn",) and app.source == "student":
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already applied (stage: {app.stage})")
    from app.campus.drives import rank_drive

    ranked = rank_drive(db, drive, [rec])
    b = ranked[0].breakdown
    snap: dict[str, Any] = {"match_percent": round(b.score * 100) if b else None, "skill_percent": round(b.skill * 100) if b else None,
                            "missing_required": [m.name for m in b.missing_required] if b else [], "at": _now().isoformat()}
    if app is None:
        app = DriveApplication(drive_id=drive.id, student_id=student.id, stage="Applied", source="student", match_snapshot=snap, stage_history=[])
        db.add(app)
        _history(app, "Applied", student.email)
    else:  # re-apply after withdrawing, or apply after a TPO pre-shortlist
        app.source, app.match_snapshot = "student", snap
        if app.stage == "Withdrawn":
            app.stage = "Applied"
        _history(app, app.stage, student.email, "Applied by student")
    return app


def withdraw(db: Session, student: User, drive: Drive) -> DriveApplication:
    app = db.scalars(select(DriveApplication).where(DriveApplication.drive_id == drive.id, DriveApplication.student_id == student.id)).first()
    if app is None or app.stage == "Withdrawn":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active application for this drive")
    deadline = _aware(drive.deadline)
    if deadline is not None and _now() > deadline:
        raise HTTPException(status.HTTP_409_CONFLICT, "The deadline has passed; ask your placement office to withdraw you")
    if app.stage not in ("Applied", "Shortlisted"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"You can't withdraw at the '{app.stage}' stage")
    app.stage = "Withdrawn"
    _history(app, "Withdrawn", student.email)
    return app


# ---------------- offers ----------------

def _profile(db: Session, user_id: str) -> StudentProfile:
    prof = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user_id)).first()
    if prof is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student profile not found")
    return prof


def refresh_placement(db: Session, prof: StudentProfile) -> None:
    """Placed status and best offer from the student's offers."""
    offers = db.scalars(select(Offer).where(Offer.student_id == prof.user_id, Offer.status != "declined")).all()
    accepted = [o for o in offers if o.status == "accepted"]
    pending = [o for o in offers if o.status == "pending"]
    prof.placed_status = "placed" if accepted else "offered" if pending else "unplaced"
    prof.current_best_offer_ctc = max((o.ctc_lpa for o in accepted or pending), default=None)


def record_offer(db: Session, actor: User, drive: Drive, student_id: str, ctc: float | None, note: str = "") -> Offer:
    app = db.scalars(select(DriveApplication).where(DriveApplication.drive_id == drive.id, DriveApplication.student_id == student_id)).first()
    if app is None or app.stage in FINAL or app.stage == "Applied":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only shortlisted students still in the process can receive an offer")
    if db.scalars(select(Offer).where(Offer.drive_id == drive.id, Offer.student_id == student_id, Offer.status != "declined")).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "This student already has an offer from this drive")
    prof = _profile(db, student_id)
    inst = db.get(Institution, drive.institution_id)
    policy = Policy.from_settings(inst.settings if inst else None)
    ctc_val = ctc if ctc is not None else drive.ctc_lpa
    if ctc_val is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Set the offer CTC")
    blocked = policy_reasons(policy, prof.placed_status, prof.current_best_offer_ctc, drive.category, ctc_val)
    if blocked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Placement policy: " + "; ".join(blocked))
    offer = Offer(institution_id=drive.institution_id, drive_id=drive.id, student_id=student_id, ctc_lpa=ctc_val, note=note)
    db.add(offer)
    app.stage = "Offer"
    _history(app, "Offer", actor.email, f"{ctc_val:g} LPA")
    db.flush()
    refresh_placement(db, prof)
    audit(db, actor, "offer.create", "drive", drive.id, after={"student_id": student_id, "ctc_lpa": ctc_val})
    student = db.get(User, student_id)
    if student is not None:
        notify(db, student, "offer", f"Offer from {drive.company}",
               f"{drive.company} has offered you the {drive.role} role at {ctc_val:g} LPA. Accept or decline it in SkillMatch.",
               link=f"/campus/{drive.id}", dedupe_key=f"offer:{offer.id}")
    return offer


def decide_offer(db: Session, student: User, offer: Offer, accept: bool) -> Offer:
    if offer.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Offer already {offer.status}")
    drive = db.get(Drive, offer.drive_id)
    assert drive is not None
    prof = _profile(db, student.id)
    inst = db.get(Institution, drive.institution_id)
    policy = Policy.from_settings(inst.settings if inst else None)
    app = db.scalars(select(DriveApplication).where(DriveApplication.drive_id == drive.id, DriveApplication.student_id == student.id)).first()
    if accept and policy.block_after_accept and db.scalars(select(Offer).where(Offer.student_id == student.id, Offer.status == "accepted")).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already accepted an offer (placement policy)")
    offer.status, offer.decided_at = ("accepted" if accept else "declined"), _now()
    if app is not None:
        app.stage = "Accepted" if accept else "Withdrawn"
        _history(app, app.stage, student.email, "" if accept else "Offer declined")
    if accept:
        for other in db.scalars(select(Offer).where(Offer.student_id == student.id, Offer.status == "pending", Offer.id != offer.id)):
            other.status, other.decided_at, other.note = "declined", _now(), "Auto-declined: accepted another offer"
        if policy.block_after_accept:
            # Accepting ends every other campus process for this student.
            for a in db.scalars(select(DriveApplication).where(DriveApplication.student_id == student.id, DriveApplication.drive_id != drive.id)):
                if a.stage not in FINAL:
                    a.stage = "Withdrawn"
                    _history(a, "Withdrawn", "system", "Accepted another offer (placement policy)")
    db.flush()
    refresh_placement(db, prof)
    audit(db, student, "offer.accept" if accept else "offer.decline", "drive", drive.id,
          after={"offer_id": offer.id, "ctc_lpa": offer.ctc_lpa}, institution_id=drive.institution_id)
    return offer


# ---------------- notifications for drives ----------------

def notify_new_drive(db: Session, drive: Drive) -> int:
    """Tell every eligible, consenting student about a newly opened drive (once)."""
    if drive.status != "open":
        return 0
    n = 0
    for r in evaluate_drive(db, drive):
        if r.verdict.eligible and notify(db, r.user, "new_drive", f"New drive: {drive.company}",
                                          f"You're eligible for {drive.role} at {drive.company}."
                                          + (f" Apply by {_aware(drive.deadline):%d %b %Y}." if drive.deadline else ""),
                                          link=f"/campus/{drive.id}", dedupe_key=f"new_drive:{drive.id}"):
            n += 1
    return n


def deadline_reminders(db: Session, hours: int = 24) -> int:
    """Eligible students who haven't applied to a drive closing within `hours` get one reminder."""
    now = _now()
    n = 0
    for drive in db.scalars(select(Drive).where(Drive.status == "open", Drive.deadline.is_not(None))):
        dl = _aware(drive.deadline)
        if dl is None or not (now < dl <= now + timedelta(hours=hours)):
            continue
        for r in evaluate_drive(db, drive):
            applied = r.application is not None and r.application.source == "student" and r.application.stage != "Withdrawn"
            if r.verdict.eligible and not applied and notify(
                db, r.user, "deadline", f"{drive.company} closes soon",
                f"Applications for {drive.role} at {drive.company} close {dl:%d %b %Y %H:%M} UTC.",
                link=f"/campus/{drive.id}", dedupe_key=f"deadline:{drive.id}",
            ):
                n += 1
    db.commit()
    return n
