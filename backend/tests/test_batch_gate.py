from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models
from app.db.session import Base
from app.discover.batch_gate import check_gate

ORG = 1


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_run_with_grant(s, batch=1, status="done"):
    run = models.SearchRun(org_id=ORG, batch_number=batch, status=status)
    s.add(run)
    s.flush()
    grant = models.Grant(
        org_id=ORG, search_run_id=run.id, url="https://x", dedupe_key="k", title="G"
    )
    s.add(grant)
    s.flush()
    return run, grant


def test_first_search_allowed():
    s = make_session()
    g = check_gate(s, ORG)
    assert g.allowed and g.next_batch_number == 1


def test_blocked_until_draft_filled():
    s = make_session()
    _, grant = add_run_with_grant(s)
    draft = models.Draft(org_id=ORG, grant_id=grant.id, status=models.DraftStatus.drafting)
    s.add(draft)
    s.commit()
    assert not check_gate(s, ORG).allowed

    draft.status = models.DraftStatus.drafted
    s.commit()
    g = check_gate(s, ORG)
    assert g.allowed and g.next_batch_number == 2 and g.unlocked_by_draft_id == draft.id


def test_blocked_while_running():
    s = make_session()
    add_run_with_grant(s, status="running")
    s.commit()
    assert not check_gate(s, ORG).allowed
