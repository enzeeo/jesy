# Context

## Product

Hilo Dispatch is a responder-facing disaster coordination demo. Operators seed
responders, trigger sample voice incidents, watch incidents appear on a live map,
run Cortex-style anomaly scans, and optimize dispatch routes.

## Current Architecture

```text
Next.js dashboard
  -> /api rewrite
FastAPI backend
  -> in-memory stores
  -> SSE event broker
  -> optional OpenAI extraction
  -> optional Snowflake writer/query runner
```

## Backend

Backend entry point: `src/disaster/app/main.py`.

Mounted routes:

- `GET /healthz`
- `GET /responders`
- `POST /incidents`
- `GET /incidents`
- `GET /incidents/{incident_id}`
- `POST /incidents/{incident_id}/escalate`
- `POST /triage/score`
- `GET /events`
- `POST /routing/optimize`
- `POST /intake/voice`
- `GET /snowflake/tile/{tile_name}`
- `GET /snowflake/tiles`
- `POST /cortex/scan`
- `POST /sim/start`
- `POST /sim/stop`
- `GET /sim/status`
- `POST /demo/seed-responders`
- `POST /demo/reset`
- `POST /demo/trigger-call`
- `GET /demo/scenarios`

## Frontend

Frontend entry point: `frontend/app/page.tsx`.

The dashboard is a single-screen dispatch console:

- Top bar with demo controls
- Mapbox incident map
- Incident list and incident detail
- Infrastructure panel
- Snowflake tiles
- Cortex alert toasts
- SSE connection status

API calls live in `frontend/lib/api.ts`. SSE connects directly to
`NEXT_PUBLIC_BACKEND_URL/events` because Next.js dev rewrites buffer SSE.

## Data Flow

1. Demo button calls `/demo/trigger-call`.
2. Backend uses OpenAI extraction when configured, otherwise deterministic stubs.
3. Incident is triaged with deterministic scoring.
4. Incident is stored in memory.
5. Optional Snowflake writer queues an `incidents` row.
6. Backend publishes an `incident_created` SSE event.
7. Dashboard updates map, list, tiles, and alerts.

## Snowflake Integration

Current `main` supports:

- Optional Snowflake connection from `.env`
- Async Snowflake writer
- `scripts/snowflake_init.sql` for core tables
- `scripts/snowflake_smoke.py` for init, seed, and smoke checks
- Tile queries with in-memory fallback
- Cortex-style cluster scan with Snowflake query path and in-memory fallback

## Future Features

These are not implemented in `main` yet:

- Victim PWA
- Vite-based responder app
- Hono API service
- pnpm workspace layout
- Full Snowflake-native pipeline with Streams, Tasks, Dynamic Tables, H3, Cortex Search, Cortex Analyst, and Cortex Agents
- Human approval workflow for dispatch recommendations
