# STACK — Tech Choices

| Layer            | Tech                                                          | Version (target) | Why                                                                                       |
| ---------------- | ------------------------------------------------------------- | ---------------- | ----------------------------------------------------------------------------------------- |
| Language         | TypeScript                                                    | 5.6.x            | Shared types across all client + server. Strict mode.                                     |
| Runtime          | Node.js (services/api)                                        | 22 LTS           | Latest stable, native fetch + WebSocket, ESM friendly.                                    |
| Package mgr      | pnpm                                                          | 9.x              | Workspace support, fast, disk-efficient.                                                  |
| Build (apps)     | Vite                                                          | 7.x              | Fast HMR. PWA via `vite-plugin-pwa`.                                                      |
| UI framework     | React                                                         | 19.x             | Standard, both apps.                                                                       |
| Routing (apps)   | React Router                                                  | 6.x              | Hash routes for PWA to avoid 404s.                                                         |
| Styling          | Tailwind CSS                                                  | 4.x              | Zero-config, dark mode, fast.                                                              |
| Icons            | lucide-react                                                  | latest           | One package, tree-shaken.                                                                  |
| State (dash)     | Zustand                                                       | 5.x              | Tiny, no boilerplate, no provider tree.                                                    |
| Animations       | Framer Motion                                                 | 11.x             | Pin entry + cluster merge animations.                                                      |
| Map base         | Mapbox GL JS                                                  | 3.x              | Best maps for demo eye-candy. Free 50k loads/mo.                                          |
| Map overlay      | deck.gl + @deck.gl/mapbox                                     | 9.x              | GPU heatmap + clustered scatter. Looks insane on demo.                                    |
| Routing API      | Mapbox Optimization v1                                        | —                | Same Mapbox account; multi-stop TSP-ish; free tier covers demo.                            |
| API framework    | Hono                                                          | 4.x              | Tiny, fast, runs anywhere, great TS DX.                                                    |
| API server       | `@hono/node-server`                                           | latest           | Run Hono on plain Node.                                                                    |
| Snowflake driver | snowflake-sdk                                                 | latest           | Official Node driver, supports key-pair auth.                                              |
| Snowflake AI     | SNOWFLAKE.CORTEX.COMPLETE (model: `claude-3-5-sonnet`)        | —                | Best reasoning for severity scoring + JSON output.                                         |
| Snowflake search | SNOWFLAKE.CORTEX.EMBED_TEXT_768 (`e5-base-v2`) + VECTOR_COSINE_SIMILARITY | —    | Vector dedup of incident reports.                                                          |
| Snowflake geo    | GEOGRAPHY type, ST_DISTANCE, ST_CLUSTER_KMEANS, H3            | —                | Native spatial fns, no GIS extension needed.                                               |
| Snowflake CDC    | STREAM + TASK on INCIDENTS_RAW                                | —                | Auto-triage trigger with zero glue code.                                                   |
| Snowflake views  | Dynamic Tables (TARGET_LAG 15s)                               | —                | Auto-refresh enrichment + clusters + heatmap + roster.                                     |
| Snowflake UDF    | Snowpark Python                                               | 3.10             | Landmark-to-coords reasoning UDF.                                                          |
| Validation       | Zod                                                           | 3.x              | Runtime validation of API bodies + Cortex JSON output.                                     |
| Logging          | pino                                                          | 9.x              | Structured logs, fast.                                                                     |
| Env loading      | dotenv                                                        | 16.x             | API only; Vite handles frontend env.                                                       |
| Push to client   | Server-Sent Events (native EventSource)                       | —                | Simpler than WebSocket; one-way is all we need.                                            |
| Forms (victim)   | react-hook-form                                               | 7.x              | Quick pre-reg form.                                                                        |
| Service worker   | vite-plugin-pwa (workbox under the hood)                      | latest           | Offline queue, install prompt.                                                             |
| IndexedDB        | idb-keyval                                                    | latest           | Offline incident queue persistence.                                                        |

## Sponsor / Optional

| Layer                | Tech                                       | Status     | Notes                                                              |
| -------------------- | ------------------------------------------ | ---------- | ------------------------------------------------------------------ |
| Voice agent          | ElevenLabs Conversational AI               | Stretch    | Drop-in to replace text submission; webhook → same incident shape. |
| LLM caching/routing  | TensorMesh                                 | Nice-only  | Wraps Cortex calls if time; sponsor prize secondary.                |
| Tunneling            | Cloudflare Tunnel (`cloudflared`)          | Conditional | Only needed if ElevenLabs added.                                    |

## Skipped

| Considered                 | Why skipped                                                  |
| -------------------------- | ------------------------------------------------------------ |
| Next.js                    | Overhead. Vite is faster for hackathon.                      |
| Supabase / Firebase        | Snowflake is the hard constraint + the prize.                |
| WebSockets                 | SSE is enough for one-way push.                              |
| Clerk / Auth0 / Supabase Auth | Demo doesn't need real auth.                              |
| Twilio                     | No phone-call infra needed for v1 (text-first).              |
| Hungarian algorithm        | Greedy assignment ships in 1 hour and demos identically.     |
| Native iOS/Android         | PWA install does the job.                                     |

## Hosting

- **All apps**: localhost during demo. Laptop is the rig.
- **API tunnel**: only if ElevenLabs is wired (Cloudflare Tunnel).
- **Snowflake**: cloud, sponsor account.

If we have stretch capacity: deploy frontends to Vercel (free), API to Railway (free starter), share URL with judges so they can poke from their phones.

## Environment Variables

See `.env.example`. Sensitive secrets never committed; share via 1Password / Notion secrets page during the build.

## Dependency Footprint Goal

Each app should be < 1MB gzipped JS. We are not building Photoshop. Aggressive imports, no kitchen-sink utility libraries beyond what's listed above.
