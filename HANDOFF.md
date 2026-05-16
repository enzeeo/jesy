# Handoff Summary

## Current Status

The repo is still in planning/scaffold stage for the Disaster Relief Triage hackathon project. No application code has been implemented yet. The docs now contain a sharper execution plan for an 18-hour, 4-person build, with a coordinator-facing TODO board in `docs/TODOS.md`.

The latest planning session focused on resolving vague or conflicting scope in the docs, especially around Snowflake ownership, victim app scope, dispatch semantics, API/security boundaries, and demo fallbacks.

## Completed This Session

- Clarified that `INCIDENTS_ENRICHED` is a physical table written by `TRIAGE_TASK`, not a Dynamic Table.
- Renamed ambiguous "landmark" fallback language to **Place description**.
- Clarified location flow: phone GPS is primary; Snowpark handles seeded Houston place-description fallback only when GPS is unavailable.
- Made live Mapbox place search an optional/stretch add-on, not v1.
- Right-sized victim app scope to a thin live submitter first.
- Defined v1 demo truth boundary: synthetic scenario input is okay, but Snowflake processing must be live.
- Defined dispatch semantics: greedy multi-resource assignment with visible `UNMET_RESOURCE_NEEDS`, while keeping schema optimizer-ready.
- Clarified scenario playback: API controls 60-second demo timing; Snowflake owns all processing after each insert.
- Added `ADMIN_TOKEN` API boundary for admin/roster mutations.
- Added visible degraded fallback for malformed Cortex severity output via `triage_status='degraded'`.
- Cut Leaflet fallback. Fallbacks are route fallback, fixture mode, and screenshot/video backup.
- Added API tests and smoke verification gates to the plan.
- Added `docs/TODOS.md` as the cross-track execution board.

## Files Changed

| File | Purpose |
|---|---|
| `docs/CONTEXT.md` | Added domain language, clarified data flow, physical enriched table, dispatch/unmet needs, auth boundary, place-description UDF. |
| `docs/PLAN.md` | Added demo truth boundary, verification standard, revised locked decisions, honest Cortex embeddings wording, narrowed victim/snowflake/map scope. |
| `docs/TASKS.md` | Added H0-H3 critical path, revised Track A scope, normalized dashboard state, API tests, Snowflake fallback behavior, dispatch details. |
| `docs/TODOS.md` | New coordinator-facing execution board with critical path, dependencies, verification gates, risks, and deferred scope. |
| `docs/TEMPLATE.md` | Updated scaffold spec for physical `INCIDENTS_ENRICHED`, `UNMET_RESOURCE_NEEDS`, API tests, place-description source, optional scenario helpers. |
| `docs/STACK.md` | Clarified Snowpark is for GPS-missing place-description resolution against seeded Houston data. |
| `docs/DEMO.md` | Updated demo language to avoid overclaiming Cortex Search; added route fallback and screenshot/video fallback. |
| `HANDOFF.md` | This handoff summary. |

## Commands Run

```bash
git remote get-url origin 2>/dev/null; git branch --show-current; git log --oneline -30; git diff origin/main --stat 2>/dev/null || git diff main --stat 2>/dev/null || true; git stash list
```

Result:

```text
Showed GitHub remote, branch `enzeeo`, recent docs commits, and an initial docs-heavy diff earlier in the session.
```

```bash
git status --short && git diff --stat
```

Result:

```text
Returned no visible output when rerun before this handoff, suggesting the working tree was clean before adding HANDOFF.md.
```

```bash
rg "Demo Truth Boundary|Resolved Scope Decisions|place_description_udf|UNMET_RESOURCE_NEEDS|triage_status|Critical Path — H0" docs
```

Result:

```text
Confirmed the clarified decisions are present in project docs.
```

```bash
rg "landmark_udf|UDF_RESOLVE_LANDMARK|Leaflet|leaflet|Cortex Search dedups|START_SCENARIO bulk|INCIDENTS_ENRICHED \\+ INCIDENT|Tests \\(we are not writing tests" docs
```

Result:

```text
Only intentional Leaflet-cut references remained in docs/TODOS.md.
```

## Tests and Checks

- `pnpm typecheck`: not run.
- API tests: not run; no application code exists yet.
- Snowflake smoke checklist: not run; SQL not implemented yet.
- Doc consistency searches: run with `rg`; no stale `landmark_udf`, old UDF name, or false Cortex Search demo phrasing remained.

## Important Decisions

- `INCIDENTS_ENRICHED` is task-written physical storage; Dynamic Tables derive clusters, roster, and heatmap.
- **Place description** means free-text location fallback like nearby restaurants, gas stations, hospitals, schools, shelters, or cross-streets.
- Do not attempt arbitrary live business/place search in Snowpark v1. Use seeded Houston data; Mapbox place search is stretch.
- Cortex dedup ships as embeddings + vector similarity. True Cortex Search service/index is stretch only after Snowflake account feasibility is proven.
- Victim PWA v1 is one live submitter flow: report form + GPS/place fallback + status page.
- The demo can use synthetic scenario "calls," but those rows must flow through the real API/Snowflake ingest and processing path.
- Dispatch assigns per required resource type, allows partial assignment, and records `UNMET_RESOURCE_NEEDS`.
- Admin/roster mutation endpoints require `Authorization: Bearer $ADMIN_TOKEN`.
- Malformed Cortex severity output must be visible as degraded state, not silently hidden.

## Known Issues

- Snowflake Cortex access/region is still unverified.
- True Cortex Search service/index feasibility is unknown and intentionally stretch.
- Snowpark seeded place-description matching still needs concrete `PLACES` table/schema and fuzzy-match algorithm.
- Exact API route contracts, request/response schemas, and test file layout still need grilling.
- Responder UI states are not fully specified for loading, empty, degraded, partial assignment, SSE reconnect, and fixture/live mode.
- Deployment/local demo rig is still under-specified.
- No code or tests have been implemented yet.

## Open Areas Worth Grilling Next

1. Exact API contracts: payloads, response shapes, error codes, Zod schemas, and API test files.
2. Snowflake SQL feasibility: schema details, `TRIAGE_TASK`, Cortex JSON parsing, vector type support, Dynamic Table syntax, dispatch proc syntax.
3. Place-description resolver: `PLACES` seed data shape, matching logic, confidence scoring, fallback UX when confidence is low.
4. Responder dashboard states: loading, empty, SSE reconnect, duplicated events, degraded triage, unmet resources, route fallback, fixture mode.
5. Scenario data model: whether scenario rows remain JSON-only or also get loaded into a Snowflake table for receipts.
6. Demo operations: exact local ports, startup script, reset script, Snowflake worksheet queries, backup screenshots/video.
7. Security story: admin token handling, device ID scoping, PII boundaries, and what not to claim in a judge Q&A.
8. Cut lines: what gets dropped at H6/H9/H12 if Snowflake, API, or dashboard is behind.

## Next Recommended Steps

1. Grill API contracts first, then update `docs/TASKS.md` and `docs/TODOS.md` with exact endpoint schemas and test cases.
2. Grill Snowflake SQL feasibility before implementation, especially Cortex JSON parsing and Dynamic Table syntax.
3. Define `PLACES` schema and 10-20 seed examples for the Houston demo.
4. Create the pnpm monorepo scaffold from `docs/TEMPLATE.md`.
5. Implement the H0-H3 contract gate before building dashboard polish.
