# Plan

## Main-Branch Goal

Keep the existing FastAPI + Next.js disaster response demo coherent, runnable,
and Snowflake-ready without documenting branch-only app scaffolds as current
behavior.

## Current Scope

- Responder dashboard only
- Hilo demo scenarios
- Voice/transcript intake through backend routes
- Deterministic triage scoring
- Live incident updates through SSE
- Route optimization with greedy and optional VRP solver
- Optional Snowflake persistence and tile queries
- Optional OpenAI extraction

## Out Of Current Scope

See Future Features. These should not be treated as shipped in `main`.

## Implementation Priorities

1. Keep backend and dashboard quick-start reliable.
2. Keep the demo usable without external credentials.
3. Preserve Snowflake optionality through graceful fallbacks.
4. Keep clinical behavior as responder decision support, not medical advice.
5. Add tests around behavior before changing routing, triage, or event flow.

## Risks

- Snowflake credentials are optional, so docs and UI must be clear about fallback mode.
- OpenAI extraction is optional, so demo controls must keep deterministic stubs.
- SSE must stay direct-to-backend in dev because Next.js rewrites can buffer streams.
- Route optimization should continue to return useful output if OR-Tools cannot solve a case.

## Future Features

- Separate victim-facing intake app
- Separate responder app outside `frontend`
- Node/Hono API
- pnpm monorepo
- Snowflake SQL module directory
- Cortex Agent responder command center
- Cortex Search evidence retrieval
- Cortex Analyst Semantic Views
- Streams and Tasks enrichment pipeline
- Dynamic Tables serving layer
- H3/geospatial clustering pipeline
- Snowpark Python UDFs
- Human-approved dispatch recommendations
