# TASKS — 4-Track Build Plan (18h)

> **Read order**: `PLAN.md` → `CONTEXT.md` → this file → your track section.
>
> **Before starting any track**: the template scaffold (per `docs/TEMPLATE.md`) must be merged to `main`. Pick one person to one-shot the scaffold in the first ~1.5h.

---

## Phase -1 — Fixture UI Preview (one person, ~2-3h)

Owner: TBD (person with strongest UI taste).

Goal: validate expected UI and demo choreography before real API/Snowflake exists. This phase uses the full pnpm monorepo skeleton, but only `apps/victim`, `apps/responder`, and `packages/types` need real implementation depth; `services/api` and `snowflake/` can remain stubs. This phase can use local mock data for everything, gives victim and responder previews equal polish, and must keep fixture/live boundaries visible in code and docs.

- [ ] Create 12 curated fixture incidents with full Synthetic Profiles covering critical, medium, low, duplicate cluster, degraded triage, partial assignment, unmet resource need, route fallback, and victim status states.
- [ ] Put shared preview data in `packages/fixtures`; keep `scenarios/texas-flood.json` for final 50-row API/Snowflake scenario later.
- [ ] Add local fixture controls: Start Scenario, Inject Critical Incident, Reset Scenario, 4x Speed, and Step Through.
- [ ] Script fixture events over 60 seconds by default, with 4x and step-through modes, so 12 curated incidents, queue rows, roster changes, clusters, and route updates appear in demo order.
- [ ] Route UI data through typed adapters: `fixture` implementation now, `api` implementation later, selected by `VITE_DATA_MODE=fixture|api` with `fixture` as default.
- [ ] Define shared Tailwind tokens for severity, resource types, typography, spacing, and focus states.
- [ ] Build polished responder dashboard from fixtures: top stats, map pins/heatmap placeholder, right incident queue, incident sheet, roster panel, route drawer.
- [ ] Optimize responder preview for laptop/desktop fullscreen; acceptable degradation elsewhere is enough.
- [ ] Responder preview must visibly cover degraded triage chip, partial assignment, unmet need, route fallback, reconnect/fixture badge, and duplicate cluster merge.
- [ ] Make fixture map Mapbox-capable when `VITE_MAPBOX_TOKEN` exists, with a CSS/SVG Houston fallback when no token is present.
- [ ] Build polished victim PWA flow from fixtures: home, lightweight skippable profile, inventory chips, text incident form, manual location screen, status screen, and emergency copy tone.
- [ ] Optimize victim preview for mobile portrait; acceptable desktop preview is enough.
- [ ] Victim status screen covers Received, Being triaged, Help assigned with ETA, Low-confidence location, and Unmet resource states without exposing responder-only internals.
- [ ] Add preview shortcuts: `/demo` in responder opens dashboard with fixture controls; `/demo` in victim opens a populated fast path through the fixture flow.
- [ ] Apply split tone: responder is dense dark command center; victim is calm high-contrast mobile aid flow.
- [ ] Add a visible fixture/live indicator in responder UI and victim status screen.
- [ ] Use the same domain shapes planned for `@disaster/types` so fixture work becomes contract scaffolding, not throwaway model drift.
- [ ] Capture screenshots or a short screen recording for UI review before starting real API/Snowflake integration.

Exit criteria:
- Mock dashboard communicates the 4-minute judge story without backend.
- Mock victim flow feels equally demo-ready, including skippable profile context and inventory chips, not a placeholder.
- Start/Inject/Reset/4x/Step controls work without API/Snowflake.
- Screenshots are captured for both `/demo` flows.
- Stop fixture polish after one good pass; move to real API/Snowflake pipeline work.
- Any unclear UI state is written back to `docs/TODOS.md` before scaffold work begins.

---

## Phase 0 — Template Scaffold (one person, ~1.5h)

Owner: TBD (person with most TS/monorepo experience).

See `docs/TEMPLATE.md` for exact spec. Output:
- Working `pnpm install && pnpm dev` runs all three apps locally.
- `packages/types` published internally with full type set from `CONTEXT.md §Domain Model`, including dashboard snapshot, route preview, victim status, and fixture timeline contracts.
- `.env.example` complete.
- All 4 tracks can `git pull` and start without conflicts.

- [ ] pnpm workspace + root tsconfig + root scripts
- [ ] `packages/types` exports full domain model plus `DashboardState`, `RoutePreview`, `VictimStatusView`, and `FixtureTimelineEvent`
- [ ] `apps/victim` Vite + React + Tailwind + PWA manifest stub runs
- [ ] `apps/responder` Vite + React + Tailwind + Mapbox import stub runs
- [ ] `services/api` Hono + Snowflake SDK + dotenv stub runs (health check route only)
- [ ] `snowflake/01_schema.sql` skeleton with empty tables
- [ ] `scenarios/texas-flood.json` with 3 example incidents (placeholder)
- [ ] `.env.example` complete
- [ ] CI: skip; local-only for hackathon
- [ ] Push to `main`. Tag `template-ready`.

---

## Critical Path — H0 to H3 Contract-First Checklist

These are the cross-track gates that prevent UI/API/Snowflake drift. If these are late, everyone shifts to unblock them before adding polish.

- [ ] H1.5: Template scaffold merged and all tracks can run `pnpm install && pnpm dev`
- [ ] H2: `@disaster/types` exports final v1 shapes for `IncidentRaw`, `IncidentEnriched`, `SeverityResult`, `Assignment`, `UnmetResourceNeed`, `DashboardState`, `RoutePreview`, `VictimStatusView`, `FixtureTimelineEvent`, and `SSEEvent`
- [ ] H2: Snowflake `01_schema.sql` applies and contains `INCIDENTS_RAW`, physical `INCIDENTS_ENRICHED`, `RESPONDERS`, `ASSIGNMENTS`, `UNMET_RESOURCE_NEEDS`, `ROUTES`, and `INCIDENT_STREAM`
- [ ] H2.5: API `/health` confirms process boot; Snowflake connection can run `SELECT 1`
- [ ] H3: `POST /v1/incidents` inserts one GPS-backed test incident into `INCIDENTS_RAW`
- [ ] H3: `GET /v1/dashboard/state` returns typed fixture-or-live shape so responder UI can hydrate normalized store
- [ ] H3: Track D shares severity JSON schema and degraded fallback shape; Tracks B/C stop changing it without sync

---

## Track A — Victim PWA (1 person)

Owner: **___________**

### Hour-by-hour

**H0–H1: Thin submitter shell**
- [ ] React Router setup with routes: `/`, `/incident`, `/status/:id`, `/manual-location`
- [ ] Tailwind theme: dark mode default, high-contrast red/green/amber
- [ ] PWA manifest stub only; install prompt is secondary
- [ ] Service worker stub only; production-grade offline queue is secondary

**H1–H3: Home + incident submit**
- [ ] `pages/Home.tsx`: two huge buttons (Call / Text), prompt panel ("Things to say: where you are, what happened, who needs help, what you have, what you need")
- [ ] **Call button** = stub for v1 (alerts "voice coming soon"; nice-to-have wires to ConvAI). DO NOT block on this.
- [ ] **Text button** → `pages/Incident.tsx`
- [ ] `Incident.tsx`: textarea + dynamic checklist (medical / trapped / fire / water / shelter / power / evacuation)
- [ ] Generate/persist anonymous `device_id` in `localStorage`; optional `profile_id` is not required for first live submit
- [ ] On submit: capture GPS (`navigator.geolocation.getCurrentPosition`). If denied/timeout → route to `/manual-location`
- [ ] `POST /v1/incidents` then route to `/status/:id`

**H3–H5: Manual location fallback**
- [ ] `pages/ManualLocation.tsx`: textarea ("describe where you are — nearby buildings, restaurants, gas stations, cross-streets")
- [ ] Pass description to `POST /v1/incidents` with `location.source = 'place_description_udf'`
- [ ] Show returned coords on a tiny Mapbox static-image preview with confidence radius

**H5–H7: Live status screen**
- [ ] `pages/Status.tsx`: poll `GET /v1/incidents/:id` every 5s
- [ ] Show severity score (big number, color-coded), category badge, 3 reasons, assigned responder type + ETA when available

**H7–H10: Pre-reg + inventory add-back**
- [ ] `pages/Onboard.tsx`: optional profile form (name, age, conditions, devices, emergency contact)
- [ ] Save to `localStorage` AND `POST /v1/profiles`
- [ ] Add inventory have/need checklists to `Incident.tsx`
- [ ] PATCH `/v1/incidents/:id/inventory` from status page only if API endpoint is ready
- [ ] Polish typography, button states, accessibility (aria-labels, focus rings)

**H10+: Stretch**
- [ ] Offline queue smoke test: DevTools offline → submit → reconnect → flushes one queued incident
- [ ] Full PWA install prompt and production-grade offline queue semantics
- [ ] 15-min GPS ping (`watchPosition`) when incident is open
- [ ] Wire Call button to ElevenLabs ConvAI agent (drop-in)

### Deliverables
- `apps/victim` thin live submitter: one GPS/place-description incident → status page
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
- [ ] Zustand store normalized by ID/type:
  - `incidentsById: Record<string, IncidentEnriched>`
  - `clustersById: Record<string, ClusterView>`
  - `assignmentsById: Record<string, Assignment>`
  - `routesByResponderId: Record<string, RoutePreview>`
  - `rosterByType: Partial<Record<ResourceType, ResourceRoster>>`
- [ ] Upsert reducers for each SSE event type; never append blindly
- [ ] Sorted selectors for queue order, active clusters, responder routes, and roster rows
- [ ] On mount: `GET /v1/dashboard/state` for initial snapshot

**H7–H9: Sidebars + side sheet**
- [ ] `components/IncidentQueue.tsx` (right sidebar, sortable by severity desc, status filter)
- [ ] `components/IncidentSheet.tsx` (side sheet): transcript, summary, profile snippet, severity card with 3 reasons, required_resources chips, assigned unit + ETA, "Mark Resolved" button
- [ ] Incident sheet shows warning chip when `triage_status='degraded'` so dispatchers know AI output fell back
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
- [ ] Smooth pin entry animation (Framer Motion) — optional polish; cut if Snowflake/dispatch is not demo-ready
- [ ] Cluster merge animation when dedup fires — optional polish; cut if Snowflake/dispatch is not demo-ready
- [ ] Route recompute animation: old polyline fades, new one draws — optional polish; cut if Snowflake/dispatch is not demo-ready
- [ ] Toasts on new sev≥90 incident ("⚠ Critical incident, dispatching")

**H15+: Stretch**
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
- [ ] `POST /v1/incidents` — validate, if GPS is unavailable call `UDF_RESOLVE_PLACE_DESCRIPTION`, INSERT INTO `INCIDENTS_RAW`, return `{ incident_id, status }`
- [ ] `GET /v1/incidents/:id` — read from `INCIDENTS_ENRICHED` (joins severity)
- [ ] `PATCH /v1/incidents/:id/inventory`

**H4–H6: Dashboard endpoints**
- [ ] `GET /v1/dashboard/state` — single query gathering open incidents, clusters, roster, active assignments + routes
- [ ] `POST /v1/roster` — bulk upsert RESPONDERS rows; require `Authorization: Bearer $ADMIN_TOKEN`
- [ ] `POST /v1/assignments/:id/status` — call `MARK_ON_SCENE` or `MARK_RESOLVED` stored proc; require `Authorization: Bearer $ADMIN_TOKEN`

**H6–H9: SSE**
- [ ] `lib/sse.ts`: in-memory `Set<ResponseWriter>` of connected clients
- [ ] `GET /v1/stream` — sets text/event-stream headers, registers client
- [ ] Background poller (`setInterval` 2s): query `INCIDENTS_ENRICHED CHANGES(INFORMATION => APPEND_ONLY)` since last cursor, emit `incident_new`/`incident_update`
- [ ] Same poller for clusters, roster, assignments

**H9–H11: Mapbox routing client**
- [ ] `lib/mapbox.ts`: `optimizeRoute(origin, stops[])` → encoded polyline + total duration
- [ ] On `assignment_new` SSE event, queue a route computation; persist to `ROUTES` table; emit `route_update`

**H11–H13: Admin + scenario**
- [ ] `lib/scenarios.ts`: load canonical scenario data, schedule `setTimeout` per incident (staggered timestamps from file)
- [ ] `POST /v1/admin/scenario/start` — requires `Authorization: Bearer $ADMIN_TOKEN`, runs scheduler, returns ETA to completion
- [ ] `POST /v1/admin/scenario/inject` — requires `Authorization: Bearer $ADMIN_TOKEN`, inserts single high-sev incident with auto-generated transcript
- [ ] `POST /v1/admin/recompute-routes` — requires `Authorization: Bearer $ADMIN_TOKEN`, re-fires dispatch + route compute

**H13–H15: Resilience + polish**
- [ ] Retry on Snowflake transient errors (3 attempts, exponential backoff)
- [ ] Structured logging (`pino`) with request IDs
- [ ] Error response shape: `{ error: { code, message } }`
- [ ] CORS allow-list from `.env`
- [ ] Route fallback: if Mapbox Optimization fails, emit cached route if available or straight-line preview with `route_source='fallback'`
- [ ] API tests with mocked Snowflake:
  - `POST /v1/incidents` validates required text + GPS/place-description input
  - `POST /v1/incidents` returns typed `{ incident_id, status }` on insert success
  - Admin/roster mutation endpoints reject missing or wrong `ADMIN_TOKEN`
  - Snowflake transient failure returns `{ error: { code, message } }` and logs request ID
  - `GET /v1/dashboard/state` returns typed incidents/clusters/roster/assignments shape
  - `POST /v1/admin/scenario/start` schedules fixture incidents without blocking response

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
- [ ] Spike whether true Cortex Search service/index is available in this Snowflake account; if not, proceed with Cortex embeddings + `VECTOR_COSINE_SIMILARITY`
- [ ] Run `snowflake/01_schema.sql`: create `PROFILES`, `INCIDENTS_RAW`, `RESPONDERS`, `ASSIGNMENTS`, `ROUTES`, indexes, primary keys, `INCIDENT_STREAM`.
- [ ] Insert 1 row in each table for sanity check.

**H1–H3: Cortex triage SQL**
- [ ] `snowflake/02_cortex_triage.sql`: `TRIAGE_TASK` that runs on `INCIDENT_STREAM`
- [ ] Compose prompt for `SNOWFLAKE.CORTEX.COMPLETE` (claude-3-5-sonnet) with strict JSON schema for `SeverityResult`
- [ ] Insert task output into physical `INCIDENTS_ENRICHED` table: raw incident fields + parsed severity JSON + `triage_status` + summary + embedding + default `status='open'`
- [ ] On Cortex JSON parse failure, store visible degraded fallback: `score=50`, `category='unknown'`, `confidence=0.2`, fallback reasons, `triage_status='degraded'`
- [ ] Test on 3 manually-inserted incidents; verify valid JSON parses and malformed JSON creates degraded fallback

**H3–H6: Dynamic Tables**
- [ ] `snowflake/03_dynamic_tables.sql`:
  - `INCIDENT_CLUSTERS` (`ST_CLUSTER_KMEANS` + `VECTOR_COSINE_SIMILARITY` dedup)
  - `RESOURCE_ROSTER` (rollup from RESPONDERS by type)
  - `SEVERITY_HEATMAP_H3` (H3 bucket aggregates)
- [ ] Confirm `TARGET_LAG = '15 seconds'`; check `last_refresh_status = SUCCEEDED`

**H6–H9: Dispatch stored proc**
- [ ] `snowflake/04_dispatch_proc.sql`: `DISPATCH_INCIDENTS()` procedure
  - For each open incident (ORDER BY severity DESC):
    - Read `required_resources` from severity JSON
    - For each required type, find nearest available responder (`ST_DISTANCE`)
    - If found, INSERT INTO `ASSIGNMENTS` with `resource_type`, UPDATE `RESPONDERS` SET `status='busy'`
    - If not found, INSERT/UPSERT `UNMET_RESOURCE_NEEDS` so the dashboard shows partial assignment clearly
  - Keep schema optimizer-ready: assignment rows are per responder/resource type, not one opaque blob per incident
- [ ] `DISPATCH_TASK` scheduled every 30s + manually triggered by API

**H9–H11: Snowpark UDF for location**
- [ ] Add `PLACES` seed data: Houston restaurants, gas stations, hospitals, schools, shelters, intersections, and scenario-specific buildings
- [ ] `snowflake/05_udf_location.py`: `UDF_RESOLVE_PLACE_DESCRIPTION(description, last_lat, last_lng)`
  - Tokenize the place description and fuzzy-match against seeded `PLACES`
  - Prefer candidates near `last_lat/last_lng` when available; otherwise prefer scenario bounding box
  - Return `{ lat, lng, confidence, reasoning, matched_place_names }`
  - Fallback: return `(last_lat, last_lng, 0.3, 'fallback to last GPS')` if available; otherwise ask the API to return a low-confidence manual-location error
- [ ] Register UDF, test with 5 sample place descriptions such as "near the McDonald's and gas station by I-10"

**H11–H13: Scenario data**
- [ ] Author `scenarios/texas-flood.json` (50 incidents): vary location (across Houston grid), severity (15 critical, 20 medium, 15 low), category mix (10 medical, 8 trapped, 12 water, 6 fire, 4 power, 5 shelter, 5 evacuation)
- [ ] Ensure scenario incidents insert through the same `INCIDENTS_RAW` path as live victim reports
- [ ] `snowflake/06_scenario_proc.sql` is optional v1: only add if time remains for canonical Snowflake scenario tables/procs; API owns 60-second demo timing

**H13–H15: End-to-end smoke**
- [ ] Trigger scenario via API → watch `INCIDENTS_RAW` fill → confirm Cortex fires → check `INCIDENTS_ENRICHED` populates → confirm clustering happens → confirm dispatch fires
- [ ] Tune `TARGET_LAG` if too slow; add manual `REFRESH` triggers in API after scenario start to force fast first-pass
- [ ] Smoke checklist: 3 manual incidents enrich, clusters refresh, dispatch creates assignment rows, unmet resources appear when roster is depleted

**H15+: Stretch**
- [ ] Cortex Search index instead of cosine similarity (proper Search API)
- [ ] TensorMesh caching wrapper around `CORTEX.COMPLETE`
- [ ] API-only live Mapbox place search for arbitrary business names, then store chosen coords/confidence in Snowflake
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
- `pnpm typecheck` passes across the workspace.
- API tests pass for incident submit, dashboard state shape, scenario start, and error response shape.
- Snowflake smoke checklist passes for enrich → cluster → dispatch → unmet resource needs.

If any of the above is broken at H16, **prioritize fixing over polish**.
