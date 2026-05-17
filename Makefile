.PHONY: install test lint fmt check dev frontend-install frontend-dev demo snowflake-init snowflake-smoke agents-push agents-pull agents-dry-run agents-push-agent-only demo-setup demo-up demo-up-prod ngrok-init

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

# ── ElevenLabs Agents ─────────────────────────────────────────────────────────
# Full-cycle push: substitute backend URL → push tools → inject tool_ids into
# agent → push agent → print agent_id for caller-ui/.env.local.
#
#   make agents-push BACKEND_URL=https://abc123.ngrok.app
#
# Re-runnable. Single command from a fresh ngrok tunnel to a working agent.
agents-push:
	@test -n "$(BACKEND_URL)" || (echo "ERROR: BACKEND_URL required. Example:  make agents-push BACKEND_URL=https://abc123.ngrok.app"; exit 1)
	uv run python scripts/elevenlabs_sync.py --backend-url $(BACKEND_URL)

# Show what would change, no mutating API calls.
agents-dry-run:
	@test -n "$(BACKEND_URL)" || (echo "ERROR: BACKEND_URL required. Example:  make agents-dry-run BACKEND_URL=https://abc123.ngrok.app"; exit 1)
	uv run python scripts/elevenlabs_sync.py --backend-url $(BACKEND_URL) --dry-run

# Push only the agent (skip tool sync — use when iterating on the prompt).
agents-push-agent-only:
	@test -n "$(BACKEND_URL)" || (echo "ERROR: BACKEND_URL required."; exit 1)
	uv run python scripts/elevenlabs_sync.py --backend-url $(BACKEND_URL) --skip-tools

# Pull dashboard-side edits back into local JSONs.
agents-pull:
	@cd agents/elevenlabs && elevenlabs tools pull --all && elevenlabs agents pull --update

# One-shot wiring per demo session. Assumes `ngrok start --all` is already
# running. Discovers both tunnel URLs from ngrok's local API, updates
# caller-ui/.env.local, re-syncs agent if backend URL changed, prints the
# caller URL for your phone.
demo-setup:
	uv run python scripts/demo_setup.py

# One-time setup: append a `tunnels:` block to your ngrok.yml so
# `ngrok start --all` actually has tunnels to start. Auto-detects your free
# static domain from the existing tool configs.
#   make ngrok-init                              # auto-detect
#   make ngrok-init NGROK_DOMAIN=foo.ngrok-free.dev   # explicit
ngrok-init:
	uv run python scripts/ngrok_init.py $(if $(NGROK_DOMAIN),--domain $(NGROK_DOMAIN),)

# Full demo orchestrator. One command starts everything (backend, ngrok,
# caller-ui, demo-setup wiring) with prefixed logs in a single terminal.
# Ctrl-C tears the whole tree down cleanly. Requires uv, npm, ngrok on PATH
# and caller-ui/node_modules already installed.
demo-up:
	uv run python scripts/demo_run.py

# Same as demo-up but builds + runs caller-ui in production mode. Required
# when testing on iOS Safari over ngrok — Next 16's Turbopack dev runtime
# breaks hydration in that environment. Adds ~15s to startup.
demo-up-prod:
	uv run python scripts/demo_run.py --caller-prod
