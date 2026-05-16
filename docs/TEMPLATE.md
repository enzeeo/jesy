# TEMPLATE — One-Shot Scaffold Spec

> **Audience**: the one engineer (or agent) who will scaffold this repo in a single pass before the 4-track build begins.
>
> **Goal**: by end of this task, `pnpm install && pnpm dev` brings up all three apps, all three apps import from `@disaster/types`, and `.env.example` is complete. Time budget: **~1.5 hours**.

---

## Sequence

1. **Init root** (5 min)
2. **Create `packages/types`** (10 min) — write all domain types from `CONTEXT.md §Domain Model`
3. **Scaffold `services/api`** (15 min)
4. **Scaffold `apps/responder`** (20 min) — slightly more setup (Mapbox + Tailwind)
5. **Scaffold `apps/victim`** (20 min) — Tailwind + PWA plugin
6. **Stub Snowflake SQL files** (10 min) — empty but applied-in-order skeleton
7. **Stub scenarios JSON** (5 min) — 3 placeholder incidents
8. **Verify all three dev servers start** (5 min)
9. **Commit + tag `template-ready`** (5 min)

---

## Step 1 — Root Init

```bash
pnpm init
```

Edit `package.json`:

```json
{
  "name": "disaster-relief",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "packageManager": "pnpm@9.12.0",
  "scripts": {
    "dev": "pnpm -r --parallel --filter='./apps/*' --filter='./services/*' dev",
    "dev:victim": "pnpm --filter @disaster/victim dev",
    "dev:responder": "pnpm --filter @disaster/responder dev",
    "dev:api": "pnpm --filter @disaster/api dev",
    "build": "pnpm -r build",
    "typecheck": "pnpm -r typecheck"
  },
  "devDependencies": {
    "typescript": "^5.6.0"
  }
}
```

Create `pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/*"
  - "services/*"
  - "packages/*"
```

Create `tsconfig.base.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": false,
    "jsx": "react-jsx"
  }
}
```

Create `.gitignore`:

```
node_modules/
dist/
.env
.env.local
*.log
.DS_Store
.snowflake/
.vite/
.turbo/
coverage/
*.tsbuildinfo
```

Create `.npmrc`:

```
auto-install-peers=true
strict-peer-dependencies=false
```

---

## Step 2 — `packages/types`

```bash
mkdir -p packages/types/src
cd packages/types
pnpm init
```

`packages/types/package.json`:

```json
{
  "name": "@disaster/types",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  },
  "scripts": {
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "typescript": "^5.6.0"
  }
}
```

`packages/types/tsconfig.json`:

```json
{
  "extends": "../../tsconfig.base.json",
  "include": ["src/**/*.ts"]
}
```

`packages/types/src/index.ts` — **copy verbatim from `docs/CONTEXT.md §Domain Model`**. This is the contract.

---

## Step 3 — `services/api`

```bash
mkdir -p services/api/src/{routes,lib}
cd services/api
pnpm init
```

`services/api/package.json`:

```json
{
  "name": "@disaster/api",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc -p tsconfig.json",
    "start": "node dist/index.js",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@disaster/types": "workspace:*",
    "@hono/node-server": "^1.13.0",
    "dotenv": "^16.4.0",
    "hono": "^4.6.0",
    "pino": "^9.0.0",
    "snowflake-sdk": "^1.13.0",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "tsx": "^4.19.0",
    "typescript": "^5.6.0",
    "vitest": "latest"
  }
}
```

`services/api/tsconfig.json`:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "dist",
    "module": "ESNext",
    "moduleResolution": "bundler"
  },
  "include": ["src/**/*.ts"]
}
```

`services/api/src/index.ts`:

```ts
import 'dotenv/config';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { serve } from '@hono/node-server';

const app = new Hono();

app.use('*', logger());
app.use('*', cors({ origin: '*' }));

app.get('/health', (c) => c.json({ ok: true, service: 'disaster-api', ts: new Date().toISOString() }));

// Routes will mount here:
// app.route('/v1/incidents', incidentsRouter);
// app.route('/v1/dashboard', dashboardRouter);
// app.route('/v1/admin', adminRouter);

const port = Number(process.env.PORT ?? 8787);
serve({ fetch: app.fetch, port });
console.log(`api listening on http://localhost:${port}`);
```

Stub files (empty exports, to be filled by Track C):

```bash
touch src/routes/incidents.ts src/routes/dashboard.ts src/routes/admin.ts
touch src/lib/snowflake.ts src/lib/mapbox.ts src/lib/sse.ts src/lib/scenarios.ts
```

Each stub starts as:

```ts
export {};
```

---

## Step 4 — `apps/responder`

```bash
cd ../../apps
pnpm create vite responder --template react-ts
cd responder
```

Then patch its `package.json` to:

```json
{
  "name": "@disaster/responder",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --port 5174",
    "build": "tsc -b && vite build",
    "preview": "vite preview --port 5174",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@disaster/types": "workspace:*",
    "@deck.gl/core": "^9.0.0",
    "@deck.gl/layers": "^9.0.0",
    "@deck.gl/mapbox": "^9.0.0",
    "framer-motion": "^11.0.0",
    "lucide-react": "^0.460.0",
    "mapbox-gl": "^3.7.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^6.27.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@types/mapbox-gl": "^3.4.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "typescript": "^5.6.0",
    "vite": "^7.0.0"
  }
}
```

`apps/responder/vite.config.ts`:

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5174 },
});
```

`apps/responder/src/main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`apps/responder/src/App.tsx`:

```tsx
export default function App() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 grid place-items-center">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-mono">Disaster Relief — Responder</h1>
        <p className="text-zinc-400">Dashboard scaffold ready. Build me out.</p>
      </div>
    </div>
  );
}
```

`apps/responder/src/index.css`:

```css
@import "tailwindcss";

html, body, #root {
  height: 100%;
  margin: 0;
}
```

---

## Step 5 — `apps/victim`

```bash
cd ..
pnpm create vite victim --template react-ts
cd victim
pnpm add vite-plugin-pwa idb-keyval react-router-dom react-hook-form
pnpm add -D @vitejs/plugin-react tailwindcss @tailwindcss/vite
```

Patch `apps/victim/package.json`:

```json
{
  "name": "@disaster/victim",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --port 5173",
    "build": "tsc -b && vite build",
    "preview": "vite preview --port 5173",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@disaster/types": "workspace:*",
    "idb-keyval": "^6.2.0",
    "lucide-react": "^0.460.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-hook-form": "^7.53.0",
    "react-router-dom": "^6.27.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "typescript": "^5.6.0",
    "vite": "^7.0.0",
    "vite-plugin-pwa": "^0.20.0"
  }
}
```

`apps/victim/vite.config.ts`:

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Disaster Relief — Help',
        short_name: 'Help',
        description: 'Get help during a disaster',
        theme_color: '#dc2626',
        background_color: '#09090b',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
  server: { port: 5173 },
});
```

`apps/victim/src/App.tsx`:

```tsx
export default function App() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 grid place-items-center px-6">
      <div className="text-center space-y-4 max-w-md">
        <h1 className="text-3xl font-bold">Disaster Relief</h1>
        <p className="text-zinc-400">Press the button below if you need help.</p>
        <button className="w-full bg-red-600 hover:bg-red-500 active:bg-red-700 text-white text-xl font-bold py-6 rounded-2xl shadow-lg">
          I NEED HELP
        </button>
      </div>
    </main>
  );
}
```

Same `index.css` as responder (Tailwind import).

Add placeholder icons (replace later with real icons):

```bash
# Use any 192x192 and 512x512 PNG placeholder in public/
touch public/icon-192.png public/icon-512.png
```

---

## Step 6 — Snowflake SQL Skeleton

```bash
mkdir -p snowflake
```

Create empty-but-named files:

```bash
touch snowflake/01_schema.sql
touch snowflake/02_cortex_triage.sql
touch snowflake/03_dynamic_tables.sql
touch snowflake/04_dispatch_proc.sql
touch snowflake/05_udf_location.py
touch snowflake/06_scenario_proc.sql
touch snowflake/README.md
```

`snowflake/01_schema.sql` — minimal skeleton:

```sql
-- Apply with: snowsql -f 01_schema.sql
-- Or paste into Snowflake worksheet sequentially.

USE WAREHOUSE COMPUTE_WH;
USE DATABASE DISASTER_RELIEF;
USE SCHEMA PUBLIC;

-- =============================================================
-- PROFILES
-- =============================================================
CREATE TABLE IF NOT EXISTS PROFILES (
  profile_id          STRING PRIMARY KEY,
  device_id           STRING,
  name                STRING,
  age                 NUMBER,
  conditions          ARRAY,
  devices_owned       ARRAY,
  emergency_contact   VARIANT,
  payload             VARIANT,        -- raw json for Cortex prompt convenience
  created_at          TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- INCIDENTS_RAW (the ingest table)
-- =============================================================
CREATE TABLE IF NOT EXISTS INCIDENTS_RAW (
  incident_id         STRING PRIMARY KEY,
  profile_id          STRING,
  device_id           STRING,
  lat                 FLOAT,
  lng                 FLOAT,
  accuracy_m          FLOAT,
  location_source     STRING,         -- 'gps' | 'place_description_udf' | 'manual'
  location_confidence FLOAT,
  raw_text            STRING,
  needs               VARIANT,
  inventory_have      ARRAY,
  inventory_need      ARRAY,
  ts                  TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- `INCIDENTS_ENRICHED` is a physical table written by TRIAGE_TASK, not a Dynamic Table.
CREATE TABLE IF NOT EXISTS INCIDENTS_ENRICHED (
  incident_id         STRING PRIMARY KEY,
  profile_id          STRING,
  device_id           STRING,
  lat                 FLOAT,
  lng                 FLOAT,
  raw_text            STRING,
  severity            VARIANT,
  triage_status       STRING DEFAULT 'ok',  -- ok | degraded
  summary             STRING,
  embedding           VECTOR(FLOAT, 768),
  status              STRING DEFAULT 'open',
  enriched_at         TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- RESPONDERS
-- =============================================================
CREATE TABLE IF NOT EXISTS RESPONDERS (
  responder_id        STRING PRIMARY KEY,
  type                STRING,         -- police | fire | ems | paramedic | nurse | doctor | volunteer
  callsign            STRING,
  current_lat         FLOAT,
  current_lng         FLOAT,
  status              STRING DEFAULT 'available'  -- available | busy | offline
);

-- =============================================================
-- ASSIGNMENTS
-- =============================================================
CREATE TABLE IF NOT EXISTS ASSIGNMENTS (
  assignment_id       STRING PRIMARY KEY,
  incident_id         STRING,
  responder_id        STRING,
  resource_type       STRING,
  eta_sec             NUMBER,
  status              STRING DEFAULT 'enroute',   -- enroute | on_scene | completed
  assigned_at         TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- UNMET_RESOURCE_NEEDS
-- =============================================================
CREATE TABLE IF NOT EXISTS UNMET_RESOURCE_NEEDS (
  incident_id         STRING,
  resource_type       STRING,
  quantity_needed     NUMBER,
  reason              STRING,         -- no_available_responder | responder_offline
  updated_at          TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- ROUTES
-- =============================================================
CREATE TABLE IF NOT EXISTS ROUTES (
  responder_id        STRING PRIMARY KEY,
  polyline            STRING,
  total_duration_sec  NUMBER,
  updated_at          TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- STREAM on INCIDENTS_RAW (drives triage)
-- =============================================================
CREATE OR REPLACE STREAM INCIDENT_STREAM ON TABLE INCIDENTS_RAW
  APPEND_ONLY = TRUE;
```

`snowflake/README.md`:

```markdown
# Snowflake apply order

1. `01_schema.sql` — tables + stream
2. `02_cortex_triage.sql` — triage task (Cortex severity)
3. `03_dynamic_tables.sql` — INCIDENT_CLUSTERS + RESOURCE_ROSTER + SEVERITY_HEATMAP_H3
4. `04_dispatch_proc.sql` — DISPATCH_INCIDENTS stored proc + DISPATCH_TASK
5. `05_udf_location.py` — Snowpark UDF for GPS-missing place description → coords
6. `06_scenario_proc.sql` — optional Snowflake scenario helpers; API owns v1 demo timing

After applying, run `SHOW DYNAMIC TABLES;` and confirm `last_refresh_status = SUCCEEDED`.
```

Other 5 files start empty with a comment header (so the placeholder shows intent):

```sql
-- snowflake/02_cortex_triage.sql
-- TODO Track D H1–H3: Cortex severity triage task on INCIDENT_STREAM.
```

---

## Step 7 — Scenario stub

`scenarios/texas-flood.json`:

```json
{
  "name": "texas-flood",
  "label": "Houston Flash Flood, May 2026",
  "center": { "lat": 29.76, "lng": -95.37 },
  "duration_sec": 60,
  "incidents": [
    {
      "delay_sec": 2,
      "lat": 29.78,
      "lng": -95.38,
      "raw_text": "I'm trapped on my roof, water is up to my chest, I'm 67 and diabetic.",
      "needs": { "medical": true, "trapped": true, "water": true },
      "inventory_have": ["insulin"],
      "inventory_need": [],
      "profile": { "age": 67, "conditions": ["diabetes"], "devices_owned": ["insulin"] }
    },
    {
      "delay_sec": 4,
      "lat": 29.74,
      "lng": -95.40,
      "raw_text": "Power is out, my baby needs formula and I can't drive out, streets are flooded.",
      "needs": { "shelter": true, "water": true, "power": true },
      "inventory_have": [],
      "inventory_need": [],
      "profile": { "age": 28, "conditions": [], "devices_owned": [] }
    },
    {
      "delay_sec": 6,
      "lat": 29.81,
      "lng": -95.32,
      "raw_text": "Apartment fire on the second floor, lots of smoke, six families still inside.",
      "needs": { "fire": true, "trapped": true },
      "inventory_have": [],
      "inventory_need": [],
      "profile": null
    }
  ]
}
```

(Track D will expand to 50 with varied severities and locations.)

---

## Step 8 — Verify

```bash
cd /Users/enzeeo/bluescreen/jezy
pnpm install
pnpm dev
```

Expected output:

- `api listening on http://localhost:8787` → `curl localhost:8787/health` returns `{ ok: true, ... }`
- Victim PWA on `http://localhost:5173` → "I NEED HELP" red button
- Responder dash on `http://localhost:5174` → "Disaster Relief — Responder" with dark theme

If any of those fail, fix before tagging.

```bash
pnpm typecheck
```

Should pass with zero errors.

---

## Step 9 — Commit + Tag

```bash
git add .
git commit -m "chore: scaffold pnpm monorepo + apps + types + snowflake skeleton"
git tag template-ready
```

Notify the team: pull `main`, branch off:

- Track A: `git checkout -b track/victim`
- Track B: `git checkout -b track/responder`
- Track C: `git checkout -b track/api`
- Track D: `git checkout -b track/snowflake`

---

## What this scaffold does NOT include (do not bloat)

- Storybook
- ESLint / Prettier configs (use editor defaults; lint at end if time)
- Full frontend/E2E test suites (API tests are required; broader test suites are out of scope)
- CI/CD
- Docker
- Husky / lint-staged
- README polish (the existing root `README.md` is enough; final polish is at H16)

Resist scope creep. If you find yourself adding a config file not in this spec, stop and ask the team lead.
