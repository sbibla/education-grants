"""Discover -> extract -> eligibility for one batch (search run).

Stops as soon as `batch_size` grants are qualified (eligible/likely, not expired) or queries run out.
Everything seen, including rejects, is stored so later batches never repeat it.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import GrantLLM
from app.agents.schemas import GrantFields
from app.config import get_settings
from app.db.models import (
    AuditLog,
    EligibilityResult,
    Grant,
    GrantStatus,
    OrgProfile,
    SearchRun,
    Verdict,
)
from app.discover.dedupe import dedupe_key, title_key
from app.extract.fetch import fetch_text

log = logging.getLogger(__name__)

QUALIFYING = {Verdict.eligible, Verdict.likely}
BASE_QUERIES = [
    "education foundation grants California K-12 application deadline",
    "grants for public school foundations California open application",
    "teacher classroom grants nonprofit education foundation apply",
    "STEM education grant nonprofit California school district foundation",
    "arts education grants nonprofit California schools",
]


def build_queries(profile: dict) -> list[str]:
    """Seed queries from the profile's location and program areas, then fall back to the base set."""
    queries: list[str] = []
    region = profile.get("region") or profile.get("county")
    for area in profile.get("program_areas", []):
        queries.append(f"{area} education grants nonprofit {region or 'California'} apply")
    return queries + BASE_QUERIES


def _expired(fields: GrantFields, today: date) -> bool:
    if not fields.deadline:
        return False
    try:
        return date.fromisoformat(fields.deadline) < today
    except ValueError:
        return False


def run_batch(
    session: Session,
    run_id: int,
    llm: GrantLLM,
    fetch: Callable[[str], str] = fetch_text,
    today: date | None = None,
) -> int:
    """Execute a search run. Returns the number of qualified grants found."""
    settings = get_settings()
    today = today or date.today()
    run = session.get(SearchRun, run_id)
    org_id = run.org_id
    profile_row = session.scalars(select(OrgProfile).where(OrgProfile.org_id == org_id)).first()
    if profile_row is None:
        run.status = "failed"
        session.commit()
        raise RuntimeError("No org profile loaded. Run `python -m app.cli profile load <file>` first.")
    profile = {"name": profile_row.name, "ein": profile_row.ein, **profile_row.data}

    seen_urls = set(session.scalars(select(Grant.dedupe_key).where(Grant.org_id == org_id)))
    seen_titles = {
        title_key(g.title, g.funder)
        for g in session.scalars(select(Grant).where(Grant.org_id == org_id))
    }
    queries = build_queries(profile)
    run.queries = queries
    session.commit()

    qualified = 0
    try:
        for query in queries:
            if qualified >= settings.batch_size:
                break
            for hit in llm.search(query):
                if qualified >= settings.batch_size:
                    break
                key = dedupe_key(hit.url)
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                qualified += _process_hit(
                    session, run, llm, fetch, profile, hit.url, hit.title, key, seen_titles, today
                )
        run.status = "done"
    except Exception:
        run.status = "failed"
        raise
    finally:
        run.finished_at = datetime.now(timezone.utc)
        session.add(
            AuditLog(
                org_id=org_id,
                actor="agent:search",
                action="search_run_finished",
                detail={"run_id": run.id, "status": run.status, "qualified": qualified},
            )
        )
        session.commit()
    return qualified


def _process_hit(session, run, llm, fetch, profile, url, title, key, seen_titles, today) -> int:
    """Returns 1 if the hit became a qualified grant, else 0."""
    try:
        text = fetch(url)
        fields = llm.extract(url, text)
    except Exception as exc:  # one bad page must not sink the batch
        log.warning("skipping %s: %s", url, exc)
        return 0
    if not fields.is_grant_opportunity:
        return 0

    tkey = title_key(fields.title, fields.funder)
    if tkey in seen_titles:
        return 0
    seen_titles.add(tkey)

    grant = Grant(
        org_id=run.org_id,
        search_run_id=run.id,
        url=url,
        dedupe_key=key,
        title=fields.title or title,
        funder=fields.funder,
        fields=fields.model_dump(),
        categories=fields.categories,
    )
    session.add(grant)
    session.flush()

    if _expired(fields, today):
        grant.status = GrantStatus.rejected
        session.commit()
        return 0

    judgment = llm.judge(fields, profile)
    verdict = Verdict(judgment.verdict)
    session.add(
        EligibilityResult(
            org_id=run.org_id,
            grant_id=grant.id,
            verdict=verdict,
            score=judgment.score,
            reasons=[r.model_dump() for r in judgment.reasons],
        )
    )
    # "unclear" stays out of the queue for the MVP; it is stored (and deduped) for later review.
    grant.status = GrantStatus.qualified if verdict in QUALIFYING else GrantStatus.rejected
    session.commit()
    return 1 if grant.status == GrantStatus.qualified else 0
