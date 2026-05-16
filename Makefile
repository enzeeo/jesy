.PHONY: install test lint fmt check dev frontend-install frontend-dev demo snowflake-init snowflake-smoke

install:
	uv sync

test:
	uv run pytest -v

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

check: lint test

dev:
	uv run uvicorn disaster.app.main:app --reload --port 8000

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

# Run both backend and frontend with one command (requires two terminals or a tool like overmind).
demo:
	@echo "Backend: make dev"
	@echo "Frontend: make frontend-dev"
	@echo "Then open http://localhost:3000"

# Snowflake: one-shot to create the 4 tables on your warehouse.
# Requires SNOWFLAKE_ACCOUNT/USER/PASSWORD/etc. in .env (see .env.example).
snowflake-init:
	uv run python scripts/snowflake_smoke.py --init --seed

# Verify schema + run all 5 tile queries + the cortex SQL query.
snowflake-smoke:
	uv run python scripts/snowflake_smoke.py
