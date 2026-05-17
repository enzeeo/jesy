# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Hilo Dispatch — a hackathon disaster-response coordination demo. A FastAPI backend (`src/disaster`) drives a Next.js responder dashboard (`frontend/`) and a separate caller-facing intake PWA (`caller-ui/`). Snowflake and OpenAI are both optional; the demo runs fully on in-memory fallbacks without credentials.

## Commands

Backend (run from repo root):

```bash
uv sync                            # install deps (uses uv + pyproject.toml)
make dev                           # uvicorn disaster.app.main:app --reload --port 8000
make test                          # pytest -v
uv run pytest -v tests/test_foo.py::test_bar   # single test
make lint                          # ruff check src/ tests/
make fmt                           # ruff format src/ tests/
make check                         # lint + test
make snowflake-init                # one-shot DDL + seed against your warehouse
make snowflake-smoke               # connect + verify schema + run all tile/cortex queries
```

Responder dashboard (`frontend/`, port 3000):

```bash
cd frontend && npm install && cp .env.example .env.local && npm run dev
```

Caller intake UI (`caller-ui/`, port 5173):

```bash
cd caller-ui && npm install && cp .env.example .env.local && npm run dev
npm run typecheck                  # tsc --noEmit (caller-ui only)
npm run lint                       # next/eslint
```

Both Next.js apps rewrite `/api/*` to `NEXT_PUBLIC_BACKEND_URL` (default `http://localhost:8000`). Mapbox token (`NEXT_PUBLIC_MAPBOX_TOKEN`) is required for the dashboard map.

## Architecture

### Backend layout (`src/disaster/`)

- `app/main.py` — `create_app()` factory. Loads `.env` from project root (`override=False` — shell env wins), wires `AppState`, registers exception handler + ElevenLabs HMAC middleware, mounts all routers, runs `SnowflakeWriter.start/stop` in lifespan. Module-level `app = create_app()` for `uvicorn disaster.app.main:app`.
- `app/deps.py` — `AppState` dataclass attached to `app.state.disaster`. Handlers read it via `request.app.state.disaster`. Holds `IncidentStore`, `ResponderStore`, `EventBroker`, optional `SnowflakeWriter` and `LLMClient`, ElevenLabs secret.
- `app/middleware.py` — HMAC-SHA256 verifies `/intake/voice`. If `elevenlabs_secret` is None, dev mode passes unverified with a warning.
- `app/routes/` — one router per domain: `incidents`, `triage`, `events`, `routing`, `intake`, `tiles`, `cortex`, `sim`, `demo`. Plus `/healthz` and `/responders` defined inline in `main.py`.
- `models/` — Pydantic v2 models. `IncidentReport` is the canonical type used by every layer (intake → store → snowflake → SSE). Strict mode rejects unknown fields so producer/consumer drift fails loudly.
- `store.py` — `IncidentStore` and `ResponderStore`: dict + `asyncio.Lock`. `IncidentStore` keeps a `(sim_run_id, external_id)` index for simulator idempotency.
- `events.py` — `EventBroker` for SSE. Single-writer, multi-reader; per-subscriber bounded queue (drops oldest on slow consumer). Monotonic `sequence_id` used by `severity_upgraded` dedupe.
- `triage/score.py` — pure START triage scorer (no I/O, no clock, no randomness). First-victim only. Priority score layered on top: severity base + age/vuln/elapsed adjustments, clamped [0,1]. Server-authoritative — always overwrites client-supplied severity/priority on `POST /incidents`.
- `routing/` — `greedy.py`, `vrp.py` (OR-Tools), `optimize.py`. Optimization must keep returning useful output if VRP can't solve.
- `llm/` — OpenAI client wiring (`openai_adapter.py`), retry/metrics wrapper (`client.py`), prompt assembly (`prompt.py`), extraction (`extract.py`). Prompt prefix is **byte-identical** across calls for KV-cache hits; `test_prompt_byte_identity.py` pins `PREFIX_SHA256`. If you intentionally change `GLOBAL_PROTOCOL` or `DISASTER_CONTEXT`, re-pin the hash.
- `snowflake/` — `connection.py` (env detection + flush factory + query runner), `writer.py` (bounded-queue async writer, never blocks caller — drops on `QueueFull`, batches per-table every 5s/50 rows), `tiles.py` (5 tile queries + in-memory fallback), `cortex.py` (cluster scan with Snowflake or in-memory path).
- `simulator/disaster_sim.py` — batch incident generator for load/demo replays.

### Optionality contract

Both OpenAI and Snowflake are optional. Never make demo flow depend on them:

- No `OPENAI_API_KEY` → `/intake/voice` returns 503; `/demo/trigger-call` uses deterministic stub incidents.
- No Snowflake env (or connect fails) → `SnowflakeWriter` is a no-op; tile queries fall back to in-memory computation; Cortex scan uses in-memory clustering.

Env detection is `disaster.snowflake.env_configured()`. Auth supports key-pair (`SNOWFLAKE_PRIVATE_KEY_PATH`, recommended) or password. Generate keys with `uv run python scripts/snowflake_keypair_setup.py`.

### Data flow (incident lifecycle)

1. Source: `POST /incidents` (caller UI), `POST /intake/voice` (ElevenLabs webhook with HMAC), or `POST /demo/trigger-call` (dashboard).
2. Triage runs server-side (overrides client severity).
3. Store insert (with sim idempotency if `sim_run_id` + external_id present).
4. `SnowflakeWriter.put()` queues the row (non-blocking; drops on overflow).
5. `EventBroker.publish()` fans out `incident_created` to all SSE subscribers.
6. Dashboard updates map/list/tiles via `/events` SSE.

### Frontends

- `frontend/` — Next.js 14 responder dashboard. Single-screen "dispatch console" (see `DESIGN.md`). API client in `lib/api.ts` (`/api/*` → backend rewrite). SSE in `lib/useSSE.ts` connects **directly** to `NEXT_PUBLIC_BACKEND_URL/events` — Next.js dev rewrites buffer SSE and break liveness, so do not route SSE through the rewrite.
- `caller-ui/` — Next.js caller intake PWA on port 5173. Flow: `onboard` → `incident` (form) → `status/[id]` (SSE-driven status). Submits via `POST /incidents` with a built transcript and victim payload (`lib/api.ts`).

### Design constraints

`DESIGN.md` pins the responder console aesthetic (Bloomberg/Palantir/ATC posture, JetBrains Mono numerals + Inter, fixed color tokens, layout grid, motion rules). It includes hard "never do this" rules (no system-ui, no purple gradients, no decorative blobs, no icons-in-circles for the 5 Snowflake tiles, etc.). Respect it when touching frontend.

### Docs

Project docs live in `docs/` and the `main`-branch state is documented in `docs/CONTEXT.md` (architecture + route map), `docs/STACK.md`, `docs/PLAN.md`, `docs/TASKS.md`, `docs/TODOS.md`, `docs/DEMO.md`, `docs/SNOWFLAKE_PLAN.md`. They explicitly separate "Current Main Branch" from "Future Features" — branch-only scaffolds (victim PWA monorepo, Hono service, Cortex Agents/Search/Analyst, Streams/Tasks/Dynamic Tables, etc.) are **not** shipped on `main` and should not be treated as current behavior.

## Conventions

- Python 3.11+, `from __future__ import annotations` at top of modules.
- Ruff config in `pyproject.toml` — line length 100, selected lints include `BLE` (blind-except). Tests ignore `BLE001`. Use `# noqa: BLE001` only on intentional broad `except Exception` (e.g. the Snowflake connect fallback in `main.py`).
- Pytest is `asyncio_mode = "auto"` — `async def test_*` runs automatically without decorators.
- The byte-identical LLM prompt prefix is a load-bearing invariant for cache hit rate. Don't reformat `GLOBAL_PROTOCOL`/`DISASTER_CONTEXT` casually.
- Triage is server-authoritative; route handlers must not trust client-supplied severity or priority.
- `SnowflakeWriter.put()` is non-blocking by design — never `await` the queue; drops on overflow are expected and counted.
