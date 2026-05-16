# Disaster Response Coordination (Hilo Dispatch)

AI-driven emergency dispatch console for a contained geographic area (5km coastal
radius around Hilo, Hawaii). Hackathon demo, 90-second flow.

## What it does

- **Voice intake** via OpenAI extraction from a transcript → structured `IncidentReport`
- **Triage** via deterministic START protocol (pure Python, fixture-tested)
- **Routing** via greedy nearest-responder (shown live) + OR-Tools VRP (writeup)
- **Map** with severity-colored incidents + clustered at scale + animated routes
- **Simulator** generates 200 synthetic Hilo-tsunami incidents at disaster scale
- **Snowflake** for incident ingest + 5 live analytical tiles + Cortex SQL clustering
- **SSE** stream pushes everything to the dashboard in real time

## Architecture

```
   ElevenLabs (or /demo/trigger-call)
        │ transcript
        ▼
  POST /intake/voice ─▶ extract (OpenAI) ─▶ /triage/score ─▶ store ─▶ Snowflake (async)
        │                                                        │
        │                                                        ▼
        │                                                  /events (SSE)
        ▼                                                        │
  /incidents store ◀────────────── DisasterSimulator       /sim/start ─┘
        │                          (200 incidents, 60s window)
        ▼
  /routing/optimize (greedy + OR-Tools fallback)
        │
        ▼
  Next.js dashboard (Mapbox cluster + severity flash + Snowflake tiles + Cortex toast)
```

## Quick start

```bash
# 1. Backend
make install                       # uv sync
cp .env.example .env               # add OPENAI_API_KEY for real extraction
make dev                           # uvicorn on :8000

# 2. Frontend (separate terminal)
cp frontend/.env.example frontend/.env.local   # add NEXT_PUBLIC_MAPBOX_TOKEN
make frontend-install              # npm install
make frontend-dev                  # next dev on :3000

# 3. Open http://localhost:3000 and click "Seed Responders" then "Start Sim".
```

## Required env vars

| Var | Required? | What happens if missing |
|---|---|---|
| `OPENAI_API_KEY` | for real LLM | `/intake/voice` returns 503; `/demo/trigger-call` falls back to stub extraction |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | for the map | Frontend shows "Mapbox token missing" message |
| `ELEVENLABS_WEBHOOK_SECRET` | for prod | Dev mode allows unsigned webhooks (warning logged) |
| `SNOWFLAKE_*` | for live tiles | Writer is no-op; tiles + Cortex fall back to in-memory computation |

The demo works end-to-end with **only `OPENAI_API_KEY` + `NEXT_PUBLIC_MAPBOX_TOKEN`**.

## Snowflake setup (optional but real)

**Key-pair auth (recommended for teams).** Each developer generates their own
private key locally; the account owner registers the public key once per user.
No shared passwords, no secrets in `.env` beyond a file path.

```bash
# Each developer runs once:
uv run python scripts/snowflake_keypair_setup.py --user YOUR_SNOWFLAKE_USER
```

The script:
1. Generates an RSA 2048 keypair in `~/.snowflake/` (chmod 600, gitignored)
2. Prints the `ALTER USER ... SET RSA_PUBLIC_KEY=...` SQL to send to whoever
   owns the Snowflake account
3. Prints the env vars to copy into your `.env`

Then verify:

```bash
make snowflake-init          # creates 4 tables + seed rows + runs all queries
make snowflake-smoke         # idempotent re-run; verifies schema + every tile + cortex SQL
```

`scripts/snowflake_smoke.py` prints which auth method it's using
(`key-pair` or `password`). Password auth (`SNOWFLAKE_PASSWORD`) still works
as a fallback for solo dev / hackathon prototyping, but key-pair is preferred
for any shared account.

`scripts/snowflake_init.sql` is the source of truth for the DDL. The 4 tables:
- `incidents` — every IncidentReport write (append-only fact table)
- `voice_calls` — per-call extraction metadata (model used, token count)
- `responder_dispatches` — dispatch events (writer hookup pending from `/routing/optimize`)
- `cortex_alerts` — pattern-detection alerts emitted by `/cortex/scan`

When the warehouse is configured:
- All 5 `/snowflake/tile/{name}` endpoints query Snowflake directly (`PERCENTILE_CONT`, `DATEADD`, etc.); `source` field in the response reads `"snowflake"`.
- `/cortex/scan` runs `CORTEX_CLUSTER_SQL` (real SQL clustering over `incidents`) instead of the in-memory matcher.
- Writes batch via the async queue worker; never block the request path.
- On any Snowflake error mid-demo, the in-memory fallback kicks in automatically.

## Demo flow (90 seconds)

1. **0–5s** — Dashboard opens. Empty map. "3 units staged. Awaiting incidents."
2. **5–10s** — Click "Seed Responders". 4 responder dots appear at Hilo HQ.
3. **10–25s** — Click "Call: pier4_immediate". Voice intake → IMMEDIATE red dot at Pier 4.
4. **25–35s** — Click "Call: banyan_delayed" and "Call: wailoa_minor". List populates.
5. **35–60s** — Click "Start Sim". 200 incidents arrive on temporal curve, cluster on the map.
6. **60–70s** — Click "Optimize". Routes computed. Snowflake tiles tick.
7. **70–80s** — Click an incident dot → detail panel opens. Click "IMM" to escalate. Map dot flashes red + halo, list row pulses.
8. **80–90s** — Click "Cortex Scan". Toast slides in: "Trauma complaints clustering in SOUTH sector".

## API

```
POST /incidents                       create (auto-triage + broadcast)
GET  /incidents                       list
GET  /incidents/{id}                  single
POST /incidents/{id}/escalate         severity upgrade → severity_upgraded SSE
POST /triage/score                    pure scoring
POST /intake/voice                    HMAC-verified voice webhook (full LLM pipeline)
POST /routing/optimize                greedy + ?prefer_vrp=true for OR-Tools
GET  /events                          SSE stream
GET  /healthz                         liveness
GET  /responders                      list responder units

POST /sim/start                       run simulator
POST /sim/stop
GET  /sim/status

GET  /snowflake/tile/{name}           one of: severity_distribution, incident_rate,
                                      response_time_percentiles, geographic_equity,
                                      extraction_confidence
GET  /snowflake/tiles                 list available tiles
POST /cortex/scan                     run pattern detection (Snowflake SQL or in-memory),
                                      emit cortex_alert SSE; response includes "source"

POST /demo/seed-responders            populate ALS-1/2, BLS-1, FIRE-1 at HQ
POST /demo/trigger-call?scenario=...  fire a pre-recorded transcript
                                      (pier4_immediate, banyan_delayed, wailoa_minor)
GET  /demo/scenarios
POST /demo/reset                      wipe in-memory state
```

OpenAPI/Swagger at http://localhost:8000/docs

## Testing

```bash
make test       # 184 tests, ~24s
make lint       # ruff
make check      # both
```

## Project layout

```
src/disaster/
  models/       # IncidentReport, Victim, ResponderUnit, Severity (strict pydantic)
  triage/       # Pure START scorer + priority modifiers
  llm/          # OpenAI client + extractor + byte-identity-pinned prompt
  routing/      # Greedy + OR-Tools VRP + top-level optimize() with fallback
  snowflake/    # Async writer + connection helper + tile queries + Cortex SQL + matcher
  simulator/    # DisasterSimulator + Hilo tsunami profile (deterministic seed)
  events.py     # SSE broker with monotonic sequence_id
  store.py      # In-memory IncidentStore + ResponderStore (sim-replay idempotent)
  app/
    main.py     # FastAPI factory + lifespan
    deps.py     # AppState bag
    exception_handler.py
    middleware.py    # ElevenLabs HMAC verification
    routes/          # incidents, triage, intake, routing, events, sim, tiles, cortex, demo

frontend/
  app/             # Next.js App Router pages
  components/      # Map, IncidentList, IncidentDetail, InfraPanel, SnowflakeTiles, CortexToasts, TopBar
  lib/             # types, severity, api, useSSE, useSeverityFlash (P1 #8)

scripts/
  snowflake_init.sql    # idempotent DDL for all 4 tables
  snowflake_smoke.py    # connect + verify schema + run every query + seed rows

tests/             # 184 tests; pytest + pytest-asyncio
DESIGN.md          # design tokens + motion specs
```

## Design system

See `DESIGN.md`. Tokens are mirrored in `frontend/tailwind.config.ts`.

## What's intentionally not in scope

- ElevenLabs Conversational AI agent setup (use `/demo/trigger-call` to simulate)
- Real multi-agency mutual aid
- Mobile/responsive UI (single-viewport 1280×720 minimum)
- Authentication (single-dispatcher demo)
- Production scale (in-memory store, no migrations)
