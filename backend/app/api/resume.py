"""Resume upload / read / edit / delete."""

from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.deps import SEEKER_ROLES, owned_candidate, require_roles
from app.core.db import get_db
from app.core.logging import get_logger
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.user import User
from app.parsing.pdf_parser import PDFParseError
from app.schemas.resume import CandidateOut, PreferencesIn, ProcessingStep, SkillEdit, UploadResponse
from app.services import resume_store
from app.services.resume_pipeline import process_pdf, process_text
from app.skills.taxonomy import get_taxonomy

router = APIRouter(prefix="/resume", tags=["resume"])
log = get_logger(__name__)

MAX_BYTES = 5 * 1024 * 1024


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(..., description="PDF resume, max 5 MB"),
    bias_aware: bool = Form(True),
    user: User = Depends(require_roles(*SEEKER_ROLES)),
    db: Session = Depends(get_db),
) -> UploadResponse:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Resume larger than 5 MB")
    try:
        result = await run_in_threadpool(process_pdf, data, bias_aware)
    except PDFParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    cand = Candidate(
        user_id=user.id,
        filename=(file.filename or "resume.pdf")[:255],
        raw_text=result.raw_text,
        masked_text=result.masked_text,
        sections=result.sections,
        skills=result.skills,
        years_experience=result.years_experience,
        education_level=result.education_level,
        education_rank=result.education_rank,
        bias_aware=bias_aware,
        pages=result.pages,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    resume_store.save(cand.id, data)  # original PDF, for the TPO's resume ZIP export
    log.info("Parsed resume %s: %d skills, %.1f yrs", cand.id, len(cand.skills), cand.years_experience)
    out = UploadResponse.model_validate(cand, from_attributes=True)
    return out.model_copy(update={"steps": [ProcessingStep(**s) for s in result.steps]})


@router.get("/me", response_model=CandidateOut)
def my_resume(user: User = Depends(require_roles(*SEEKER_ROLES)), db: Session = Depends(get_db)) -> Candidate:
    """The signed-in user's latest resume."""
    cand = db.scalars(select(Candidate).where(Candidate.user_id == user.id).order_by(Candidate.created_at.desc())).first()
    if cand is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No resume uploaded yet")
    return cand


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_resume(cand: Candidate = Depends(owned_candidate)) -> Candidate:
    return cand


@router.put("/{candidate_id}/skills", response_model=CandidateOut)
def edit_skills(body: SkillEdit, cand: Candidate = Depends(owned_candidate), db: Session = Depends(get_db)) -> Candidate:
    """Add or remove skill chips. Added skills get confidence 1.0 and method 'user'."""
    remove = set(body.remove)
    skills = [s for s in cand.skills if s["skill_id"] not in remove]
    have = {s["skill_id"] for s in skills}
    tax = get_taxonomy()
    for name in body.add:
        if not name.strip():
            continue
        sk = tax.resolve_or_custom(name)
        if sk.id in have:
            continue
        skills.append(
            {
                "skill_id": sk.id, "name": sk.name, "esco_uri": sk.esco_uri, "confidence": 1.0,
                "evidence": "Added by user", "section": "user", "method": "user", "mentions": 1,
            }
        )
        have.add(sk.id)
    cand.skills = skills
    db.commit()
    db.refresh(cand)
    return cand


@router.put("/{candidate_id}/preferences", response_model=CandidateOut)
def set_preferences(body: PreferencesIn, cand: Candidate = Depends(owned_candidate), db: Session = Depends(get_db)) -> Candidate:
    cand.preferences = body.model_dump()
    db.commit()
    db.refresh(cand)
    return cand


class ResumeSettings(BaseModel):
    bias_aware: bool


@router.put("/{candidate_id}/settings", response_model=CandidateOut)
def update_settings(body: ResumeSettings, cand: Candidate = Depends(owned_candidate), db: Session = Depends(get_db)) -> Candidate:
    """Toggle bias-aware mode: re-process the stored resume text, keeping skills the user added."""
    if body.bias_aware == cand.bias_aware:
        return cand
    if not cand.raw_text:
        raise HTTPException(status.HTTP_409_CONFLICT, "Original resume text was deleted; upload the resume again")
    result = process_text(cand.raw_text, bias_aware=body.bias_aware, pages=cand.pages)
    user_added = [s for s in cand.skills if s.get("method") == "user"]
    have = {s["skill_id"] for s in result.skills}
    cand.skills = result.skills + [s for s in user_added if s["skill_id"] not in have]
    cand.masked_text = result.masked_text
    cand.sections = result.sections
    cand.bias_aware = body.bias_aware
    db.commit()
    db.refresh(cand)
    return cand


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(candidate_id: str, cand: Candidate = Depends(owned_candidate), db: Session = Depends(get_db)) -> Response:
    """Permanently delete the candidate and every derived record."""
    from app.api.student_campus import active_drive_applications

    active = active_drive_applications(db, cand.user_id)
    if active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You have {active} active campus drive application(s). Withdraw them (or wait until they close) before deleting your data.",
        )
    db.execute(delete(Job).where(Job.owner_id == candidate_id))  # their imported jobs
    db.delete(cand)
    db.commit()
    resume_store.delete(candidate_id)
    log.info("Deleted candidate %s and all derived data", candidate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
