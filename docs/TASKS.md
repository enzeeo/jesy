# TASKS — 4-Track Build Plan (18h)

> **Read order**: `PLAN.md` → `CONTEXT.md` → this file → your track section.
>
> **Before starting any track**: the template scaffold (per `docs/TEMPLATE.md`) must be merged to `main`. Pick one person to one-shot the scaffold in the first ~1.5h.

---

## Phase 0 — Template Scaffold (one person, ~1.5h)

Owner: TBD (person with most TS/monorepo experience).

See `docs/TEMPLATE.md` for exact spec. Output:
- Working `pnpm install && pnpm dev` runs all three apps locally.
- `packages/types` published internally with full type set from `CONTEXT.md §Domain Model`.
- `.env.example` complete.
- All 4 tracks can `git pull` and start without conflicts.

- [ ] pnpm workspace + root tsconfig + root scripts
- [ ] `packages/types` exports full domain model
- [ ] `apps/victim` Vite + React + Tailwind + PWA manifest stub runs
- [ ] `apps/responder` Vite + React + Tailwind + Mapbox import stub runs
- [ ] `services/api` Hono + Snowflake SDK + dotenv stub runs (health check route only)
- [ ] `snowflake/01_schema.sql` skeleton with empty tables
- [ ] `scenarios/texas-flood.json` with 3 example incidents (placeholder)
- [ ] `.env.example` complete
- [ ] CI: skip; local-only for hackathon
- [ ] Push to `main`. Tag `template-ready`.

---

## Track A — Victim PWA (1 person)

Owner: **___________**

### Hour-by-hour

**H0–H1: Onboard + Routing**
- [ ] React Router setup with routes: `/onboard`, `/`, `/incident`, `/status/:id`, `/inventory`, `/manual-location`
- [ ] Tailwind theme: dark mode default, high-contrast red/green/amber
- [ ] PWA manifest + install prompt
- [ ] Service worker stub (network-first, but queue POSTs on offline)

**H1–H3: Pre-reg flow**
- [ ] `pages/Onboard.tsx`: form (name, age, conditions multiselect, devices multiselect, emergency contact)
- [ ] Save to `localStorage` AND `POST /v1/profiles`
- [ ] Skip-able ("I'll do this later") — sets a `device_id` only
- [ ] On next launch, route to `/` if profile exists, else `/onboard`

**H3–H6: Home + incident submit**
- [ ] `pages/Home.tsx`: two huge buttons (Call / Text), prompt panel ("Things to say: where you are, what happened, who needs help, what you have, what you need")
- [ ] **Call button** = stub for v1 (alerts "voice coming soon"; nice-to-have wires to ConvAI). DO NOT block on this.
- [ ] **Text button** → `pages/Incident.tsx`
- [ ] `Incident.tsx`: textarea + dynamic checklist (medical / trapped / fire / water / shelter / power / evacuation), inventory have/need checklists
- [ ] On submit: capture GPS (`navigator.geolocation.getCurrentPosition`). If denied/timeout → route to `/manual-location`
- [ ] `POST /v1/incidents` then route to `/status/:id`

**H6–H8: Manual location fallback**
- [ ] `pages/ManualLocation.tsx`: textarea ("describe where you are — landmarks, cross-streets, building name")
- [ ] Pass description to `POST /v1/incidents` with `location.source = 'landmark_udf'`
- [ ] Show returned coords on a tiny Mapbox static-image preview with confidence radius

**H8–H10: Live status screen**
- [ ] `pages/Status.tsx`: poll `GET /v1/incidents/:id` every 5s
- [ ] Show severity score (big number, color-coded), category badge, 3 reasons, assigned responder type + ETA when available
- [ ] Inventory toggle component embedded for mid-incident updates

**H10–H12: Inventory page + polish**
- [ ] `pages/Inventory.tsx`: each device → toggle Have/Need
- [ ] PATCH `/v1/incidents/:id/inventory` on toggle
- [ ] Polish typography, button states, accessibility (aria-labels, focus rings)

**H12+: Stretch**
- [ ] 15-min GPS ping (`watchPosition`) when incident is open
- [ ] Wire Call button to ElevenLabs ConvAI agent (drop-in)
- [ ] Offline queue end-to-end test (DevTools offline → submit → reconnect → flushes)

### Deliverables
- `apps/victim` fully functional end-to-end with text submission
- All API contract types imported from `@disaster/types`
- No domain types defined inline

### Blockers / Dependencies
- Needs API track to have `/v1/profiles` and `/v1/incidents` stubbed by H3 (can mock against fixture JSON until then).

---

## Track B — Responder Dashboard (1 person)

Owner: **___________**

### Hour-by-hour

**H0–H1: Layout shell**
- [ ] `pages/Dashboard.tsx`: CSS grid layout per `PLAN.md §D15` (top bar, left/right sidebars, main map, bottom drawer)
- [ ] Tailwind dark mode, monospace numerics font (`font-mono` from Tailwind), red/amber/green severity palette
- [ ] Hardcoded login screen (`admin/admin` → set localStorage flag)

**H1–H3: Map base**
- [ ] `components/MapView.tsx`: Mapbox GL JS init, satellite-streets style, center on Houston (29.76, -95.37)
- [ ] `lib/map/mapbox.ts` adapter: `addPin`, `removePin`, `updateHeatmap`, `drawPolyline` interface
- [ ] Severity legend overlay top-right (corner card)

**H3–H5: Pin + heatmap layers**
- [ ] deck.gl MapboxOverlay
- [ ] `IconLayer` for incident pins, color by severity (red/orange/yellow/green)
- [ ] `HeatmapLayer` driven by `severity_heatmap_h3` data
- [ ] Cluster pins (`SCATTERPLOT` with size = total severity) when zoomed out; individual pins when zoomed in

**H5–H7: SSE + state**
- [ ] `lib/sse.ts`: `EventSource('/v1/stream')` with reconnect-on-error
- [ ] Zustand or Jotai store: `incidents[]`, `clusters[]`, `roster[]`, `assignments[]`, `routes[]`
- [ ] Reducers for each SSE event type
- [ ] On mount: `GET /v1/dashboard/state` for initial snapshot

**H7–H9: Sidebars + side sheet**
- [ ] `components/IncidentQueue.tsx` (right sidebar, sortable by severity desc, status filter)
- [ ] `components/IncidentSheet.tsx` (side sheet): transcript, summary, profile snippet, severity card with 3 reasons, required_resources chips, assigned unit + ETA, "Mark Resolved" button
- [ ] `components/FiltersPanel.tsx` (left sidebar): severity ≥ slider, category checkboxes, status, time window, responder dropdown

**H9–H11: Resource roster + stats bar**
- [ ] `components/ResourceRoster.tsx`: 7 rows (one per type), `available/total` numbers, color when fully busy
- [ ] `components/StatsBar.tsx` top: scenario name + elapsed timer + open count + resolved count + avg severity + responders dispatched
- [ ] Roster config modal on first load: set counts per type, `POST /v1/roster`

**H11–H13: Route drawer**
- [ ] `components/RouteDrawer.tsx` (bottom): on responder selection in filter, show ordered stop list with severity badges + ETA between stops + total ETA
- [ ] Draw polyline on map for that responder (different color per type)
- [ ] "Recompute" button → `POST /v1/admin/recompute-routes`

**H13–H15: Demo polish**
- [ ] Smooth pin entry animation (Framer Motion)
- [ ] Cluster merge animation when dedup fires
- [ ] Route recompute animation: old polyline fades, new one draws
- [ ] Toasts on new sev≥90 incident ("⚠ Critical incident, dispatching")

**H15+: Stretch**
- [ ] Leaflet adapter (`lib/map/leaflet.ts`) as fallback toggle
- [ ] H3 grid visualization toggle
- [ ] Analytics tab (severity histogram, resource utilization over time)

### Deliverables
- `apps/responder` consuming `@disaster/types` for everything
- Full visual flow from Start Scenario → pins land → clusters form → routes draw → resolve

### Blockers / Dependencies
- Needs API track to have SSE channel + `/v1/dashboard/state` by H5 (mock with local fixture until then).
- Needs Snowflake track to have severity output shape locked by H6.

---

## Track C — API + Glue (1 person)

Owner: **___________**

### Hour-by-hour

**H0–H1: Hono setup + Snowflake conn**
- [ ] `services/api/src/index.ts`: Hono app, CORS, JSON middleware
- [ ] `lib/snowflake.ts`: `snowflake-sdk` pool, `query<T>(sql, binds)` helper, key-pair auth (load PEM from env)
- [ ] `GET /health` returns `{ ok: true, snowflake: 'connected' }` after pool init

**H1–H4: Victim endpoints**
- [ ] `POST /v1/profiles` — upsert by `device_id`
- [ ] `GET /v1/profiles/:device_id`
- [ ] `POST /v1/incidents` — validate, if landmark-only call `UDF_RESOLVE_LANDMARK`, INSERT INTO `INCIDENTS_RAW`, return `{ incident_id, status }`
- [ ] `GET /v1/incidents/:id` — read from `INCIDENTS_ENRICHED` (joins severity)
- [ ] `PATCH /v1/incidents/:id/inventory`

**H4–H6: Dashboard endpoints**
- [ ] `GET /v1/dashboard/state` — single query gathering open incidents, clusters, roster, active assignments + routes
- [ ] `POST /v1/roster` — bulk upsert RESPONDERS rows
- [ ] `POST /v1/assignments/:id/status` — call `MARK_ON_SCENE` or `MARK_RESOLVED` stored proc

**H6–H9: SSE**
- [ ] `lib/sse.ts`: in-memory `Set<ResponseWriter>` of connected clients
- [ ] `GET /v1/stream` — sets text/event-stream headers, registers client
- [ ] Background poller (`setInterval` 2s): query `INCIDENTS_ENRICHED CHANGES(INFORMATION => APPEND_ONLY)` since last cursor, emit `incident_new`/`incident_update`
- [ ] Same poller for clusters, roster, assignments

**H9–H11: Mapbox routing client**
- [ ] `lib/mapbox.ts`: `optimizeRoute(origin, stops[])` → encoded polyline + total duration
- [ ] On `assignment_new` SSE event, queue a route computation; persist to `ROUTES` table; emit `route_update`

**H11–H13: Admin + scenario**
- [ ] `lib/scenarios.ts`: load JSON, schedule `setTimeout` per incident (staggered timestamps from file)
- [ ] `POST /v1/admin/scenario/start` — runs scheduler, returns ETA to completion
- [ ] `POST /v1/admin/scenario/inject` — single high-sev incident with auto-generated transcript
- [ ] `POST /v1/admin/recompute-routes` — re-fires dispatch + route compute

**H13–H15: Resilience + polish**
- [ ] Retry on Snowflake transient errors (3 attempts, exponential backoff)
- [ ] Structured logging (`pino`) with request IDs
- [ ] Error response shape: `{ error: { code, message } }`
- [ ] CORS allow-list from `.env`

**H15+: Stretch**
- [ ] Cloudflare Tunnel script for ElevenLabs webhook
- [ ] ElevenLabs ConvAI webhook handler: `POST /v1/webhooks/elevenlabs` parses transcript + extracted slots → same `INCIDENTS_RAW` shape

### Deliverables
- All endpoints from `CONTEXT.md §API Endpoints` working
- SSE channel emitting events as soon as Snowflake side updates
- Type-safe with `@disaster/types`

### Blockers / Dependencies
- Snowflake schema must be created by H1 (Track D priority).
- Mapbox token in `.env` (any team member can grab from mapbox.com).

---

## Track D — Snowflake + Scenario (1 person)

Owner: **___________**

### Hour-by-hour

**H0–H1: Account access + schema**
- [ ] Confirm Snowflake sponsor account access. Get warehouse name + DB + schema.
- [ ] Confirm Cortex AI is enabled in the region.
- [ ] Run `snowflake/01_schema.sql`: create `PROFILES`, `INCIDENTS_RAW`, `RESPONDERS`, `ASSIGNMENTS`, `ROUTES`, indexes, primary keys, `INCIDENT_STREAM`.
- [ ] Insert 1 row in each table for sanity check.

**H1–H3: Cortex triage SQL**
- [ ] `snowflake/02_cortex_triage.sql`: `TRIAGE_TASK` that runs on `INCIDENT_STREAM`
- [ ] Compose prompt for `SNOWFLAKE.CORTEX.COMPLETE` (claude-3-5-sonnet) with strict JSON schema for `SeverityResult`
- [ ] Test on 3 manually-inserted incidents; verify JSON parses

**H3–H6: Dynamic Tables**
- [ ] `snowflake/03_dynamic_tables.sql`:
  - `INCIDENTS_ENRICHED` (joins triage output, summary, embedding, profile)
  - `INCIDENT_CLUSTERS` (`ST_CLUSTER_KMEANS` + `VECTOR_COSINE_SIMILARITY` dedup)
  - `RESOURCE_ROSTER` (rollup from RESPONDERS by type)
  - `SEVERITY_HEATMAP_H3` (H3 bucket aggregates)
- [ ] Confirm `TARGET_LAG = '15 seconds'`; check `last_refresh_status = SUCCEEDED`

**H6–H9: Dispatch stored proc**
- [ ] `snowflake/04_dispatch_proc.sql`: `DISPATCH_INCIDENTS()` procedure
  - For each open incident (ORDER BY severity DESC):
    - Find required resources from severity JSON
    - For each required type, find nearest available responder (`ST_DISTANCE`)
    - If found, INSERT INTO ASSIGNMENTS, UPDATE RESPONDERS SET status='busy'
- [ ] `DISPATCH_TASK` scheduled every 30s + manually triggered by API

**H9–H11: Snowpark UDF for location**
- [ ] `snowflake/05_udf_location.py`: `UDF_RESOLVE_LANDMARK(description, last_lat, last_lng)`
  - Use `_snowflake.snowpark_python.SnowflakeFile` to call Cortex from Python? No — call SNOWFLAKE.CORTEX.COMPLETE via `session.sql(...)` inside the UDF
  - Parse JSON response: `{ lat, lng, confidence, reasoning }`
  - Fallback: return `(last_lat, last_lng, 0.3, 'fallback to last GPS')` on parse error
- [ ] Register UDF, test with 5 sample landmark descriptions

**H11–H13: Scenario data**
- [ ] Author `scenarios/texas-flood.json` (50 incidents): vary location (across Houston grid), severity (15 critical, 20 medium, 15 low), category mix (10 medical, 8 trapped, 12 water, 6 fire, 4 power, 5 shelter, 5 evacuation)
- [ ] Write `snowflake/06_scenario_proc.sql`: `START_SCENARIO(name)` — reads from a staging table or VARIANT input, inserts staggered
- [ ] Alternatively: API loads JSON and calls direct INSERTs (simpler; pick this)

**H13–H15: End-to-end smoke**
- [ ] Trigger scenario via API → watch `INCIDENTS_RAW` fill → confirm Cortex fires → check `INCIDENTS_ENRICHED` populates → confirm clustering happens → confirm dispatch fires
- [ ] Tune `TARGET_LAG` if too slow; add manual `REFRESH` triggers in API after scenario start to force fast first-pass

**H15+: Stretch**
- [ ] Cortex Search index instead of cosine similarity (proper Search API)
- [ ] TensorMesh caching wrapper around `CORTEX.COMPLETE`
- [ ] Snowflake Native App packaging (skip, way too much for 18h)

### Deliverables
- Apply-in-order SQL files in `snowflake/`
- README in `snowflake/` with apply instructions
- Confirmed end-to-end pipeline: insert → enriched within 30s
- 50-incident scenario JSON ready to play

### Blockers / Dependencies
- None — start at H0, you are critical path.
- Coordinate severity JSON shape with Track B (responder) by H3.

---

## Cross-Track Sync Points

| Hour | Sync                                                                     |
| ---- | ------------------------------------------------------------------------ |
| H1.5 | Template merged. All 4 tracks pull, run, start.                          |
| H3   | Track D shares final severity JSON shape. Tracks B/C lock contract.      |
| H6   | First end-to-end: victim text → API → Snowflake row visible. Track A+C+D demo together. |
| H9   | First Cortex severity visible in dashboard. Track A+B+C+D check pipeline. |
| H12  | Dispatch + routes visible. Full pipeline demo internally. Stretch decisions go/no-go. |
| H14  | Demo dry-run. Record + retake.                                           |
| H16  | Code freeze. Polish slide deck, prepare laptops.                         |
| H18  | Present.                                                                 |

---

## Definition of Done

- Judge can press "Start Scenario" → see 50 incidents flood the map in 60s.
- Judge can click any pin → see Cortex-generated severity + 3 reasons.
- Judge can see clusters auto-merging.
- Judge can watch routes recompute on `inject` button.
- Judge can see resource roster decrement live.
- Snowflake worksheet is on standby to show actual SQL + Dynamic Tables refreshing.
- All 6 Snowflake features can be pointed at on screen.

If any of the above is broken at H16, **prioritize fixing over polish**.
