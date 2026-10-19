import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.config import get_settings
from app.db import models
from app.db.session import Base, get_session
from app.main import app

ORG = 1


@pytest.fixture
def client(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    monkeypatch.setattr(routes, "SessionLocal", Session)
    monkeypatch.setattr(get_settings(), "exports_dir", str(tmp_path))
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


def _drafted(client):
    gid = client.get("/api/grants/queue").json()["grants"][0]["id"]
    draft_id = client.post(f"/api/grants/{gid}/draft").json()["draft_id"]
    return draft_id, client.get(f"/api/drafts/{draft_id}").json()["fields"]


def test_as_is_blocked_while_fields_unresolved(client):
    draft_id, _ = _drafted(client)
    r = client.post(f"/api/drafts/{draft_id}/approve", json={})
    assert r.status_code == 409 and "2 field" in r.json()["detail"]
    assert client.get(f"/api/drafts/{draft_id}/export.docx").status_code == 409


def test_edit_approve_export_and_mark_submitted(client):
    draft_id, fields = _drafted(client)
    edits = [{"id": f["id"], "answer": f"Answer {i}"} for i, f in enumerate(fields)]

    r = client.post(f"/api/drafts/{draft_id}/approve", json={"edits": edits})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved" and body["export_ready"]
    assert [f["answer"] for f in body["fields"]] == ["Answer 0", "Answer 1"]
    assert not any(f["needs_human"] for f in body["fields"])

    docx = client.get(f"/api/drafts/{draft_id}/export.docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"  # zip container

    # Approving an already-approved draft is allowed (idempotent re-approve).
    assert client.post(f"/api/drafts/{draft_id}/approve", json={}).status_code == 200

    done = client.post(f"/api/drafts/{draft_id}/mark-submitted").json()
    assert done["status"] == "submitted"
    assert client.post(f"/api/drafts/{draft_id}/approve", json={}).status_code == 409


def test_stub_text_cannot_be_marked_reviewed(client):
    draft_id, fields = _drafted(client)
    r = client.post(
        f"/api/drafts/{draft_id}/approve", json={"reviewed_ids": [f["id"] for f in fields]}
    )
    assert r.status_code == 409  # placeholder answers still need real text
