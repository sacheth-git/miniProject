"""Resume upload / read / edit / delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.logging import get_logger
from app.models.candidate import Candidate
from app.parsing.pdf_parser import PDFParseError
from app.schemas.resume import CandidateOut, PreferencesIn, ProcessingStep, SkillEdit, UploadResponse
from app.services.resume_pipeline import process_pdf
from app.skills.taxonomy import get_taxonomy

router = APIRouter(prefix="/resume", tags=["resume"])
log = get_logger(__name__)

MAX_BYTES = 5 * 1024 * 1024


def _get(db: Session, candidate_id: str) -> Candidate:
    cand = db.get(Candidate, candidate_id)
    if cand is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    return cand


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(..., description="PDF resume, max 5 MB"),
    bias_aware: bool = Form(True),
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
    log.info("Parsed resume %s: %d skills, %.1f yrs", cand.id, len(cand.skills), cand.years_experience)
    out = UploadResponse.model_validate(cand, from_attributes=True)
    return out.model_copy(update={"steps": [ProcessingStep(**s) for s in result.steps]})


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_resume(candidate_id: str, db: Session = Depends(get_db)) -> Candidate:
    return _get(db, candidate_id)


@router.put("/{candidate_id}/skills", response_model=CandidateOut)
def edit_skills(candidate_id: str, body: SkillEdit, db: Session = Depends(get_db)) -> Candidate:
    """Add or remove skill chips. Added skills get confidence 1.0 and method 'user'."""
    cand = _get(db, candidate_id)
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
def set_preferences(candidate_id: str, body: PreferencesIn, db: Session = Depends(get_db)) -> Candidate:
    cand = _get(db, candidate_id)
    cand.preferences = body.model_dump()
    db.commit()
    db.refresh(cand)
    return cand


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(candidate_id: str, db: Session = Depends(get_db)) -> Response:
    """Permanently delete the candidate and every derived record."""
    cand = _get(db, candidate_id)
    db.delete(cand)
    db.commit()
    log.info("Deleted candidate %s and all derived data", candidate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
