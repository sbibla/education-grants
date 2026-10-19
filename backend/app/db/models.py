"""Core tables. Every table carries org_id so multi-org cloud tenancy needs no rewrite."""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GrantStatus(str, enum.Enum):
    discovered = "discovered"
    qualified = "qualified"
    rejected = "rejected"
    drafting = "drafting"
    drafted = "drafted"
    in_review = "in_review"
    approved = "approved"
    submitted = "submitted"
    failed = "failed"
    archived = "archived"


class Verdict(str, enum.Enum):
    eligible = "eligible"
    likely = "likely"
    unclear = "unclear"
    ineligible = "ineligible"


class DraftStatus(str, enum.Enum):
    drafting = "drafting"
    drafted = "drafted"  # all fields filled (some may be flagged needs_human)
    approved = "approved"
    submitted = "submitted"
    failed = "failed"


class OrgProfile(Base):
    __tablename__ = "org_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    ein: Mapped[str | None] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # mission, budget, programs, etc.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class DriveFile(Base):
    __tablename__ = "drive_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    drive_id: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chunk(Base):
    __tablename__ = "chunk"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    drive_file_id: Mapped[int] = mapped_column(ForeignKey("drive_file.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON)  # swap for sqlite-vec/pgvector later


class SearchRun(Base):
    __tablename__ = "search_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    batch_number: Mapped[int] = mapped_column(Integer)
    # Draft whose completion unlocked this run (null for the first batch).
    unlocked_by_draft_id: Mapped[int | None] = mapped_column(ForeignKey("draft.id"))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|done|failed
    queries: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    grants: Mapped[list["Grant"]] = relationship(back_populates="search_run")


class Grant(Base):
    __tablename__ = "grant"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    search_run_id: Mapped[int] = mapped_column(ForeignKey("search_run.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)  # hash of canonical url+title
    title: Mapped[str] = mapped_column(String(500))
    funder: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[GrantStatus] = mapped_column(Enum(GrantStatus), default=GrantStatus.discovered)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)  # extracted deadline/amount/rules/questions
    categories: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    search_run: Mapped[SearchRun] = relationship(back_populates="grants")
    eligibility: Mapped["EligibilityResult | None"] = relationship(back_populates="grant")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="grant")


class EligibilityResult(Base):
    __tablename__ = "eligibility_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("grant.id"), unique=True)
    verdict: Mapped[Verdict] = mapped_column(Enum(Verdict))
    score: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)  # [{text, source_quote}]

    grant: Mapped[Grant] = relationship(back_populates="eligibility")


class Draft(Base):
    __tablename__ = "draft"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("grant.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[DraftStatus] = mapped_column(Enum(DraftStatus), default=DraftStatus.drafting)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    grant: Mapped[Grant] = relationship(back_populates="drafts")
    fields: Mapped[list["DraftField"]] = relationship(back_populates="draft")


class DraftField(Base):
    __tablename__ = "draft_field"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("draft.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)  # [{chunk_id, quote}]
    needs_human: Mapped[bool] = mapped_column(default=False)

    draft: Mapped[Draft] = relationship(back_populates="fields")


class Submission(Base):
    __tablename__ = "submission"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("draft.id"))
    method: Mapped[str] = mapped_column(String(30))  # export|email_draft|portal_prefill
    artifact_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    actor: Mapped[str] = mapped_column(String(50))  # user|agent:<name>
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
