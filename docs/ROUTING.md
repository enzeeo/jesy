# Open Routing + Responder Tracking

## What Was Built

The route optimizer now recommends per-responder routes, lets a dispatcher
explicitly send a selected responder, tracks responder phone-style location
pings, detects arrival at the caller location, and queues Snowflake-compatible
dispatch and arrival rows.

The first screen remains dispatcher-controlled. `POST /routing/optimize`
computes recommendations only. A responder is not considered sent until a human
dispatcher starts a route leg with `POST /routing/dispatches/start`.

## Research Grounding

The optimizer is grounded in disaster-routing literature:

- Dubois et al., ISCRAM 2022, flood rescue CVRP/DVRP:
  <https://www.idl.iscram.org/files/florentdubois/2022/2400_FlorentDubois_etal2022.pdf>
  Use upstream incident priority as the authoritative weight and minimize
  weighted arrival/waiting time instead of pure distance.
- Akbari/Shiri 2022, online routing with blocked edges:
  <https://www.sciencedirect.com/science/article/abs/pii/S0305054821002707>
  Treat blocked or flooded roads as non-recoverable constraints for routing;
  road repair is out of scope.
- Campbell et al. 2008, routing for relief efforts:
  <https://pubsonline.informs.org/doi/abs/10.1287/trsc.1070.0209>
  Value arrival time and service fairness, not only shortest path.

Implementation translation: the backend keeps the AI/triage `priority_score` as
input, then minimizes weighted flow-time:

```text
priority_score * demand_count * arrival_seconds + road/access penalties
```

That means the route may visit a closer lower-priority caller first when doing
so reduces total weighted waiting time without ignoring the higher-priority
incident.

## Route Optimization API

`POST /routing/optimize` accepts optional stub/live-shaped data:

- `responders`: responder units; omitted means use responders currently in app
  state.
- `incidents`: incident records; omitted means use open in-memory incidents.
- `clusters`: upstream incident clusters.
- `road_access`: GeoJSON road access or closure features.
- `accepted_assignments`: responder-to-target ids that should be frozen.
- `route_stop_limit` and `max_candidates`: solver bounds.

The response includes:

- `route_id`: durable id for this recommendation result.
- `routes`: object keyed by responder id.
- `leg_id`: durable id on each route leg.
- `route_geometry`: LineString for Mapbox route display.
- `eta_seconds`, `distance_km`, `arrival_seconds`.
- `provider_status`, `degraded`, `warnings`.
- `road_access`: closure summary and source GeoJSON when supplied.
- `unassigned`: incidents or clusters not assigned in this pass.

Each route starts at the responder's current location. In demos, that location
comes from seeded stub responders. In production, it would come from the latest
responder location ping or fleet location feed.

## Road Closures

Road access is supplied as GeoJSON. Features should carry properties such as:

- `road_status`: `confirmed_closed`, `likely_flooded`, `restricted`, or
  `uncertain_needs_verification`.
- `confidence`: source confidence.
- access-mode metadata when available.
- freshness/source metadata when available.

Routing behavior:

- `confirmed_closed` and `likely_flooded` are hard avoid statuses for ground
  vehicles.
- `restricted` and `uncertain_needs_verification` are soft penalties.
- With `OPENROUTESERVICE_API_KEY`, OpenRouteService can enforce avoid polygons.
- Without ORS, the stub provider returns haversine geometry, adds penalties, and
  marks hard closures as degraded because the stub cannot truly route around the
  polygon.

Mapbox renders the closure GeoJSON and route lines so the dispatcher can inspect
recommendations before sending a unit.

## Dispatch Start

`POST /routing/dispatches/start` turns a recommendation into a live dispatch.

Request:

```json
{
  "route_id": "recommendation-id",
  "leg_id": "recommendation-id:responder-id:0",
  "started_by": "dispatcher-a"
}
```

On success, the backend:

- validates that the route and leg still exist in the recommendation store.
- validates that the leg is incident-backed.
- sets the responder status to `en_route`.
- writes `assigned_incident_id` on the responder.
- sets the incident status to `en_route`.
- publishes SSE event `dispatch_started`.
- queues a Snowflake `responder_dispatches` row.

The endpoint is idempotent for the same `route_id` and `leg_id`. Repeating the
same start call returns the original `dispatch_id` and does not queue another
Snowflake row.

Cluster note: `/routing/optimize` can recommend routes to clusters, but V1
dispatch start requires an incident-backed leg because responder assignment and
arrival detection currently use `assigned_incident_id`.

## Responder Phone UI

The responder web UI lives at `/responder`.

It is a simple responsive phone page where a responder can:

- pick a seeded responder/unit.
- see callsign, status, assigned incident, route id, leg id, ETA, and distance.
- request browser GPS and send a location ping.
- send a manual stub ping.
- send a simulated ping that moves toward the assigned destination.

This is not a native app and has no auth in V1. It uses the same backend path a
native phone app would use later.

## Tracking + Arrival Detection

`POST /responders/{responder_id}/location` accepts phone-like GPS pings:

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

On every ping, the backend:

- updates the responder location.
- publishes SSE event `responder_location_updated`.
- checks distance to the assigned incident.
- marks arrival after geofence dwell logic: default 50 meters and either two
  consecutive in-radius pings or 30 seconds dwell.

When arrival is detected, the backend:

- sets responder status to `on_scene`.
- sets incident status to `on_scene`.
- publishes SSE event `responder_arrived`.
- queues a Snowflake `responder_arrivals` row.

The phone UI and dispatcher map both listen to the SSE feed.

## Assignment Lookup

`GET /responders/{responder_id}/assignment` returns the active dispatch for the
unit, if any. It includes:

- `assignment_id`, which is the dispatch id for the active assignment.
- `route_id`.
- `leg_id`.
- `responder_id`.
- `incident_id`.
- `status`.
- `eta_seconds`.
- `distance_km`.
- `route_leg`.
- embedded incident details when available.

The responder phone UI uses this endpoint to show the current assignment after a
dispatcher clicks Send.

## Snowflake Data

Snowflake is optional. If credentials are missing, the app uses a no-op writer.
The code path still queues rows and updates metrics, so tests and demos exercise
the same API boundary.

Supported operational tables now include:

`incidents`

- `id`, `timestamp`, `source`, `status`.
- `lat`, `lng`, `location_description`.
- `severity`, `priority_score`.
- `victim_count`, `vulnerabilities`.
- `confidence`, `sim_run_id`.

`voice_calls`

- `incident_id`.
- `transcript_length`.
- `model`.
- `tokens`.

`responder_dispatches`

- `responder_id`.
- `incident_id`.
- `dispatched_at`.
- `distance_km`.
- `eta_seconds`.
- `solver`.

`responder_arrivals`

- `responder_id`.
- `callsign`.
- `incident_id`.
- `cluster_id`.
- `arrival_timestamp`.
- `ping_lat`, `ping_lng`.
- `accuracy_m`.
- `route_id`.
- `assignment_id`.
- `detection_method`.
- `distance_m`.

The SQL bootstrap in `scripts/snowflake_init.sql` includes the
`responder_arrivals` table.

## Dispatcher Flow

1. Seed or ingest incidents and responders.
2. Dispatcher opens the map dashboard.
3. Dashboard calls `POST /routing/optimize`.
4. Map shows route lines and road-access polygons.
5. Dispatcher selects an incident.
6. Incident detail shows the recommended responder for that incident.
7. Dispatcher clicks Send.
8. Backend starts dispatch, updates state, emits `dispatch_started`, and queues
   `responder_dispatches`.
9. Responder opens `/responder`, sees the assignment, and sends GPS pings.
10. Arrival detection emits `responder_arrived` and queues `responder_arrivals`.

## Current Limits

- V1 uses one primary responder per incident-backed dispatch leg.
- Cluster routing is recommended and rendered, but dispatch start is currently
  incident-backed.
- The phone UI is demo-auth only.
- Stub routing cannot truly enforce blocked roads; real avoidance requires ORS
  or another directions provider that supports avoid polygons.