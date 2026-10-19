"""Batch gate: a new search may start only after a draft from the current batch is filled."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Draft, DraftStatus, Grant, SearchRun

FILLED = (DraftStatus.drafted, DraftStatus.approved, DraftStatus.submitted)


@dataclass
class GateResult:
    allowed: bool
    reason: str
    next_batch_number: int
    unlocked_by_draft_id: int | None = None


def check_gate(session: Session, org_id: int) -> GateResult:
    latest = session.scalars(
        select(SearchRun)
        .where(SearchRun.org_id == org_id)
        .order_by(SearchRun.batch_number.desc())
        .limit(1)
    ).first()
    if latest is None:
        return GateResult(True, "first batch", 1)

    next_batch = latest.batch_number + 1
    if latest.status == "running":
        return GateResult(False, "A search is already running.", next_batch)

    filled = session.scalars(
        select(Draft)
        .join(Grant, Draft.grant_id == Grant.id)
        .where(Grant.search_run_id == latest.id, Draft.status.in_(FILLED))
        .order_by(Draft.id)
        .limit(1)
    ).first()
    if filled is None:
        return GateResult(
            False,
            "Fill at least one draft from the current batch before searching for more grants.",
            next_batch,
        )
    return GateResult(True, "unlocked by filled draft", next_batch, filled.id)
