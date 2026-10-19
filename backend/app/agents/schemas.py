"""Structured outputs shared by the pipeline stages."""

from typing import Literal

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    url: str
    title: str


class GrantFields(BaseModel):
    """What the extractor pulls from a grant page. Every claim must be backed by the page text."""

    is_grant_opportunity: bool = Field(
        description="True only if the page describes a specific grant/funding program that accepts applications."
    )
    title: str
    funder: str | None = None
    deadline: str | None = Field(None, description="ISO date YYYY-MM-DD, or null if rolling/unknown")
    rolling_or_unknown_deadline: bool = False
    amount_min: int | None = None
    amount_max: int | None = None
    geography: str | None = Field(None, description="Where applicants/recipients must be located")
    eligible_applicants: list[str] = Field(default_factory=list)
    eligibility_rules: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    application_questions: list[str] = Field(default_factory=list)
    submission_method: Literal["portal", "email", "mail", "other", "unknown"] = "unknown"
    submission_url_or_email: str | None = None
    categories: list[str] = Field(
        default_factory=list, description="e.g. STEM, arts, teacher, facilities, equity, literacy"
    )
    evidence_quotes: list[str] = Field(
        default_factory=list, description="Short verbatim quotes supporting deadline/eligibility"
    )


class Reason(BaseModel):
    text: str
    source_quote: str | None = None


class EligibilityJudgment(BaseModel):
    verdict: Literal["eligible", "likely", "unclear", "ineligible"]
    score: int = Field(ge=0, le=100)
    reasons: list[Reason]
