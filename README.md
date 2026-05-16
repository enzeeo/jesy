# Disaster Relief Triage

> Real-time disaster triage powered by Snowflake AI. Hackathon project — Texas Flash Flood scenario.

## What this is

A two-sided platform:

- **Victim PWA** — anonymous one-tap entry point for people who need help. Captures situation, location, profile, and needs. Works under low signal.
- **Responder dashboard** — live command-center map for first responders. Auto-clustered incidents, AI-scored severity with explanations, dynamic dispatch of police / fire / EMT / paramedic / nurse / doctor / volunteer units.
- **Snowflake brain** — Cortex AI for severity + summarization, Cortex Search for vector dedup, Streams + Tasks for auto-triage, Dynamic Tables for live aggregates, Geo functions for clustering + routing, Snowpark Python UDFs for landmark-based location fallback.

## Why this exists

During large-scale disasters, individual victims can't reach overwhelmed call centers, and responders lack a macro picture. Triage breaks down. This system flips that: every report is captured, AI-scored, deduplicated, geo-clustered, and dispatched to the nearest appropriate unit — automatically.

## Read these first

| File              | Purpose                                                              |
| ----------------- | -------------------------------------------------------------------- |
| `docs/PLAN.md`    | The design doc. All decisions D1–D19. Must-haves vs nice-to-haves.   |
| `docs/CONTEXT.md` | Architecture, data flow, domain model, repo layout, conventions.    |
| `docs/STACK.md`   | Tech choices with versions and rationale.                            |
| `docs/TASKS.md`   | Hour-by-hour 4-track build plan with checkboxes.                     |
| `docs/TEMPLATE.md`| Step-by-step scaffold spec for the initial template build.           |
| `docs/DEMO.md`    | 4-minute judge script + Q&A prep + backup plan.                      |

## Quick start (after template is scaffolded)

```bash
# 1. Install
# If pnpm asks whether to reinstall modules from scratch, answer Y
# or force a non-interactive yes (example):
#   yes | pnpm install
pnpm install

# 2. Copy env template and fill in
cp .env.example .env
# edit .env with Snowflake + Mapbox credentials

# 3. Apply Snowflake SQL (one-time)
# Open snowflake/01_schema.sql in Snowflake worksheet, run.
# Repeat for 02 → 06 in order. See snowflake/README.md.

# 4. Run everything
pnpm dev

# 5. Open in browser
# Victim PWA:     http://localhost:5173
# Responder dash: http://localhost:5174
# API:            http://localhost:8787/health
```

## Team

| Track | Owner | What they own |
| ----- | ----- | -------------- |
| A     | TBD   | `apps/victim` PWA — Vite + React + Tailwind + service worker |
| B     | TBD   | `apps/responder` dashboard — Mapbox + deck.gl + SSE consumer |
| C     | TBD   | `services/api` — Hono + Snowflake SDK + SSE publisher + Mapbox routing |
| D     | TBD   | `snowflake/` SQL + Snowpark UDF + scenario data + dispatch logic |

## Snowflake features showcased

1. **Cortex AI** (`CORTEX.COMPLETE`) — severity scoring + required-resource extraction
2. **Cortex Search** (`CORTEX.EMBED_TEXT_768` + `VECTOR_COSINE_SIMILARITY`) — vector dedup of duplicate reports
3. **Streams + Tasks** — CDC auto-triage pipeline
4. **Dynamic Tables** — live heatmap aggregates + resource roster + cluster view
5. **Geospatial** (`ST_CLUSTER_KMEANS`, `ST_DISTANCE`, `H3_LATLNG_TO_CELL`)
6. **Snowpark Python UDF** — landmark-to-coordinates reasoning fallback

## Status

Phase 0 — Monorepo scaffold + Fixture UI Preview for victim + responder is in the tree.

See `docs/PLAN.md` for the full status, locked decisions, and risk register.

### Install issues

This repo expects **pnpm 9** (`corepack prepare pnpm@9.12.0 --activate`). If `pnpm install` hangs or fails:

1. Use a working network/VPN and retry.
2. If prompted *“The modules directories will be removed and reinstalled from scratch”*, confirm **Y** or run `yes | pnpm install` in a terminal.
3. After a successful install, run `pnpm typecheck` and `pnpm test` to verify all packages.

The applications still need `node_modules` to run `pnpm dev` or to typecheck React/Vite imports—there is no way to execute Vite without installing dependencies.

If install fails with missing files under `node_modules/.pnpm` (for example `ENOENT .../nanoid/package.json`), wipe and reinstall:

```bash
rm -rf node_modules apps/*/node_modules services/*/node_modules packages/*/node_modules
pnpm install
```
