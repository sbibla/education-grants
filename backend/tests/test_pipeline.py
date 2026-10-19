from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agents.schemas import EligibilityJudgment, GrantFields, Reason, SearchHit
from app.config import get_settings
from app.db import models
from app.db.session import Base
from app.discover.dedupe import canonical_url, dedupe_key
from app.discover.pipeline import run_batch

ORG = 1
TODAY = date(2026, 10, 19)


class FakeLLM:
    def __init__(self, hits, fields, verdicts):
        self.hits, self.fields, self.verdicts = hits, fields, verdicts
        self.searches = 0

    def search(self, query):
        self.searches += 1
        return self.hits

    def extract(self, url, page_text):
        return self.fields[url]

    def judge(self, fields, org_profile):
        return EligibilityJudgment(
            verdict=self.verdicts[fields.title], score=80, reasons=[Reason(text="r")]
        )


def grant_fields(title, deadline=None, is_grant=True):
    return GrantFields(is_grant_opportunity=is_grant, title=title, funder="F " + title, deadline=deadline)


def setup():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(models.OrgProfile(org_id=ORG, name="OPEF", data={"region": "Ventura County"}))
    run = models.SearchRun(org_id=ORG, batch_number=1)
    s.add(run)
    s.commit()
    return s, run


def test_batch_classifies_and_filters():
    s, run = setup()
    urls = {f"https://x.org/{n}": n for n in ["a", "b", "c", "d", "e"]}
    fields = {
        "https://x.org/a": grant_fields("A"),
        "https://x.org/b": grant_fields("B"),
        "https://x.org/c": grant_fields("C", deadline="2026-01-01"),  # expired
        "https://x.org/d": grant_fields("D", is_grant=False),  # not a grant
        "https://x.org/e": grant_fields("E"),
    }
    llm = FakeLLM(
        [SearchHit(url=u, title=n) for u, n in urls.items()],
        fields,
        {"A": "eligible", "B": "ineligible", "E": "likely"},
    )
    n = run_batch(s, run.id, llm, fetch=lambda u: "page", today=TODAY)

    assert n == 2
    status = {g.title: g.status for g in s.scalars(select(models.Grant))}
    assert status["A"] == models.GrantStatus.qualified
    assert status["B"] == models.GrantStatus.rejected
    assert status["C"] == models.GrantStatus.rejected
    assert "D" not in status
    assert status["E"] == models.GrantStatus.qualified
    assert s.get(models.SearchRun, run.id).status == "done"


def test_stops_at_batch_size_and_dedupes_across_batches():
    s, run = setup()
    limit = get_settings().batch_size
    urls = [f"https://x.org/g{i}" for i in range(limit + 5)]
    fields = {u: grant_fields(f"T{i}") for i, u in enumerate(urls)}
    verdicts = {f"T{i}": "eligible" for i in range(len(urls))}
    llm = FakeLLM([SearchHit(url=u, title="t") for u in urls], fields, verdicts)

    assert run_batch(s, run.id, llm, fetch=lambda u: "p", today=TODAY) == limit

    run2 = models.SearchRun(org_id=ORG, batch_number=2)
    s.add(run2)
    s.commit()
    run_batch(s, run2.id, llm, fetch=lambda u: "p", today=TODAY)
    batch2 = s.scalars(select(models.Grant).where(models.Grant.search_run_id == run2.id)).all()
    batch1_urls = {
        g.url for g in s.scalars(select(models.Grant).where(models.Grant.search_run_id == run.id))
    }
    assert batch2 and not ({g.url for g in batch2} & batch1_urls)


def test_missing_profile_fails_run():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    run = models.SearchRun(org_id=ORG, batch_number=1)
    s.add(run)
    s.commit()
    try:
        run_batch(s, run.id, FakeLLM([], {}, {}), fetch=lambda u: "", today=TODAY)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    assert s.get(models.SearchRun, run.id).status == "failed"


def test_canonical_url_strips_tracking():
    a = "https://www.Foo.org/grants/?utm_source=x&id=3#top"
    b = "https://foo.org/grants?id=3"
    assert canonical_url(a) == canonical_url(b)
    assert dedupe_key(a) == dedupe_key(b)
