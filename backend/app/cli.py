"""Local CLI: load the org profile and run search batches without the UI.

    python -m app.cli profile load profile.json
    python -m app.cli search
"""

import argparse
import json
import sys

from sqlalchemy import select

from app.agents.llm import ClaudeGrantLLM
from app.config import get_settings
from app.db.models import OrgProfile, SearchRun
from app.db.session import SessionLocal, init_db
from app.discover.batch_gate import check_gate
from app.discover.pipeline import run_batch


def load_profile(path: str) -> None:
    org_id = get_settings().default_org_id
    with open(path) as f:
        data = json.load(f)
    name, ein = data.pop("name"), data.pop("ein", None)
    with SessionLocal() as s:
        row = s.scalars(select(OrgProfile).where(OrgProfile.org_id == org_id)).first()
        if row is None:
            row = OrgProfile(org_id=org_id, name=name)
            s.add(row)
        row.name, row.ein, row.data = name, ein, data
        s.commit()
    print(f"Loaded profile for {name}")


def search() -> int:
    org_id = get_settings().default_org_id
    with SessionLocal() as s:
        gate = check_gate(s, org_id)
        if not gate.allowed:
            print(f"Blocked: {gate.reason}")
            return 1
        run = SearchRun(
            org_id=org_id,
            batch_number=gate.next_batch_number,
            unlocked_by_draft_id=gate.unlocked_by_draft_id,
        )
        s.add(run)
        s.commit()
        n = run_batch(s, run.id, ClaudeGrantLLM())
        print(f"Batch {run.batch_number}: {n} qualified grants")
    return 0


def main() -> int:
    init_db()
    parser = argparse.ArgumentParser(prog="grant-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    prof = sub.add_parser("profile").add_subparsers(dest="action", required=True)
    prof.add_parser("load").add_argument("path")
    sub.add_parser("search")
    args = parser.parse_args()
    if args.cmd == "profile":
        load_profile(args.path)
        return 0
    return search()


if __name__ == "__main__":
    sys.exit(main())
