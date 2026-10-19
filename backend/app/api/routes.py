import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.models import Draft, DraftStatus, Grant, GrantStatus, SearchRun
from app.db.session import SessionLocal, get_session
from app.discover.batch_gate import check_gate
from app.discover.pipeline import run_batch
from app.draft.drafter import StubDrafter, run_draft

router = APIRouter()
ORG_ID = get_settings().default_org_id  # replaced by the authenticated user's org in cloud
log = logging.getLogger(__name__)


class GrantOut(BaseModel):
    id: int
    title: str
    funder: str | None
    url: str
    categories: list
    fields: dict
    verdict: str | None
    reasons: list
    draft_id: int | None
    draft_status: str | None


class QueueOut(BaseModel):
    batch_number: int | None
    grants: list[GrantOut]
    search_running: bool
    can_search: bool
    search_blocked_reason: str | None


class DraftFieldOut(BaseModel):
    id: int
    question: str
    answer: str
    sources: list
    needs_human: bool


class DraftOut(BaseModel):
    id: int
    grant_id: int
    version: int
    status: str
    fields: list[DraftFieldOut]


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _latest_draft(grant: Grant) -> Draft | None:
    live = [d for d in grant.drafts if d.status != DraftStatus.failed]
    return max(live, key=lambda d: d.id) if live else None


@router.get("/grants/queue", response_model=QueueOut)
def grants_queue(session: Session = Depends(get_session)) -> QueueOut:  # noqa: B008
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
                .options(selectinload(Grant.eligibility), selectinload(Grant.drafts))
                .where(
                    Grant.search_run_id == latest.id,
                    Grant.status.in_(
                        [GrantStatus.qualified, GrantStatus.drafting, GrantStatus.drafted,
                         GrantStatus.in_review, GrantStatus.approved]
                    ),
                )
                .order_by(Grant.id)
                .limit(settings.batch_size)
            )
        )
    gate = check_gate(session, ORG_ID)
    out = []
    for g in grants:
        d = _latest_draft(g)
        out.append(
            GrantOut(
                id=g.id, title=g.title, funder=g.funder, url=g.url, categories=g.categories,
                fields=g.fields,
                verdict=g.eligibility.verdict.value if g.eligibility else None,
                reasons=g.eligibility.reasons if g.eligibility else [],
                draft_id=d.id if d else None,
                draft_status=d.status.value if d else None,
            )
        )
    return QueueOut(
        batch_number=latest.batch_number if latest else None,
        grants=out,
        search_running=bool(latest and latest.status == "running"),
        can_search=gate.allowed,
        search_blocked_reason=None if gate.allowed else gate.reason,
    )


@router.post("/search-runs", status_code=202)
def start_search_run(
    background: BackgroundTasks,
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
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
    background.add_task(_run_search_in_background, run.id)
    return {"search_run_id": run.id, "batch_number": run.batch_number}


def _run_search_in_background(run_id: int) -> None:
    from app.agents.llm import ClaudeGrantLLM

    with SessionLocal() as session:
        try:
            run_batch(session, run_id, ClaudeGrantLLM())
        except Exception:
            log.exception("search run %s failed", run_id)


@router.post("/grants/{grant_id}/draft", status_code=202)
def start_draft(
    grant_id: int,
    background: BackgroundTasks,
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    grant = session.scalars(
        select(Grant).options(selectinload(Grant.drafts)).where(Grant.id == grant_id, Grant.org_id == ORG_ID)
    ).first()
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")
    existing = _latest_draft(grant)
    if existing:  # idempotent: don't create a second draft while one exists
        return {"draft_id": existing.id, "status": existing.status.value}
    if grant.status != GrantStatus.qualified:
        raise HTTPException(status_code=409, detail=f"Grant is {grant.status.value}, not draftable")

    draft = Draft(org_id=ORG_ID, grant_id=grant.id, status=DraftStatus.drafting)
    grant.status = GrantStatus.drafting
    session.add(draft)
    session.commit()
    background.add_task(_run_draft_in_background, draft.id)
    return {"draft_id": draft.id, "status": draft.status.value}


def _run_draft_in_background(draft_id: int) -> None:
    with SessionLocal() as session:
        try:
            run_draft(session, draft_id, StubDrafter())
        except Exception:
            log.exception("draft %s failed", draft_id)


@router.get("/drafts/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:  # noqa: B008
    draft = session.scalars(
        select(Draft).options(selectinload(Draft.fields)).where(Draft.id == draft_id, Draft.org_id == ORG_ID)
    ).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return DraftOut(
        id=draft.id,
        grant_id=draft.grant_id,
        version=draft.version,
        status=draft.status.value,
        fields=[
            DraftFieldOut(id=f.id, question=f.question, answer=f.answer, sources=f.sources,
                          needs_human=f.needs_human)
            for f in sorted(draft.fields, key=lambda f: f.id)
        ],
    )
