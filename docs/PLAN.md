<!-- /autoplan restore point: /Users/enzeeo/.gstack/projects/jezy/enzeeo-autoplan-restore-20260516-151602.md -->
# PLAN — Disaster Relief Triage (Texas Flood Demo)

**Status:** APPROVED · 18h hackathon · 4 people
**Last updated:** 2026-05-16

---

## Problem

During a large-scale disaster (e.g. Texas flood), individual victims can't get through to overwhelmed call centers, and responders lack a macro-level picture of who needs what, where, and how badly. Triage breaks down. People die waiting.

## Solution

A two-sided web platform.

- **Victim PWA**: one button to call (or text) describing situation. Captures location, needs, profile. Works under low signal (offline queue).
- **Responder dashboard**: live map of incidents with severity heatmap, auto-clustered duplicate reports, AI-explained priority, and dynamic dispatch of responder units (police / fire / EMT / paramedic / nurse / doctor / volunteer) by required-resource match + severity + distance.
- **AI backbone in Snowflake**: Cortex AI for severity scoring + summarization, Cortex embeddings + vector similarity for semantic dedup, Streams+Tasks for auto-triage pipeline, Dynamic Tables for live aggregates, geospatial functions for clustering, Snowpark UDF for GPS-missing place-description fallback.

## Demo Scenario

**Texas flash flood, Houston metro.** Pre-authored 50-incident scenario triggered by admin "Start Scenario" button. The API owns the 60-second theatrical insert timing; every inserted incident then runs through the real Snowflake pipeline → genuine severity, real clusters, real dispatch.

## Demo Truth Boundary

- **Fixture UI Preview comes first**: the first build can use mock data for every UI surface to validate layout, copy, and state choreography before API/Snowflake exists. It should use 12 curated incidents in a scripted 60-second scenario with Start, Inject, and Reset controls so the preview matches the final demo rhythm while staying easy to review.
- **Fixture UI Preview is not the judged demo**: local fixture data must not be presented as live Snowflake processing.
- **Synthetic input is allowed**: v1 victim "calls" are pre-authored scenario incidents, not real phone calls.
- **Snowflake processing must be live**: scenario incidents still go through the real API/Snowflake ingest path, Cortex severity, dedup/clustering, roster rollup, and dispatch assignment during the demo.
- **Scenario timing belongs to the API**: Snowflake owns scenario processing/state after ingest; the API schedules incident inserts so the demo beats are reliable.
- **Routes are live with fallback**: Mapbox polylines are attempted live; if Mapbox fails, use cached routes or straight-line route previews so dispatch remains visible.
- **Offline queue is smoke-tested only**: prove one offline submit can queue and flush, but do not build production-grade offline sync semantics in v1.
- **Animations are optional polish**: pin entry, cluster merge, and route redraw animations are cut before any Snowflake or dispatch work.

## Verification Standard

- **Required**: `pnpm typecheck` across workspace.
- **Required**: API tests for request validation, happy-path route handlers with mocked Snowflake, and error response shape.
- **Required**: Snowflake smoke checklist: schema applies, 3 incidents enrich, clusters refresh, dispatch creates assignments/unmet needs.
- **Required**: manual end-to-end demo script: start scenario → incidents appear → severity visible → dispatch visible → route fallback works.
- **Not required for v1**: full frontend unit tests, full Playwright suite, production offline-sync tests.

---

## Locked Decisions

| ID  | Decision                                                                  | Chosen                                                                                                 |
| --- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| D1  | Time + team                                                               | 18h × 4 people                                                                                         |
| D2  | Realtime layer                                                            | Snowflake only (hard constraint), poll Snowflake from API, push to dashboards via SSE                  |
| D3  | Snowflake features showcased                                              | Cortex AI, Cortex embeddings/vector similarity, Streams+Tasks, Dynamic Tables, Geo fns, Snowpark UDF; true Cortex Search service is stretch |
| D4  | Voice pipeline                                                            | **Deferred** — text-first for v1, ElevenLabs ConvAI added as drop-in replacement when time permits     |
| D5  | Victim client                                                             | PWA (Vite + React + TS), service worker offline queue                                                  |
| D6  | Map + routing                                                             | Mapbox + deck.gl + Mapbox Optimization API; fallbacks are cached/straight-line routes, fixture mode, and screenshot/video backup |
| D7  | API server                                                                | Hono on Node, TS, SSE push, Snowflake Node SDK                                                         |
| D8  | Auth                                                                      | Anonymous victim w/ device ID; responder UI may use hardcoded login; admin/roster mutations require `ADMIN_TOKEN` |
| D9  | Doomsday kit                                                              | Self-inventory in pre-reg; need-flags ride on incident payload; no delivery routing                    |
| D10 | Location confidence                                                       | GPS primary; if GPS fails, Snowpark UDF scores a seeded Houston place-description lookup; live Mapbox place search is stretch |
| D11 | Severity scoring                                                          | Full inputs (transcript, needs, profile, location risk, time-decay); JSON output with 3-reason explain |
| D12 | Cluster + dedup                                                           | Both, auto via Dynamic Table joining `ST_CLUSTER_KMEANS` + Cortex embeddings/vector similarity; true Cortex Search service only if hour-1 spike succeeds |
| D13 | Routing                                                                   | V1 greedy multi-resource dispatch with visible unmet needs; schema leaves room for later optimizer; Mapbox polyline + recompute on sev≥80 or unit-free |
| D14 | Demo data                                                                 | 50 hand-authored Texas flood incidents in `scenarios/texas-flood.json`                                 |
| D15 | Responder UI                                                              | Map-dominant + collapsible side panels + bottom route drawer; dense dark command-center tone           |
| D16 | Victim UI                                                                 | Polished calm high-contrast mobile flow: Call/Text buttons + dynamic prompt; lightweight skippable pre-reg/profile; inventory chips; status screen after |
| D17 | Repo                                                                      | pnpm monorepo, 4 tracks; template scaffolded first by one person, then forked                          |
| D18 | Hosting                                                                   | Local dev only for v1 demo; Cloudflare Tunnel optional if ElevenLabs added                             |
| D19 | Multi-responder dispatch (promoted)                                       | Roster panel + Cortex `required_resources` output + Snowflake greedy assignment proc                   |
| D20 | Fixture UI Preview                                                       | First implementation may use local mock data for all UI states; equal polish with shared tokens and split tone; live Snowflake remains final demo truth |

---

## Must-Have Feature List (ship by hour 16)

1. **pnpm monorepo scaffold** + shared `packages/types`.
2. **Snowflake schema**: `profiles`, `incidents_raw`, `incidents_enriched`, `clusters`, `responders`, `assignments`, `routes`.
3. **Victim PWA**: thin live submitter first: home (Call/Text buttons + dynamic prompt), text incident submit with GPS/place-description fallback, post-submit live status screen. Pre-reg, inventory, and offline depth are add-back scope after the main pipeline works.
4. **Responder dashboard**: Mapbox map full-bleed, deck.gl heatmap + cluster pins, severity legend, right-sidebar queue, side-sheet with transcript + extracted needs + severity + 3 explainability reasons, left-sidebar filters, top stats bar, **resource roster panel**, bottom route drawer with per-unit assignment.
5. **Cortex severity scoring**: full inputs, JSON output incl. `score`, `category`, `top_reasons[3]`, `confidence`, `required_resources`.
6. **Cortex embedding/vector dedup + `ST_CLUSTER_KMEANS` clustering** auto-run in Dynamic Table every 10s.
7. **Snowpark location-confidence UDF**: place description → `(lat, lng, confidence, reasoning)` from seeded Houston places/intersections when phone GPS is unavailable.
8. **Snowflake dispatch + routing stored proc**: greedy multi-resource assignment by severity × distance × resource-match; partial assignment is allowed and unmet resource needs are visible; Mapbox Optimization for polyline with fallback; recompute on sev≥80 or unit-free.
9. **SSE push** from API → responder dashboard for new incidents + cluster updates + assignment changes.
10. **Texas flood scenario JSON** (50 incidents) + admin "Start Scenario" endpoint.
11. **Self-inventory toggle** propagating need-flags on incidents.
12. **Demo script + 5-slide deck**.
13. **Resource roster panel**: configurable counts (police / fire / EMT / paramedic / nurse / doctor / volunteer); live `active / total` per type; backed by Dynamic Table.
14. **Side sheet assigned-unit display**: shows assigned responder, ETA, route preview.

## Nice-to-Have (only if ahead by hour 12)

- **ElevenLabs ConvAI** integration replaces text submit (drop-in via webhook → same incident shape).
- **15-min GPS ping polling** from victim PWA `watchPosition`.
- **TensorMesh caching** layer for repeated Cortex calls (sponsor prize secondary).
- **Vercel + Railway deploy** so judges click real URLs.
- **Hospital + shelter layer** on responder map.

## Out of Scope (skip)

- Real auth (Clerk, OTP, Twilio).
- Kit delivery routing.
- Native iOS/Android.
- Mid-call interruption / barge-in handling.
- Hungarian-algorithm multi-responder optimization (greedy is enough).

---

## Snowflake Prize Angle (judge-facing)

> "We don't just store data in Snowflake. The entire AI brain lives there. Cortex generates severity. Cortex embeddings dedup duplicate reports across 50 callers using vector similarity. Snowpark UDFs resolve GPS-missing place descriptions against Houston places and intersections. Streams + Tasks trigger triage with zero glue code. Dynamic Tables refresh our heatmap aggregates and resource rosters in real time. Geospatial functions cluster victims and rank routes. Everything you see on this dashboard, the warehouse computed."

---

## Workflow Summaries

### Victim workflow

1. Open PWA link → optional one-time **pre-reg** (name, age, conditions, devices owned, emergency contact) saved to `profiles`.
2. **Home**: Call button + Text button + scrolling prompt of *"things you should mention: where you are, what happened, who's hurt, what you need."*
3. Victim picks Text (v1) → text area with same prompts → submit. *(v2: Call → ElevenLabs ConvAI agent.)*
4. PWA captures GPS via `navigator.geolocation`. On failure, **manual-location fallback** screen: "describe where you are" → Snowpark place-description UDF.
5. Incident posted to API → Snowflake → Stream picks it up → Task fires Cortex severity + dedup → Dynamic Table updates.
6. PWA shows **status screen**: severity score, ETA estimate, nearest responder type assigned. Live-updated via SSE-equivalent (PWA polls `/v1/incidents/:id` every 5s for v1; SSE if time).
7. **Inventory toggle**: any pre-reg item flippable to "have/need" mid-incident; updates incident.

### Responder workflow

1. Login (hardcoded `admin/admin`).
2. **Setup roster** (one-time per session): set available counts for police / fire / EMT / paramedic / nurse / doctor / volunteer.
3. Admin: click **Start Scenario** → 50 synthetic Texas flood calls fire over 60s.
4. Dashboard fills with pins. Heatmap blooms. Right sidebar fills with sorted incidents. Resource panel ticks down as Snowflake assigns units.
5. Click pin → side sheet: transcript, profile, severity, 3 reasons, required resources, assigned unit, ETA.
6. Toggle responder unit in left filter → bottom drawer shows that unit's ordered route on map.
7. Drop a manual severity-95 incident mid-demo → watch routes recompute, units reassign.

---

## End-to-End Data Flow

```
Victim PWA
  └─ POST /v1/incidents  (text + GPS or place-description + profile_id)
        │
        ▼
  Hono API  ─────────►  Snowflake INCIDENTS (raw)
                                │
                                ▼
                       STREAM (incident_changes)
                                │
                                ▼
                       TASK (every 5s)
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
            Cortex Severity   Cortex Embeddings   Snowpark UDF
            (score+resources) (vector dedup)      (location conf)
                  └─────────────┼─────────────┘
                                ▼
                       INCIDENTS_ENRICHED  (physical table written by TRIAGE_TASK)
                                │
                                ▼
                       CLUSTERS  (ST_CLUSTER_KMEANS in Dynamic Table)
                                │
                                ▼
                       ASSIGNMENTS  (stored proc: greedy dispatch)
                                │
                                ▼
                       ROUTES  (Mapbox Optimization API via API server)
                                │
                                ▼
  Hono API  ─────────►  SSE channel  ─────────►  Responder Dashboard
```

---

## Critical Risks & Mitigations

| Risk                                       | Mitigation                                                                                            |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Snowflake account access blocks all 4 people | Person 4 spins up Snowflake first hour; shares ROLE; uses `INSERT INTO ... VALUES` for dummy data so frontend/api can mock until pipeline ready. |
| Cortex region availability                 | Confirm Cortex AI region for the sponsor account in hour 1; if wrong region, request migration or use `claude-3-5-sonnet` cross-region. |
| Mapbox Optimization API limits             | Free tier covers demo; cache routes in `routes` table; recompute only on triggers (not every render). |
| Dynamic Table refresh latency              | Set TARGET_LAG = '1 minute' on dev, demonstrate visible refresh; tighten to '15 seconds' for demo.    |
| Type drift between 4 apps                  | All apps consume `@disaster/types` package; lint rule forbids inline domain types in apps.            |
| Demo crash mid-presentation                | Always have local `texas-flood.json` replay as backup; never depend solely on live demo input.        |

---

## Success Criteria

- [ ] Judge can press "Start Scenario" → see 50 incidents flood the map in 60s with severity colors + clusters.
- [ ] Judge clicks a pin → sees AI-written severity reasons that *feel personalized* (cite victim's profile/age/condition).
- [ ] Judge sees a high-severity incident appear → watches at least one route visibly recompute and reassign a unit.
- [ ] Judge sees two duplicate reports auto-merge into one cluster.
- [ ] Judge sees resource roster panel decrement as units dispatch and increment on "mark resolved."
- [ ] Snowflake worksheet shown live: judge sees real Cortex SQL, real Dynamic Table refresh, real `ST_CLUSTER_KMEANS`.
- [ ] All 6 Snowflake features visibly demoed within 4 minutes.

---

## What Comes Next (after this doc)

1. One person **one-shots the template scaffold** per `docs/TEMPLATE.md` (~1.5h).
2. Fork into 4 tracks per `docs/TASKS.md`.
3. Sync every 3h: status, blockers, type changes.
4. Demo dry-run at hour 14. Tighten + record at hour 16.
