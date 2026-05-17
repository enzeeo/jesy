# TODOs

## Main-Branch TODOs

- Keep backend and frontend start commands verified.
- Keep Snowflake fallback behavior documented.
- Keep OpenAI optional behavior documented.
- Add docs when routes or demo buttons change.
- Keep `DESIGN.md` aligned with actual dashboard components.
- Run `make check` before larger backend changes.

## Future Features

These belong in future work until implemented on `main`:

- Victim PWA with low-signal intake
- Responder dashboard split into a Vite app
- Hono API service
- pnpm workspace
- Shared TypeScript packages
- Scenario JSON package
- Snowflake SQL deployment directory
- Cortex Agent chat surfaces
- Cortex Search over incident evidence
- Cortex Analyst Semantic Views
- Streams and Tasks enrichment
- Dynamic Tables serving views
- H3 clustering and route coverage
- Snowpark Python UDFs
- Human-approved dispatch recommendations

## AAR follow-ups (post-2026-05-17 CEO plan)

Deferred from the AAR plan — these did not make the hackathon push but have full context in `~/.gstack/projects/enzeeo-jezy/ceo-plans/2026-05-17-post-disaster-aar.md`.

- **Cortex Search "moments" panel in AAR narrative.** Surface 3-5 voice-call snippets semantically matched to the narrative ("3 callers said 'water rising'"). Requires `transcript_full` column on `voice_calls` (Gap #2 from prior CEO plan) + Cortex Search Service registration + verified Cortex access on the Snowflake account. Effort: human ~1 day / CC ~45min (after prereqs). Priority: P1 post-demo.
- **PDF export of AAR (judge-ready styling).** `POST /api/analysis/{sim_run_id}/export.pdf` renders the AAR through a Playwright print-styled template. Cover page, scorecard, counterfactual table, narrative, map snapshot. Effort: human ~3hrs / CC ~25min. Priority: P2.
- **Pre-positioning policy in counterfactual.** "VRP + pre-staging" as a 4th policy in the AAR's counterfactual panel. Blocked on: a defensible signal for *where* to pre-stage (post-multi-run, mine historical incident hotspots from `incidents` table). Priority: P2.
- **Multi-run trend dashboard.** Cross sim_run_id comparison — pick 5 runs, see how policies evolved, response times improved, vulnerable victim outcomes trended. Effort: human ~1 day / CC ~1hr. Priority: P2.
- **Persisted AAR artifacts in Snowflake.** New table `OPERATIONAL.aar_reports` storing generated narrative + scorecard + lessons keyed by sim_run_id, so the multi-run trend dashboard has memory. Effort: human ~4hrs / CC ~20min. Priority: P3.
- **AAR auto-trigger on /demo/run/end.** Right now AAR is generated on-page-load. When `/demo/run/end` is added (prior CEO plan Hour 4), have it trigger AAR generation + an SSE notification to the dispatcher. Effort: human ~2hrs / CC ~15min. Priority: P3.
- **Discrete-event simulation in counterfactual (responder service times).** Replace the single-trip assignment model with a proper DES — responders complete assignments over a service window, become available again. Enables honest cross-policy ETA percentile comparison. Effort: human ~2 days / CC ~2hr. Priority: P2.
- **Sensitivity slider (+1 responder).** "If you had 5 units instead of 4, p90 ETA would have improved by X." UI slider, runs counterfactual with adjusted responder count. Effort: human ~4hrs / CC ~30min. Priority: P3.
- **Per-call dispatch trace (click an incident → modal).** Show the full lifecycle: call received → triage → dispatched → ETA → on-scene → resolved. Effort: human ~3hrs / CC ~20min. Priority: P3.
- **Responder route animation in TimelineScrubber.** v1 ships incidents-only animation. v2 interpolates responder positions along route legs as the cursor moves. Requires per-leg progress field, requestAnimationFrame plumbing, SSE pause during scrub. Effort: human ~1 day / CC ~45min. Priority: P3.
- **`incident_vulnerabilities` long-table schema migration.** Replace comma-joined `incidents.vulnerabilities VARCHAR(500)` with a proper join table so vulnerability breakdowns can be queried in Snowflake instead of computed Python-side. Add boolean denorm columns (`has_elderly`, `has_child`, ...) as covering index. Effort: human ~3hrs / CC ~30min. Priority: P2.
