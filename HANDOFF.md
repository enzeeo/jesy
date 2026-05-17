# Route Optimization + Responder Tracking Handoff

## Current Status

Implemented route optimization, road-access-aware degraded routing, responder phone ping tracking, arrival detection, fake Snowflake arrival writes, and Mapbox route/closure rendering.

Verification:
- `uv run pytest -q` -> 201 passed, 3 OR-Tools/SWIG deprecation warnings.
- `npm run build` from `frontend/` -> passed.

## Research Grounding

The optimizer is grounded in these sources:

- Florent Dubois, Paul Renaud-Goud, Patricia Stolf, "Dynamic Capacitated Vehicle Routing Problem for Flash Flood Victim's Relief Operations," ISCRAM 2022.
  - Used for the core objective: minimize flow-time/waiting time weighted by upstream priority and demand count.
  - This repo treats `priority_score` as authoritative upstream triage input and does not recalculate caller priority inside routing.
- Vahid Akbari and Davood Shiri, "An online optimization approach for post-disaster relief distribution with online blocked edges," Computers & Operations Research, 2022.
  - Used for the road-disruption model: blocked edges are routing constraints that may be discovered or updated online.
  - Road repair/unblocking is explicitly out of scope; we route around or degrade when a live road-aware provider is unavailable.
- Ann Melissa Campbell, Dieter Vandenbussche, William Hermann, "Routing for Relief Efforts," Transportation Science, 2008.
  - Used for the objective choice: relief routing should value arrival time and fairness, not just shortest total distance.
- OpenRouteService routing options.
  - Future live provider should pass hard road closure polygons through `options.avoid_polygons`.
- Mapbox GL JS GeoJSON line/polygon examples.
  - Route lines and road-access polygons are rendered as GeoJSON sources/layers.

## Backend Changes

Key files:
- `src/disaster/routing/weighted.py`
- `src/disaster/app/routes/routing.py`
- `src/disaster/app/routes/responders.py`
- `src/disaster/tracking.py`
- `src/disaster/app/deps.py`
- `src/disaster/app/main.py`

### Route Optimization

`POST /routing/optimize` now accepts an optional JSON body with stubbed or live-provider-shaped data:

- `responders`
- `incidents`
- `clusters`
- `road_access`
- `accepted_assignments`
- `route_stop_limit`
- `max_candidates`

No-body calls still work against in-memory app state. The default solver is now `weighted_flow`; `?prefer_vrp=true` keeps the old OR-Tools/greedy path available for compatibility.

The optimizer converts incidents and upstream clusters into `DispatchTarget` records, then assigns stops to responders using an insertion-style weighted flow-time heuristic:

```text
estimated objective = sum(priority_score * demand_count * arrival_seconds)
```

It can route a closer lower-priority caller first when that lowers total weighted waiting time. Accepted/current legs are frozen via `accepted_assignments`, then later stops are recomputed.

Capability handling:
- `required_capabilities` are hard filters against responder type/capabilities.
- `preferred_capabilities` are stored for future scoring but not yet used as a soft preference.

Response includes:
- solver name
- routes by responder id
- target id/type
- incident/member ids
- ETA and arrival seconds
- route GeoJSON `LineString`
- degraded/provider status/warnings
- road-access summary and original feature collection for the frontend

### Road Closures

Road-access input is GeoJSON `FeatureCollection`.

Status handling:
- `confirmed_closed`, `likely_flooded`: hard avoid for ground routing.
- `restricted`, `uncertain_needs_verification`: soft penalty.

Current provider behavior:
- If `OPENROUTESERVICE_API_KEY` is configured, the optimizer calls OpenRouteService directions and passes hard closure polygons through `avoid_polygons`.
- If ORS is unavailable or not configured, the implementation falls back to deterministic offline `stub_haversine`.
- In stub fallback, if hard closures are present, the route is marked `degraded`, ETA is penalized, and the leg warning includes `hard road closures not enforced by stub provider`.
- The response keeps the road-access `feature_collection` so Mapbox can render closures immediately.

Live-provider behavior:
- ORS legs return `provider_status: "openrouteservice"` with ORS route geometry, distance, and duration.
- Failed ORS calls fall back to `provider_status: "stub_haversine"` with an `openrouteservice unavailable; using stub haversine` warning.
- The response contract stays stable across live and stub providers.

### Responder Tracking

New endpoint:

```text
POST /responders/{responder_id}/location
```

Request shape:

```json
{
  "lat": 19.701,
  "lng": -155.0,
  "accuracy_m": 8,
  "timestamp": "2026-05-17T12:00:00Z",
  "speed_mps": 4.2,
  "heading": 180
}
```

Each ping:
- Updates `ResponderStore` location with description `phone ping`.
- Publishes SSE `responder_location_updated`.
- Checks the responder's assigned incident geofence.

Arrival detection:
- Default geofence radius: 50 meters.
- Arrival triggers after 2 consecutive inside-radius pings or 30 seconds dwell.
- Single inside ping does not mark arrival.

On arrival:
- Responder status becomes `on_scene`.
- Incident status becomes `on_scene`.
- SSE `responder_arrived` is published.
- A fake/future Snowflake row is queued via `SnowflakeWriter.write("responder_arrivals", row)`.

Snowflake row fields include:
- responder id and callsign
- incident id
- arrival timestamp
- ping lat/lng
- accuracy
- route id placeholder
- assignment id
- detection method
- distance in meters

## Frontend Changes

Key files:
- `frontend/lib/types.ts`
- `frontend/lib/api.ts`
- `frontend/lib/useSSE.ts`
- `frontend/app/page.tsx`
- `frontend/components/Map.tsx`

Mapbox now renders:
- responder route `LineString` layers
- degraded route styling
- road-access polygon fill/outline layers
- responder marker movement from SSE pings
- on-scene responder and incident state from arrival events

The dashboard stores the latest routing response from `api.optimize()` and avoids an optimize/SSE loop with a short local echo guard.

## Tests Added

Routing:
- Weighted flow-time can visit closer lower-priority callers first when total waiting cost drops.
- Accepted/current leg stays frozen.
- Hard road closures mark stub fallback routes as degraded.
- `/routing/optimize` accepts stub responders, clusters, and road-access GeoJSON.

Tracking:
- Single location ping updates responder without arrival.
- Second in-geofence ping marks arrival, updates responder/incident state, emits arrival SSE, and queues a Snowflake row.

## Remaining Work

- Add live road-access feed ingestion upstream of `road_access` request bodies.
- Add route id / assignment id persistence instead of placeholders in Snowflake arrival rows.
- Add a frontend simulator loop that emits periodic responder pings along route geometry.
- Expand capability scoring so preferred responder types influence tie-breaking without becoming hard constraints.
