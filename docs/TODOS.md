# TODOS — Execution Board

Coordinator-facing TODOs for the 18h build. Use `docs/TASKS.md` for per-track checklists; use this file to decide what must happen next, what is blocked, and what gets cut when time is tight.

---

## Critical Path

### H0-H1.5 — Scaffold Gate

- [ ] One owner runs the template scaffold from `docs/TEMPLATE.md`.
- [ ] `pnpm install && pnpm dev` starts victim, responder, and API locally.
- [ ] `packages/types` exports the v1 contract before app/API feature work begins.
- [ ] `.env.example` is copied to `.env`; Snowflake, Mapbox, and `ADMIN_TOKEN` values are filled.

### H1.5-H3 — Contract Gate

- [ ] Snowflake `01_schema.sql` applies cleanly.
- [ ] `INCIDENTS_RAW`, physical `INCIDENTS_ENRICHED`, `RESPONDERS`, `ASSIGNMENTS`, `UNMET_RESOURCE_NEEDS`, `ROUTES`, and `INCIDENT_STREAM` exist.
- [ ] API `/health` boots and can run `SELECT 1` against Snowflake.
- [ ] `POST /v1/incidents` inserts one GPS-backed test incident into `INCIDENTS_RAW`.
- [ ] `GET /v1/dashboard/state` returns the typed snapshot shape, even if backed by fixtures.
- [ ] Track D publishes the final `SeverityResult` JSON schema, degraded fallback shape, and `required_resources` format.

### H3-H6 — First Vertical Slice

- [ ] One thin victim report reaches `INCIDENTS_RAW`.
- [ ] `TRIAGE_TASK` writes one row into physical `INCIDENTS_ENRICHED`.
- [ ] Dashboard hydrates normalized Zustand store from `/v1/dashboard/state`.
- [ ] Incident queue shows at least one enriched incident with score, category, reasons, and `triage_status`.

### H6-H12 — Prize Story Gate

- [ ] Cortex severity works on scenario rows.
- [ ] Embedding/vector dedup and geospatial clustering create visible clusters.
- [ ] Resource roster is configurable and represented in Snowflake.
- [ ] Greedy multi-resource dispatch creates `ASSIGNMENTS`.
- [ ] Missing responder types create visible `UNMET_RESOURCE_NEEDS`.
- [ ] Route polyline works through Mapbox or route fallback.

### H12-H16 — Demo Gate

- [ ] `Start Scenario` inserts 50 synthetic incidents over 60 seconds via API timing.
- [ ] Dashboard shows map pins, queue, side sheet, roster, assignments, and route drawer.
- [ ] `Inject Critical Incident` creates visible recompute/priority change.
- [ ] Snowflake worksheet is ready to show live tables/tasks/dynamic tables.
- [ ] API tests pass.
- [ ] `pnpm typecheck` passes.
- [ ] Snowflake smoke checklist passes.
- [ ] Demo dry-run completes within 4 minutes.

---

## Resolved Scope Decisions

- [x] `INCIDENTS_ENRICHED` is a physical table written by `TRIAGE_TASK`, not a Dynamic Table.
- [x] Victim app is a thin live submitter first; pre-reg, inventory, and offline depth are add-back scope.
- [x] Phone GPS is primary. Snowpark handles seeded `place_description` fallback only when GPS is unavailable.
- [x] Live Mapbox place search is stretch, not v1.
- [x] Dedup ships with Cortex embeddings + `VECTOR_COSINE_SIMILARITY`; true Cortex Search service is stretch.
- [x] Dispatch is greedy multi-resource with visible `UNMET_RESOURCE_NEEDS`; schema should stay optimizer-ready.
- [x] API owns 60-second scenario timing; Snowflake owns all processing after ingest.
- [x] Admin/roster mutation endpoints require `ADMIN_TOKEN`.
- [x] Severity parse failures produce visible degraded fallback, not silent defaults.
- [x] Leaflet fallback is cut; use route fallback, fixture mode, and screenshot/video backup.

---

## Track Dependencies

### Track A — Victim PWA

Depends on:
- [ ] `@disaster/types` contract from Phase 0.
- [ ] `POST /v1/incidents` by H3.
- [ ] `GET /v1/incidents/:id` by H7 for status page.

Cut first if behind:
- [ ] Pre-reg profile form.
- [ ] Inventory page and PATCH flow.
- [ ] Full offline queue semantics.
- [ ] PWA install polish.

### Track B — Responder Dashboard

Depends on:
- [ ] Snapshot shape from `GET /v1/dashboard/state`.
- [ ] SSE event envelope shape.
- [ ] Severity JSON shape and `triage_status`.
- [ ] `ASSIGNMENTS`, `UNMET_RESOURCE_NEEDS`, and route preview shape.

Build with fixtures until live data is ready:
- [ ] Normalized Zustand store.
- [ ] Map pins + queue + side sheet.
- [ ] Resource roster panel.
- [ ] Route drawer.

Cut first if behind:
- [ ] Framer Motion polish.
- [ ] Cluster merge animation.
- [ ] Analytics/H3 visualization tabs.

### Track C — API + Glue

Depends on:
- [ ] Snowflake schema by H2.
- [ ] Mapbox token for live polylines.
- [ ] Scenario JSON from Track D.

Must not slip:
- [ ] `/v1/incidents` validation + insert.
- [ ] `/v1/dashboard/state` typed snapshot.
- [ ] `/v1/stream` SSE.
- [ ] `/v1/admin/scenario/start`.
- [ ] `ADMIN_TOKEN` guard for admin/roster mutations.
- [ ] API tests with mocked Snowflake.

Fallbacks:
- [ ] If Mapbox Optimization fails, emit cached route or straight-line preview with `route_source='fallback'`.
- [ ] If Snowflake is late, responder dashboard can hydrate from fixture shape while Snowflake catches up.

### Track D — Snowflake + Scenario

Must not slip:
- [ ] `01_schema.sql`.
- [ ] `02_cortex_triage.sql` writes physical `INCIDENTS_ENRICHED`.
- [ ] Degraded fallback on malformed Cortex JSON.
- [ ] `03_dynamic_tables.sql` for clusters, roster, heatmap.
- [ ] `04_dispatch_proc.sql` for greedy multi-resource dispatch and unmet needs.
- [ ] `05_udf_location.py` for seeded place-description fallback.
- [ ] 50-row Texas flood scenario data.

Cut first if behind:
- [ ] True Cortex Search service/index.
- [ ] Snowflake scenario stored procedure.
- [ ] TensorMesh caching.
- [ ] Snowflake Native App packaging.

---

## Verification Gates

### API Tests

- [ ] `POST /v1/incidents` rejects missing `raw_text`.
- [ ] `POST /v1/incidents` accepts GPS-backed incident payload.
- [ ] `POST /v1/incidents` calls place-description resolver only when GPS is unavailable.
- [ ] Admin and roster mutation endpoints reject missing/wrong `ADMIN_TOKEN`.
- [ ] Snowflake transient failure returns `{ error: { code, message } }`.
- [ ] `GET /v1/dashboard/state` returns typed incidents/clusters/roster/assignments/routes.
- [ ] `POST /v1/admin/scenario/start` returns quickly while scheduling scenario inserts.

### Snowflake Smoke

- [ ] Apply SQL files in order.
- [ ] Insert 3 raw incidents.
- [ ] Confirm `INCIDENTS_ENRICHED` receives rows.
- [ ] Confirm malformed Cortex output creates `triage_status='degraded'`.
- [ ] Confirm clusters refresh.
- [ ] Confirm roster refreshes after responder status changes.
- [ ] Confirm dispatch creates assignments.
- [ ] Confirm depleted roster creates `UNMET_RESOURCE_NEEDS`.

### Demo Smoke

- [ ] Start scenario.
- [ ] Watch map populate.
- [ ] Open a high-severity incident side sheet.
- [ ] Show three AI reasons and required resources.
- [ ] Show duplicate cluster.
- [ ] Show roster decrement.
- [ ] Show route drawer with live or fallback route.
- [ ] Inject critical incident.
- [ ] Flip to Snowflake worksheet and show live receipts.

---

## Open Risks To Watch

- [ ] Snowflake Cortex region/access is not enabled. Fallback: pre-populate `INCIDENTS_ENRICHED` for demo and show SQL/prompt receipt.
- [ ] Dynamic Table refresh is slower than the demo. Fallback: manual refresh trigger or narrate latency while showing rows.
- [ ] Mapbox token or Optimization API fails. Fallback: cached or straight-line route preview.
- [ ] SSE reconnect creates duplicate UI rows. Prevention: normalized Zustand store with upsert reducers.
- [ ] Severity prompt returns malformed JSON. Prevention: visible degraded fallback.
- [ ] Team overbuilds victim PWA. Prevention: thin submitter first; add-back only after Snowflake/dashboard works.

---

## Deferred / Stretch

- [ ] ElevenLabs Conversational AI webhook.
- [ ] API-only live Mapbox place search for arbitrary business names.
- [ ] True Cortex Search service/index.
- [ ] TensorMesh caching.
- [ ] Full PWA offline sync semantics.
- [ ] 15-minute GPS ping tracking.
- [ ] Vercel/Railway deploy.
- [ ] Hospital/shelter map layer.
- [ ] Optimizer-style global dispatch.
- [ ] Leaflet fallback remains intentionally cut.
