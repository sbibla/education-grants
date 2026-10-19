from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.models import Grant, GrantStatus, SearchRun
from app.db.session import get_session
from app.discover.batch_gate import check_gate

router = APIRouter()
ORG_ID = get_settings().default_org_id  # replaced by the authenticated user's org in cloud


class GrantOut(BaseModel):
    id: int
    title: str
    funder: str | None
    url: str
    categories: list
    fields: dict
    verdict: str | None
    reasons: list


class QueueOut(BaseModel):
    batch_number: int | None
    grants: list[GrantOut]
    can_search: bool
    search_blocked_reason: str | None


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/grants/queue", response_model=QueueOut)
def grants_queue(session: Session = Depends(get_session)) -> QueueOut:
    """Current batch only: the latest search run's qualified grants, capped at batch_size."""
    settings = get_settings()
    latest = session.scalars(
        select(SearchRun).where(SearchRun.org_id == ORG_ID).order_by(SearchRun.batch_number.desc())
    ).first()
    grants: list[Grant] = []
    if latest:
        grants = list(
            session.scalars(
                select(Grant)
                .options(selectinload(Grant.eligibility))
                .where(
                    Grant.search_run_id == latest.id,
                    Grant.status.in_(
                        [GrantStatus.qualified, GrantStatus.drafting, GrantStatus.drafted,
                         GrantStatus.in_review, GrantStatus.approved]
                    ),
                )
                .limit(settings.batch_size)
            )
        )
    gate = check_gate(session, ORG_ID)
    return QueueOut(
        batch_number=latest.batch_number if latest else None,
        grants=[
            GrantOut(
                id=g.id, title=g.title, funder=g.funder, url=g.url, categories=g.categories,
                fields=g.fields,
                verdict=g.eligibility.verdict.value if g.eligibility else None,
                reasons=g.eligibility.reasons if g.eligibility else [],
            )
            for g in grants
        ],
        can_search=gate.allowed,
        search_blocked_reason=None if gate.allowed else gate.reason,
    )


@router.post("/search-runs", status_code=202)
def start_search_run(session: Session = Depends(get_session)) -> dict:
    gate = check_gate(session, ORG_ID)
    if not gate.allowed:
        raise HTTPException(status_code=409, detail=gate.reason)
    run = SearchRun(
        org_id=ORG_ID,
        batch_number=gate.next_batch_number,
        unlocked_by_draft_id=gate.unlocked_by_draft_id,
    )
    session.add(run)
    session.commit()
    # TODO(phase 3): enqueue discover -> extract -> eligibility pipeline for this run.
    return {"search_run_id": run.id, "batch_number": run.batch_number}
