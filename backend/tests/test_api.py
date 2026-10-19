import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.db import models
from app.db.session import Base, get_session
from app.main import app

ORG = 1


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    monkeypatch.setattr(routes, "SessionLocal", Session)
    app.dependency_overrides[get_session] = override
    with Session() as s:
        run = models.SearchRun(org_id=ORG, batch_number=1, status="done")
        s.add(run)
        s.flush()
        s.add(
            models.Grant(
                org_id=ORG, search_run_id=run.id, url="https://x.org/a", dedupe_key="a",
                title="Grant A", status=models.GrantStatus.qualified,
                fields={"application_questions": ["Describe your program", "Budget summary"]},
            )
        )
        s.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_draft_flow_unlocks_next_search(client):
    q = client.get("/api/grants/queue").json()
    assert q["can_search"] is False
    assert client.post("/api/search-runs").status_code == 409
    gid = q["grants"][0]["id"]

    r = client.post(f"/api/grants/{gid}/draft")
    assert r.status_code == 202
    draft_id = r.json()["draft_id"]

    # TestClient runs background tasks before returning, so the draft is already filled.
    draft = client.get(f"/api/drafts/{draft_id}").json()
    assert draft["status"] == "drafted"
    assert [f["question"] for f in draft["fields"]] == ["Describe your program", "Budget summary"]
    assert all(f["needs_human"] for f in draft["fields"])

    q = client.get("/api/grants/queue").json()
    assert q["grants"][0]["draft_status"] == "drafted"
    assert q["can_search"] is True  # one filled draft unlocks the next batch


def test_draft_is_idempotent_and_404s(client):
    gid = client.get("/api/grants/queue").json()["grants"][0]["id"]
    first = client.post(f"/api/grants/{gid}/draft").json()["draft_id"]
    assert client.post(f"/api/grants/{gid}/draft").json()["draft_id"] == first
    assert client.post("/api/grants/999/draft").status_code == 404
    assert client.get("/api/drafts/999").status_code == 404
