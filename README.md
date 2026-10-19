# Grant Agent

Finds education grants, checks eligibility for OPEF, drafts applications from OPEF's Google Drive
documents, and waits for human review before export/submission.

Searches run in batches of 10; the next batch unlocks only after one draft from the current batch is filled.

## Run locally
```
cp .env.example .env   # add ANTHROPIC_API_KEY
make setup
make dev               # API :8000, UI :5173
make test
```
Plan: see the project plan in `~/.claude/plans/`.
