# CONTEXT — How the system fits together

> **Read this first if you are an agent or engineer landing on this repo.** It explains the moving parts, where they live, what they own, and how they talk.

---

## High-Level Architecture

Three apps + one warehouse:

| Component         | Tech                                    | Purpose                                                   |
| ----------------- | --------------------------------------- | --------------------------------------------------------- |
| `apps/victim`     | Vite + React + TS + Tailwind, PWA       | Anonymous victim entry point; submit incident; live status |
| `apps/responder`  | Vite + React + TS + Tailwind + Mapbox   | Command-center dashboard for first responders             |
| `services/api`    | Hono on Node + TS, Snowflake Node SDK   | Sole gateway between clients and Snowflake; SSE pusher    |
| `snowflake/`      | SQL + Snowpark Python                   | All data + all AI + all geospatial + all routing logic    |
| `packages/types`  | TS only                                 | Shared domain types: `Incident`, `Profile`, `Severity`, `Responder`, `Assignment`, `Cluster` |
| `scenarios/`      | JSON                                    | Synthetic demo data                                       |

**No client talks to Snowflake directly.** Everything funnels through `services/api`. This keeps credentials safe and lets us swap warehouse later if needed (we won't).

**No business logic in the API.** API is dumb glue: validate input, call a Snowflake stored proc or query, push results to SSE. All scoring, dedup, routing happens in Snowflake.

---

## Data Flow (detailed)

### 1. Incident submission

```
victim PWA
  POST /v1/incidents
  body: {
    profile_id?,
    device_id,
    location: { lat, lng, accuracy } | { description },
    raw_text,
    needs: { medical?: bool, trapped?: bool, ... },
    inventory_have: ["epipen", ...],
    inventory_need: ["insulin", ...],
    timestamp
  }
       │
       ▼
services/api
  - validate against @disaster/types
  - if location is description-only, call:
      CALL SNOWFLAKE.UDF_RESOLVE_LANDMARK(description, last_known_lat, last_known_lng)
  - INSERT INTO INCIDENTS_RAW (...)
  - return { incident_id, status: 'received' }
```

### 2. Auto-triage pipeline (entirely in Snowflake)

```
STREAM incident_stream ON INCIDENTS_RAW
       │
       ▼ (fires every 5s while stream has data)
TASK triage_task:
  INSERT INTO INCIDENTS_ENRICHED
  SELECT
    i.*,
    PARSE_JSON(SNOWFLAKE.CORTEX.COMPLETE(
      'claude-3-5-sonnet',
      'You are a disaster triage AI. Score severity 0-100, ' ||
      'categorize, list 3 reasons, list required_resources. ' ||
      'INCIDENT: ' || i.raw_text || ' PROFILE: ' || p.payload ||
      'NEEDS: ' || i.needs::STRING
    )) AS severity_json,
    SNOWFLAKE.CORTEX.SUMMARIZE(i.raw_text) AS summary,
    -- vector embedding for dedup
    SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', i.raw_text) AS embedding
  FROM incident_stream i
  LEFT JOIN PROFILES p USING (profile_id);
```

### 3. Dedup + clustering (Dynamic Table)

```sql
CREATE OR REPLACE DYNAMIC TABLE INCIDENT_CLUSTERS
  TARGET_LAG = '15 seconds'
  WAREHOUSE = compute_wh
AS
WITH spatial AS (
  SELECT
    incident_id,
    ST_CLUSTER_KMEANS(
      ST_MAKEPOINT(lng, lat),
      8       -- k = 8 clusters for demo
    ) OVER () AS spatial_cluster_id,
    summary,
    embedding
  FROM INCIDENTS_ENRICHED
  WHERE status = 'open'
    AND ts > DATEADD(minute, -30, CURRENT_TIMESTAMP())
),
semantic AS (
  -- Cortex Search: incidents within 100m AND cosine sim > 0.85 → merge
  SELECT
    a.incident_id AS primary_id,
    b.incident_id AS duplicate_id
  FROM spatial a
  JOIN spatial b ON a.spatial_cluster_id = b.spatial_cluster_id
    AND a.incident_id < b.incident_id
    AND VECTOR_COSINE_SIMILARITY(a.embedding, b.embedding) > 0.85
)
SELECT * FROM spatial
LEFT JOIN semantic ON spatial.incident_id = semantic.duplicate_id;
```

### 4. Dispatch (Snowflake stored proc)

```sql
CALL DISPATCH_INCIDENTS();
-- For each open unassigned incident (severity DESC):
--   find nearest available responder unit matching required_resources
--   INSERT INTO ASSIGNMENTS (incident_id, responder_id, eta_sec)
--   UPDATE RESPONDERS SET status='busy' WHERE id=...
```

Triggered by:
- TASK every 30s
- Manual trigger when sev≥80 incident lands
- Manual trigger when unit marked resolved (frees up)

### 5. Route polyline

```
API calls Mapbox Optimization API with:
  - Origin: responder current_location
  - Stops: assigned incidents in priority order
Stores polyline in ROUTES table
Pushes via SSE: { event: 'route_update', responder_id, polyline }
```

### 6. Push to dashboard

```
services/api maintains an SSE channel at GET /v1/stream
On each TASK completion, API polls Snowflake CHANGES clause:
  SELECT * FROM INCIDENTS_ENRICHED CHANGES(INFORMATION => APPEND_ONLY)
    AT(TIMESTAMP => :last_poll);
Emits SSE messages: 'incident_new', 'cluster_update', 'assignment_new', 'route_update', 'resource_update'.
```

---

## Domain Model (shared types)

Lives in `packages/types/src/index.ts`. All apps import from `@disaster/types`.

```ts
export type ResourceType =
  | 'police' | 'fire' | 'ems' | 'paramedic'
  | 'nurse' | 'doctor' | 'volunteer';

export type IncidentCategory =
  | 'medical' | 'trapped' | 'fire' | 'water'
  | 'shelter' | 'power' | 'evacuation' | 'unknown';

export type DeviceFlag =
  | 'epipen' | 'inhaler' | 'insulin' | 'first_aid'
  | 'mobility_aid' | 'oxygen' | 'aed';

export interface Profile {
  profile_id: string;
  device_id: string;
  name: string;
  age: number;
  conditions: string[];        // e.g. ['diabetes', 'heart_condition']
  devices_owned: DeviceFlag[];
  emergency_contact?: { name: string; phone: string };
  created_at: string;
}

export interface IncidentLocation {
  lat: number;
  lng: number;
  accuracy_m?: number;
  source: 'gps' | 'landmark_udf' | 'manual';
  confidence?: number;         // 0..1, only when source='landmark_udf'
  description?: string;        // original landmark text when applicable
}

export interface IncidentRaw {
  incident_id: string;
  profile_id?: string;
  device_id: string;
  location: IncidentLocation;
  raw_text: string;
  needs: Partial<Record<IncidentCategory, boolean>>;
  inventory_have: DeviceFlag[];
  inventory_need: DeviceFlag[];
  ts: string;
}

export interface SeverityResult {
  score: number;               // 0..100
  category: IncidentCategory;
  top_reasons: [string, string, string];
  required_resources: Partial<Record<ResourceType, number>>;
  confidence: number;          // 0..1
}

export interface IncidentEnriched extends IncidentRaw {
  severity: SeverityResult;
  summary: string;
  cluster_id?: string;
  primary_of_duplicate_group?: string;
  status: 'open' | 'assigned' | 'in_progress' | 'resolved';
}

export interface Responder {
  responder_id: string;
  type: ResourceType;
  callsign: string;
  current_location?: { lat: number; lng: number };
  status: 'available' | 'busy' | 'offline';
}

export interface Assignment {
  assignment_id: string;
  incident_id: string;
  responder_id: string;
  eta_sec: number;
  polyline?: string;           // encoded polyline from Mapbox
  status: 'enroute' | 'on_scene' | 'completed';
  assigned_at: string;
}

export interface ClusterView {
  cluster_id: string;
  centroid: { lat: number; lng: number };
  incident_ids: string[];
  total_severity: number;
  category_breakdown: Partial<Record<IncidentCategory, number>>;
}

export interface ResourceRoster {
  type: ResourceType;
  total: number;
  available: number;
  busy: number;
}

// SSE event envelope
export type SSEEvent =
  | { type: 'incident_new'; data: IncidentEnriched }
  | { type: 'incident_update'; data: IncidentEnriched }
  | { type: 'cluster_update'; data: ClusterView }
  | { type: 'assignment_new'; data: Assignment }
  | { type: 'route_update'; data: { responder_id: string; polyline: string } }
  | { type: 'resource_update'; data: ResourceRoster[] };
```

---

## Snowflake Object Inventory

### Tables (transactional)
- `PROFILES` — victim pre-reg
- `INCIDENTS_RAW` — incoming reports
- `RESPONDERS` — unit roster
- `ASSIGNMENTS` — unit → incident
- `ROUTES` — Mapbox polylines cache

### Dynamic Tables (auto-refresh)
- `INCIDENTS_ENRICHED` (TARGET_LAG 15s) — Cortex severity + summary + embedding joined
- `INCIDENT_CLUSTERS` (TARGET_LAG 15s) — spatial + semantic clustering
- `RESOURCE_ROSTER` (TARGET_LAG 5s) — live `available/total` per type
- `SEVERITY_HEATMAP_H3` (TARGET_LAG 30s) — H3 bucket aggregates for deck.gl heatmap

### Streams
- `INCIDENT_STREAM` ON `INCIDENTS_RAW` — drives triage task

### Tasks
- `TRIAGE_TASK` (every 5s, suspends on empty stream) — invokes Cortex on new rows
- `DISPATCH_TASK` (every 30s) — calls `DISPATCH_INCIDENTS()` stored proc

### Stored Procedures
- `DISPATCH_INCIDENTS()` — greedy assignment by severity × distance × resource match
- `MARK_RESOLVED(incident_id)` — closes incident, frees responder
- `START_SCENARIO(scenario_name)` — bulk-inserts staggered scenario data

### Snowpark Python UDFs
- `UDF_RESOLVE_LANDMARK(description, last_lat, last_lng)` → `(lat, lng, confidence, reasoning)`

### Cortex Functions used
- `SNOWFLAKE.CORTEX.COMPLETE` — severity scoring + required_resources JSON
- `SNOWFLAKE.CORTEX.SUMMARIZE` — incident summary for dashboard
- `SNOWFLAKE.CORTEX.EMBED_TEXT_768` — embeddings for dedup
- `VECTOR_COSINE_SIMILARITY` — semantic dedup matching

### Geo functions used
- `ST_MAKEPOINT`, `ST_DISTANCE`, `ST_CLUSTER_KMEANS`, `H3_LATLNG_TO_CELL`

---

## API Endpoints (`services/api`)

| Method | Path                          | Owner-ship    | Purpose                                                      |
| ------ | ----------------------------- | ------------- | ------------------------------------------------------------ |
| POST   | `/v1/profiles`                | victim        | Create/upsert pre-reg profile                                |
| GET    | `/v1/profiles/:device_id`     | victim        | Load existing profile                                        |
| POST   | `/v1/incidents`               | victim        | Submit new incident; runs landmark UDF if needed             |
| GET    | `/v1/incidents/:id`           | victim/admin  | Read enriched incident (status screen polling)               |
| PATCH  | `/v1/incidents/:id/inventory` | victim        | Update need/have flags mid-incident                          |
| GET    | `/v1/dashboard/state`         | responder     | Initial dashboard snapshot (incidents, clusters, roster)     |
| GET    | `/v1/stream`                  | responder     | SSE channel for live updates                                 |
| POST   | `/v1/roster`                  | responder     | Set responder counts per type                                |
| POST   | `/v1/assignments/:id/status`  | responder     | Mark `on_scene` / `completed`                                |
| POST   | `/v1/admin/scenario/start`    | admin         | Trigger scenario play (e.g. `texas-flood`)                   |
| POST   | `/v1/admin/scenario/inject`   | admin         | Drop a single high-sev incident mid-demo (judge demo trick)  |

All responses are typed against `@disaster/types`.

---

## Repo Layout

```
disaster-relief/
├── apps/
│   ├── victim/
│   │   ├── src/
│   │   │   ├── pages/Home.tsx
│   │   │   ├── pages/Onboard.tsx
│   │   │   ├── pages/Incident.tsx
│   │   │   ├── pages/Status.tsx
│   │   │   ├── pages/Inventory.tsx
│   │   │   ├── lib/api.ts
│   │   │   ├── lib/geo.ts        # navigator.geolocation wrapper + offline queue
│   │   │   └── main.tsx
│   │   ├── public/manifest.webmanifest
│   │   ├── public/service-worker.ts
│   │   ├── index.html
│   │   ├── vite.config.ts
│   │   └── package.json
│   └── responder/
│       ├── src/
│       │   ├── pages/Dashboard.tsx
│       │   ├── components/MapView.tsx
│       │   ├── components/IncidentSheet.tsx
│       │   ├── components/IncidentQueue.tsx
│       │   ├── components/FiltersPanel.tsx
│       │   ├── components/RouteDrawer.tsx
│       │   ├── components/ResourceRoster.tsx
│       │   ├── components/StatsBar.tsx
│       │   ├── lib/api.ts
│       │   ├── lib/sse.ts
│       │   ├── lib/map/mapbox.ts   # adapter
│       │   ├── lib/map/leaflet.ts  # nice-to-have fallback
│       │   └── main.tsx
│       ├── vite.config.ts
│       └── package.json
├── services/
│   └── api/
│       ├── src/
│       │   ├── index.ts            # Hono app + routes wiring
│       │   ├── routes/incidents.ts
│       │   ├── routes/dashboard.ts
│       │   ├── routes/admin.ts
│       │   ├── lib/snowflake.ts    # connection pool, query helpers
│       │   ├── lib/mapbox.ts       # Optimization API client
│       │   ├── lib/sse.ts          # broadcast channel
│       │   └── lib/scenarios.ts    # scenario loader + scheduler
│       └── package.json
├── packages/
│   └── types/
│       ├── src/index.ts            # the contract
│       └── package.json
├── snowflake/
│   ├── 01_schema.sql               # tables, streams
│   ├── 02_cortex_triage.sql        # triage task using Cortex
│   ├── 03_dynamic_tables.sql       # INCIDENTS_ENRICHED, CLUSTERS, ROSTER, HEATMAP
│   ├── 04_dispatch_proc.sql        # DISPATCH_INCIDENTS stored proc
│   ├── 05_udf_location.py          # Snowpark Python UDF
│   ├── 06_scenario_proc.sql        # START_SCENARIO stored proc
│   └── README.md                   # apply-order instructions
├── scenarios/
│   └── texas-flood.json            # 50 incident specs
├── docs/
│   ├── PLAN.md
│   ├── CONTEXT.md  (you are here)
│   ├── TASKS.md
│   ├── STACK.md
│   ├── DEMO.md
│   └── TEMPLATE.md
├── .env.example
├── .gitignore
├── package.json
├── pnpm-workspace.yaml
├── tsconfig.base.json
└── README.md
```

---

## Conventions

- **TypeScript everywhere.** No JS files. Strict mode on.
- **No domain types defined outside `packages/types`.** If you need a new type, add it there.
- **API is the only Snowflake client.** Apps never connect to Snowflake.
- **All SQL files in `snowflake/` are runnable in order.** Numbered prefix = apply order.
- **Tailwind for styling.** No CSS modules, no styled-components.
- **Env vars** loaded from `.env` files via Vite's `import.meta.env` (frontend) or `dotenv` (API). Names in `.env.example`.
- **Commits**: conventional commit prefixes (`feat:`, `fix:`, `chore:`, `docs:`).
- **Branches**: `track/victim`, `track/responder`, `track/api`, `track/snowflake`; merge to `main` via PR-light review (just a thumbs-up; we're moving fast).

---

## Anti-Patterns We Avoid

| Tempting                                                                            | Don't because                                                                      |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Calling Cortex from the API server                                                  | Defeats the prize. All AI must live in the warehouse.                              |
| Storing severity in the API and only writing to Snowflake after                     | Same.                                                                              |
| Duplicating `Incident` type across apps                                             | Drift. Use `@disaster/types`.                                                      |
| Mapbox API key in the frontend bundle without a referrer restriction                | Public token is OK with referrer restriction; set on Mapbox dashboard.             |
| Adding "real-time" by polling every 500ms                                           | Use SSE. Polling that fast burns the laptop in demo.                               |
| Polishing UI before Cortex pipeline ships                                           | The pipeline is the demo. UI must work, but the AI is the story.                   |
| Building Hungarian algorithm dispatch                                               | Greedy is fine. Save 4 hours.                                                      |
| Trying to make ElevenLabs work in v1                                                | It's a stretch. Text submission ships first. Voice is a drop-in once base is done. |

---

## When stuck

- API connectivity to Snowflake broken? Check `SF_PRIVATE_KEY_PATH` env, role grants on the warehouse.
- Dynamic Table not refreshing? `ALTER DYNAMIC TABLE x REFRESH;` manually. Check `SHOW DYNAMIC TABLES;` for `last_refresh_status`.
- Cortex returning gibberish? Lower temperature, force JSON with `response_format`, validate against `SeverityResult` shape; fall back to default `{score:50, category:'unknown', ...}` on parse failure.
- Map blank? Mapbox token missing or wrong scope; check Network tab for 401.
- SSE not arriving? CORS, check `EventSource` URL matches API origin, no proxy buffering.
