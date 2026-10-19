.PHONY: setup api web dev test

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 api web

test:
	cd backend && .venv/bin/pytest -q
