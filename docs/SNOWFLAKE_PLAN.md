# Snowflake Plan

## Current Main-Branch Status

Snowflake is optional in `main`. The app runs without Snowflake credentials.
When credentials are configured, the backend can write operational rows and run
tile/Cortex-style queries. When credentials are missing or connection fails, the
backend falls back to no-op writes and in-memory tile/scan data.

Current files:

- `src/disaster/snowflake/connection.py`
- `src/disaster/snowflake/writer.py`
- `src/disaster/snowflake/tiles.py`
- `src/disaster/snowflake/live_ops.py`
- `src/disaster/snowflake/cortex.py`
- `src/disaster/app/routes/tiles.py`
- `src/disaster/app/routes/cortex.py`
- `scripts/snowflake_init.sql`
- `scripts/snowflake_keypair_setup.py`
- `scripts/snowflake_smoke.py`

Current schemas/tables from `scripts/snowflake_init.sql`:

- `RAW`, `CLEAN`, `GEO`, `FEATURES`, `SERVING`, and `AGENT`
- Runtime writes include incident submissions, voice calls, responders,
  dispatches, route recommendations, route legs, pings, arrivals, Cortex
  alerts, and app-managed agent runs.
- Optional 1-minute dynamic tables:
  - `GEO.LIVE_INCIDENT_H3`
  - `FEATURES.LIVE_H3_CLUSTER_WINDOWS`
  - `FEATURES.LIVE_ROUTE_STATUS`
  - `SERVING.LIVE_RESOURCE_GAPS`

Current commands:

```bash
make snowflake-init
make snowflake-smoke
```

## Current Behavior

- Incident creation can queue rows for Snowflake.
- Voice intake can queue incident and voice call data.
- Route optimization can queue responder dispatch rows.
- Snowflake tile endpoints can query Snowflake or compute in memory.
- Cortex scan can use a Snowflake query runner or in-memory clustering fallback.
- `/snowflake/ops` returns app-managed live ops cards from `AGENT.AGENT_RUNS`,
  live dynamic tables, or in-memory fallback data.
- A FastAPI scheduler runs Cluster Monitor, Resource Gap Monitor, and
  Supervisor Agent once per minute when Snowflake is configured.
- CortexChat includes recent live ops agent output in its warehouse-grounded
  answers.
- Key-pair auth is supported through `scripts/snowflake_keypair_setup.py`.

## Future Features

The following Snowflake concepts are not implemented on `main` yet and should be
treated as roadmap items:

- Native Cortex Agent responder command center
- Global chat, incident-dot chat, cluster chat, and dispatch approval chat
- Cortex Search over enriched incident reports
- Cortex Analyst Semantic Views
- AISQL extraction/classification/summarization pipeline
- Streams and Tasks enrichment pipeline
- More advanced Dynamic Tables for live serving views
- H3/geospatial route coverage beyond the v1 live incident H3 table
- Snowpark Python UDFs
- Human-approved dispatch recommendation workflow
- Feedback labels for future Snowpark ML
- Specialist agents for severity, location confidence, duplicate review, dispatch review, and clinical risk review

## Future Target

Longer term, Snowflake should become the governed operational layer:

1. Raw submissions enter Snowflake.
2. Enrichment creates normalized incident reports.
3. Clustering and resource-gap jobs update serving tables.
4. A dispatch recommendation is generated.
5. A responder approves, rejects, or overrides.
6. Feedback is stored for evaluation and future model training.

Clinical output must stay responder-only: risk flags, missing-information prompts,
and escalation cues. It must not provide diagnosis, treatment plans, or
victim-facing medical advice.
