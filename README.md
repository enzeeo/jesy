# Hilo Dispatch

Real-time disaster response coordination system for a hackathon demo. The current `main`
branch is a Python/FastAPI backend with a Next.js responder dashboard.

## Current Main Branch

- FastAPI backend in `src/disaster`
- Next.js dashboard in `frontend`
- In-memory incident and responder stores for demo flow
- Server-sent events for live dashboard updates
- OpenAI-backed voice/transcript extraction when `OPENAI_API_KEY` is set
- Deterministic triage scoring and route optimization
- Optional Snowflake writer and tile queries with in-memory fallbacks
- Hilo, Hawaii demo scenarios controlled from the dashboard

## Docs

| File | Purpose |
| --- | --- |
| `docs/CONTEXT.md` | Main-branch architecture, data flow, and API map |
| `docs/PLAN.md` | Current implementation plan and boundaries |
| `docs/STACK.md` | Current tech stack |
| `docs/TASKS.md` | Main-branch task checklist |
| `docs/TODOS.md` | Current TODOs plus future features |
| `docs/DEMO.md` | Demo runbook |
| `docs/SNOWFLAKE_PLAN.md` | Snowflake status and future Snowflake roadmap |
| `DESIGN.md` | Frontend design rules for the responder console |

## Quick Start

Backend:

```bash
uv sync
cp .env.example .env
make dev
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`.

## Useful Commands

```bash
make test
make lint
make check
make snowflake-init
make snowflake-smoke
```

## Environment

The demo works without Snowflake credentials. If Snowflake env vars are missing,
the backend uses a no-op writer and in-memory tile fallbacks.

Set `OPENAI_API_KEY` only when you want real transcript extraction. Without it,
`/demo/trigger-call` uses deterministic stub incidents and `/intake/voice`
returns unavailable.

## Future Features

Items from branch docs that are not present in `main` are future work:

- Separate victim PWA
- Separate responder Vite app
- Hono/Node API service
- pnpm monorepo layout with `apps/`, `packages/`, and `services/`
- Snowflake SQL files under a `snowflake/` directory
- Cortex Agent command center
- Cortex Search over enriched incident reports
- Cortex Analyst Semantic Views
- Streams, Tasks, Dynamic Tables, H3, and Snowpark UDF pipeline
- Human-approved dispatch recommendation workflow
