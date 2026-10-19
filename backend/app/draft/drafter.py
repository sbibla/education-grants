"""Draft filling. The stub leaves every answer for a human; phase 5 swaps in a RAG drafter
that answers from OPEF's Drive documents with citations."""

from typing import Protocol

from sqlalchemy.orm import Session

from app.db.models import Draft, DraftField, DraftStatus, Grant, GrantStatus

STUB_NOTE = "[Not drafted yet: OPEF documents aren't connected. Write this answer manually.]"


class Drafter(Protocol):
    def fill(self, session: Session, draft: Draft, grant: Grant) -> None: ...


class StubDrafter:
    def fill(self, session: Session, draft: Draft, grant: Grant) -> None:
        questions = grant.fields.get("application_questions") or ["Application overview"]
        for q in questions:
            session.add(
                DraftField(
                    org_id=draft.org_id,
                    draft_id=draft.id,
                    question=q,
                    answer=STUB_NOTE,
                    needs_human=True,
                )
            )


def run_draft(session: Session, draft_id: int, drafter: Drafter) -> None:
    draft = session.get(Draft, draft_id)
    grant = session.get(Grant, draft.grant_id)
    try:
        drafter.fill(session, draft, grant)
        draft.status = DraftStatus.drafted
        grant.status = GrantStatus.drafted
    except Exception:
        draft.status = DraftStatus.failed
        grant.status = GrantStatus.qualified  # back in the queue so it can be retried
        session.commit()
        raise
    session.commit()
