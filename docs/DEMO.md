# DEMO — 4-Minute Judge Script

Target length: **4 minutes**. Practice twice before submitting.

---

## Pre-Demo Checklist (5 min before)

- [ ] All three apps running locally: victim PWA (port 5173), responder dash (5174), API (8787)
- [ ] Snowflake worksheet open in browser tab, ready to flip to
- [ ] Browser tab 1: `localhost:5174` (responder dash, fullscreen, dark mode confirmed)
- [ ] Browser tab 2: `localhost:5173` (victim PWA on phone-sized window, e.g. DevTools iPhone 12 Pro view)
- [ ] Browser tab 3: Snowflake worksheet
- [ ] Browser tab 4: deck.gl / Cortex doc page (bail-out reference)
- [ ] Cleared previous scenario data: `TRUNCATE INCIDENTS_RAW;` then re-seed roster
- [ ] Roster set: 5 fire, 4 EMT, 3 paramedic, 2 nurse, 2 doctor, 6 police, 10 volunteer
- [ ] Open `scenarios/texas-flood.json` in a code window for show-and-tell

---

## The Story (memorize this)

> *"Texas, last week. Houston flash flooded. Emergency call centers got 40,000 calls in two hours. People who needed help most never got through. Today we built the system that fixes that — and the entire AI brain runs inside Snowflake."*

---

## Beat-by-Beat Script

### Beat 1 — Hook (0:00–0:30, 30s)

**Show**: responder dashboard, blank map of Houston.

**Say**: *"This is a first responder command center, set up for the Houston metro area. Right now it's empty — no disaster. Let me start a real-time simulation of a Texas flash flood: 50 victim reports over 60 seconds."*

**Do**: Click **Start Scenario** button.

---

### Beat 2 — The Flood (0:30–1:30, 60s)

**Show**: Pins fly onto the map, severity colors blooming. Heatmap intensifies. Right sidebar populates.

**Say**: *"As victims report in, the dashboard fills in real time. But these aren't just dots — every one is being analyzed by Snowflake Cortex AI right now."*

**Do**: Click on one pin with severity 92.

**Show**: Side sheet opens with transcript, severity 92, 3 reasons.

**Say**: *"This is Sarah, 67, diabetic, stuck on her roof in Spring Branch. Cortex saw her age + her insulin dependency + the rising-water language in her transcript, and pushed her to severity 92. Notice the three reasons — those came straight from the warehouse, not a separate API."*

---

### Beat 3 — The Deduplication Magic (1:30–2:15, 45s)

**Show**: A cluster forming over an apartment complex.

**Say**: *"Watch this — six different people just called about the same apartment fire."*

**Do**: Zoom in. Show the cluster merging from 6 separate pins into one larger cluster icon.

**Say**: *"Snowflake's Cortex Search is computing vector embeddings on every transcript. When semantic similarity exceeds 85% and the calls are within 100 meters, the Dynamic Table merges them into a single incident. Six tickets, one dispatch. No duplicate trucks."*

**Optional flip to Snowflake tab**: Show `SELECT * FROM INCIDENT_CLUSTERS LIMIT 5;` — point at the `duplicate_id` column.

---

### Beat 4 — Smart Dispatch (2:15–3:00, 45s)

**Show**: Roster panel ticking down — fire 3/5 active, EMT 4/4 active, paramedic 1/3.

**Say**: *"Cortex doesn't just score severity — it tells us what's needed. For Sarah, it returned `required_resources: {paramedic: 1, fire: 1}`."*

**Do**: Open Sarah's incident sheet. Point at `required_resources` chips. Show `Assigned: Paramedic Unit 3, ETA 9 min`.

**Say**: *"A Snowflake stored procedure runs every 30 seconds. It finds the highest-severity unassigned incident, matches the closest available unit with the right skills, and creates the assignment. Greedy dispatch, but it's optimal under load and demos transparently."*

**Do**: Toggle "Paramedic Unit 3" in left filter.

**Show**: Bottom drawer slides up with their ordered route — 5 stops, ETAs, polyline on map.

---

### Beat 5 — The Curveball (3:00–3:45, 45s)

**Say**: *"Now I'm going to throw something at the system. Building collapse, downtown Houston, 20 victims trapped."*

**Do**: Click admin **Inject Critical Incident** button.

**Show**: New severity-98 pin appears mid-screen. Routes visibly recompute. Paramedic Unit 3's old polyline fades, new one draws to the new incident first.

**Say**: *"Severity 98 trips the recompute trigger. Cortex re-evaluates the unit's queue, the proc reassigns, the Mapbox Optimization API computes the new path. The responder's tablet would update right now."*

---

### Beat 6 — The Snowflake Receipt (3:45–4:00, 15s)

**Do**: Flip to Snowflake worksheet tab. Run a pre-typed query.

```sql
SHOW DYNAMIC TABLES;
SELECT name, target_lag, last_refresh_status, scheduling_state FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

**Say**: *"Every piece of intelligence you just saw — severity, summary, dedup, clustering, dispatch — runs natively in Snowflake. Cortex AI, Cortex Search, Streams + Tasks, Dynamic Tables, geospatial functions, Snowpark Python. Six features, one platform, the warehouse is the brain. Thank you."*

---

## Backup Plan (if something breaks live)

| Failure                             | Fallback                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------ |
| Scenario doesn't fire               | Pre-recorded screen recording in the same browser tab; switch and narrate. |
| Cortex API timeout                  | Show pre-populated `INCIDENTS_ENRICHED` rows; "here's what it looks like after triage."  |
| Map doesn't load (Mapbox token bad) | Fall back to Leaflet adapter; less flashy, still works.                  |
| Whole laptop dies                   | Slide deck with screenshots + the GitHub repo URL.                       |
| Voice question from judge           | Refer to "Voice is wired via ElevenLabs in our nice-to-haves; the same incident shape works whether the input is voice or text."  |

---

## Slide Deck (5 slides, backup only)

1. **Title** — "Real-time disaster triage powered by Snowflake AI"
2. **Problem** — 40k calls/2hr, dropped lifelines, macro chaos. (1 image: news photo of flooded house.)
3. **System diagram** — the architecture flow from `CONTEXT.md`. (Copy verbatim.)
4. **Snowflake angle** — bullet list of all 6 features used.
5. **Roadmap** — voice (ElevenLabs), multi-agency, prepositioned cache, native app.

---

## After Demo: Q&A Prep

**Q**: "Could this scale to a real city?"
A: "The architecture scales — Snowflake handles millions of rows easily. Cortex Throughput is the throttle. For Houston, you'd need a dedicated COMPUTE_WH at LARGE size and probably partition by `event_id` if multiple disasters overlap. Cost on a real event: maybe $500-2000 in compute for a 4-hour disaster, dwarfed by the value of saving lives."

**Q**: "Why not just use Twilio + a database?"
A: "You'd be writing the AI yourself. Snowflake Cortex gave us severity, summarization, embeddings, and the orchestration pipeline in SQL. We saved maybe 30 hours of glue."

**Q**: "What about false positives — over-prioritization?"
A: "Severity has a confidence field. The dashboard lets responders override. And the prompt is auditable — the three reasons are shown to the dispatcher every time."

**Q**: "Privacy?"
A: "Pre-registration is opt-in. Anonymous device IDs for everyone else. PII stays in PROFILES, which is encrypted at rest and access-controlled via Snowflake roles. We'd add column-level masking before any production deploy."

**Q**: "What about no signal?"
A: "PWA queues incident POSTs in IndexedDB and flushes when the network returns. We assume *some* signal exists; full radio dead-zones need mesh and that's a separate hardware project."

**Q**: "What's next?"
A: "Voice via ElevenLabs ConvAI is the obvious next step — drop-in via webhook. Then multi-agency coordination (handoffs between police, fire, EMS systems), then prepositioned cache logistics (which is what 'doomsday kit' becomes when you scale it)."
