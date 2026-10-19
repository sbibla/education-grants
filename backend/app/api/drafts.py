"""Draft review: read, edit, approve (with an export file), and confirm manual submission."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.models import (
    AuditLog,
    Draft,
    DraftField,
    DraftStatus,
    Grant,
    GrantStatus,
    Submission,
)
from app.db.session import get_session
from app.draft.drafter import STUB_NOTE
from app.submit.export import build_docx

router = APIRouter()
ORG_ID = get_settings().default_org_id


class DraftFieldOut(BaseModel):
    id: int
    question: str
    answer: str
    sources: list
    needs_human: bool


class DraftOut(BaseModel):
    id: int
    grant_id: int
    grant_title: str
    grant_url: str
    submission_method: str | None
    submission_target: str | None
    version: int
    status: str
    fields: list[DraftFieldOut]
    export_ready: bool


class FieldEdit(BaseModel):
    id: int
    answer: str


class ApproveIn(BaseModel):
    edits: list[FieldEdit] = []  # only fields the user changed
    reviewed_ids: list[int] = []  # flagged fields the user read and accepts as written


def _load(session: Session, draft_id: int) -> Draft:
    draft = session.scalars(
        select(Draft)
        .options(selectinload(Draft.fields), selectinload(Draft.grant))
        .where(Draft.id == draft_id, Draft.org_id == ORG_ID)
    ).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


def _out(draft: Draft, export_ready: bool) -> DraftOut:
    g = draft.grant
    return DraftOut(
        id=draft.id,
        grant_id=g.id,
        grant_title=g.title,
        grant_url=g.url,
        submission_method=g.fields.get("submission_method"),
        submission_target=g.fields.get("submission_url_or_email"),
        version=draft.version,
        status=draft.status.value,
        fields=[
            DraftFieldOut(id=f.id, question=f.question, answer=f.answer, sources=f.sources,
                          needs_human=f.needs_human)
            for f in sorted(draft.fields, key=lambda f: f.id)
        ],
        export_ready=export_ready,
    )


def _export_path(draft: Draft) -> Path:
    return Path(get_settings().exports_dir) / f"grant-{draft.grant_id}-draft-{draft.id}.docx"


@router.get("/drafts/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:  # noqa: B008
    draft = _load(session, draft_id)
    return _out(draft, _export_path(draft).exists())


@router.post("/drafts/{draft_id}/approve", response_model=DraftOut)
def approve_draft(
    draft_id: int,
    body: ApproveIn,
    session: Session = Depends(get_session),  # noqa: B008
) -> DraftOut:
    """Apply any edits, require every field answered and human-resolved, then export a DOCX.

    Covers both "submit as-is" (no edits) and "save changes & submit".
    """
    draft = _load(session, draft_id)
    if draft.status not in (DraftStatus.drafted, DraftStatus.approved):
        raise HTTPException(status_code=409, detail=f"Draft is {draft.status.value}")

    by_id: dict[int, DraftField] = {f.id: f for f in draft.fields}
    for edit in body.edits:
        field = by_id.get(edit.id)
        if field is None:
            raise HTTPException(status_code=404, detail=f"Field {edit.id} not in this draft")
        if edit.answer != field.answer:
            session.add(
                AuditLog(
                    org_id=ORG_ID,
                    actor="user",
                    action="draft_field_edited",
                    detail={"draft_id": draft.id, "field_id": field.id, "before": field.answer,
                            "after": edit.answer},
                )
            )
            field.answer = edit.answer
            field.needs_human = False  # a person wrote it
    for fid in body.reviewed_ids:
        if fid in by_id:
            by_id[fid].needs_human = False

    unresolved = [
        f for f in draft.fields
        if f.needs_human or not f.answer.strip() or f.answer == STUB_NOTE
    ]
    if unresolved:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"{len(unresolved)} field(s) still need your answer before this can be submitted.",
        )

    path = build_docx(draft, draft.grant, get_settings().exports_dir)
    if draft.status != DraftStatus.approved:
        session.add(
            Submission(org_id=ORG_ID, draft_id=draft.id, method="export", artifact_path=str(path))
        )
    draft.status = DraftStatus.approved
    draft.grant.status = GrantStatus.approved
    session.add(
        AuditLog(org_id=ORG_ID, actor="user", action="draft_approved", detail={"draft_id": draft.id})
    )
    session.commit()
    return _out(draft, True)


@router.get("/drafts/{draft_id}/export.docx")
def export_docx(draft_id: int, session: Session = Depends(get_session)) -> FileResponse:  # noqa: B008
    draft = _load(session, draft_id)
    path = _export_path(draft)
    if draft.status not in (DraftStatus.approved, DraftStatus.submitted) or not path.exists():
        raise HTTPException(status_code=409, detail="Approve the draft first")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@router.post("/drafts/{draft_id}/mark-submitted", response_model=DraftOut)
def mark_submitted(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:  # noqa: B008
    """The human sent the application themselves (email/portal); record it."""
    draft = _load(session, draft_id)
    if draft.status != DraftStatus.approved:
        raise HTTPException(status_code=409, detail="Approve the draft first")
    draft.status = DraftStatus.submitted
    draft.grant.status = GrantStatus.submitted
    session.add(
        AuditLog(org_id=ORG_ID, actor="user", action="marked_submitted", detail={"draft_id": draft.id})
    )
    session.commit()
    return _out(draft, _export_path(draft).exists())
