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
- **AI backbone in Snowflake**: Cortex AI for severity scoring + summarization, Cortex Search for vector dedup, Streams+Tasks for auto-triage pipeline, Dynamic Tables for live aggregates, geospatial functions for clustering, Snowpark UDF for landmark-based location fallback.

## Demo Scenario

**Texas flash flood, Houston metro.** Pre-authored 50-incident JSON triggered by admin "Start Scenario" button. Real Cortex pipeline runs on synthetic data → genuine severity, real clusters, real routing.

---

## Locked Decisions

| ID  | Decision                                                                  | Chosen                                                                                                 |
| --- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| D1  | Time + team                                                               | 18h × 4 people                                                                                         |
| D2  | Realtime layer                                                            | Snowflake only (hard constraint), poll Snowflake from API, push to dashboards via SSE                  |
| D3  | Snowflake features showcased                                              | All 6: Cortex AI, Cortex Search, Streams+Tasks, Dynamic Tables, Geo fns, Snowpark UDF                  |
| D4  | Voice pipeline                                                            | **Deferred** — text-first for v1, ElevenLabs ConvAI added as drop-in replacement when time permits     |
| D5  | Victim client                                                             | PWA (Vite + React + TS), service worker offline queue                                                  |
| D6  | Map + routing                                                             | Mapbox + deck.gl + Mapbox Optimization API; Leaflet adapter as fallback                                |
| D7  | API server                                                                | Hono on Node, TS, SSE push, Snowflake Node SDK                                                         |
| D8  | Auth                                                                      | Anonymous victim w/ device ID + optional pre-reg profile; demo-hardcoded responder login               |
| D9  | Doomsday kit                                                              | Self-inventory in pre-reg; need-flags ride on incident payload; no delivery routing                    |
| D10 | Location confidence                                                       | Must-have minimal: Snowpark UDF wrapping Cortex + Mapbox Geocoding; pin with dashed confidence radius  |
| D11 | Severity scoring                                                          | Full inputs (transcript, needs, profile, location risk, time-decay); JSON output with 3-reason explain |
| D12 | Cluster + dedup                                                           | Both, auto via Dynamic Table joining `ST_CLUSTER_KMEANS` + Cortex Search vector similarity             |
| D13 | Routing                                                                   | Full dynamic: Snowflake greedy proc + Mapbox polyline + recompute on sev≥80 or unit-free               |
| D14 | Demo data                                                                 | 50 hand-authored Texas flood incidents in `scenarios/texas-flood.json`                                 |
| D15 | Responder UI                                                              | Map-dominant + collapsible side panels + bottom route drawer, dark mode                                |
| D16 | Victim UI                                                                 | Minimal: Call/Text buttons + dynamic prompt of what to say; pre-reg one-time; status screen after      |
| D17 | Repo                                                                      | pnpm monorepo, 4 tracks; template scaffolded first by one person, then forked                          |
| D18 | Hosting                                                                   | Local dev only for v1 demo; Cloudflare Tunnel optional if ElevenLabs added                             |
| D19 | Multi-responder dispatch (promoted)                                       | Roster panel + Cortex `required_resources` output + Snowflake greedy assignment proc                   |

---

## Must-Have Feature List (ship by hour 16)

1. **pnpm monorepo scaffold** + shared `packages/types`.
2. **Snowflake schema**: `profiles`, `incidents`, `severities`, `clusters`, `responders`, `assignments`, `routes`.
3. **Victim PWA**: pre-reg screen, home (Call/Text buttons + dynamic prompt), text incident submit, post-submit live status screen, inventory toggle, manual-location fallback.
4. **Responder dashboard**: Mapbox map full-bleed, deck.gl heatmap + cluster pins, severity legend, right-sidebar queue, side-sheet with transcript + extracted needs + severity + 3 explainability reasons, left-sidebar filters, top stats bar, **resource roster panel**, bottom route drawer with per-unit assignment.
5. **Cortex severity scoring**: full inputs, JSON output incl. `score`, `category`, `top_reasons[3]`, `confidence`, `required_resources`.
6. **Cortex Search dedup + `ST_CLUSTER_KMEANS` clustering** auto-run in Dynamic Table every 10s.
7. **Snowpark location-confidence UDF**: text input → `(lat, lng, confidence, reasoning)`.
8. **Snowflake dispatch + routing stored proc**: greedy by severity × distance × resource-match; Mapbox Optimization for polyline; recompute on sev≥80 or unit-free.
9. **SSE push** from API → responder dashboard for new incidents + cluster updates + assignment changes.
10. **Texas flood scenario JSON** (50 incidents) + admin "Start Scenario" endpoint.
11. **Self-inventory toggle** propagating need-flags on incidents.
12. **Demo script + 5-slide deck**.
13. **Resource roster panel**: configurable counts (police / fire / EMT / paramedic / nurse / doctor / volunteer); live `active / total` per type; backed by Dynamic Table.
14. **Side sheet assigned-unit display**: shows assigned responder, ETA, route preview.

## Nice-to-Have (only if ahead by hour 12)

- **ElevenLabs ConvAI** integration replaces text submit (drop-in via webhook → same incident shape).
- **15-min GPS ping polling** from victim PWA `watchPosition`.
- **Leaflet fallback** toggle for map (architect as adapter; build if time).
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

> "We don't just store data in Snowflake. The entire AI brain lives there. Cortex generates severity. Cortex Search dedups duplicate reports across 50 callers. Snowpark UDFs reason about landmarks. Streams + Tasks trigger triage with zero glue code. Dynamic Tables refresh our heatmap aggregates and resource rosters in real time. Geospatial functions cluster victims and rank routes. Everything you see on this dashboard, the warehouse computed."

---

## Workflow Summaries

### Victim workflow

1. Open PWA link → optional one-time **pre-reg** (name, age, conditions, devices owned, emergency contact) saved to `profiles`.
2. **Home**: Call button + Text button + scrolling prompt of *"things you should mention: where you are, what happened, who's hurt, what you need."*
3. Victim picks Text (v1) → text area with same prompts → submit. *(v2: Call → ElevenLabs ConvAI agent.)*
4. PWA captures GPS via `navigator.geolocation`. On failure, **manual-location fallback** screen: "describe where you are" → Snowpark UDF.
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
  └─ POST /v1/incidents  (text + GPS or landmark-desc + profile_id)
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
            Cortex Severity   Cortex Search   Snowpark UDF
            (score+resources) (vector dedup)  (location conf)
                  └─────────────┼─────────────┘
                                ▼
                       INCIDENTS_ENRICHED  (Dynamic Table)
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
