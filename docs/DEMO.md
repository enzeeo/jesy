# Demo

## Prerequisites

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

## Demo Flow

1. Confirm backend is healthy at `http://localhost:8000/healthz`.
2. Open the dashboard.
3. Click the reset control.
4. Seed responders.
5. Trigger the Pier 4 immediate scenario.
6. Trigger the Banyan delayed scenario.
7. Trigger the Wailoa minor scenario.
8. Watch incidents appear through SSE.
9. Run route optimization.
10. Run Cortex Scan and show alert behavior.
11. Show Snowflake tiles. If credentials are missing, explain fallback mode.

## Snowflake Mode

Optional setup:

```bash
make snowflake-init
make snowflake-smoke
```

When Snowflake env vars are not configured, the demo still runs with no-op
writes and in-memory tile data.

## Future Features

Do not demo these as current `main` features:

- Victim PWA
- Separate responder Vite app
- Hono API
- pnpm workspace
- Cortex Agent chat
- Cortex Search and Analyst
- Streams/Tasks/Dynamic Tables pipeline
