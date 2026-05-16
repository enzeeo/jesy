# SNOWFLAKE PLAN — Conversational Command Center

**Status:** Companion plan to `docs/PLAN.md`
**Last updated:** 2026-05-16

---

## Thesis

The Snowflake prize angle is not just a warehouse-backed dashboard. It is a responder command center where operators ask operational questions across live disaster data, and Snowflake grounds every answer in governed incident, cluster, roster, dispatch, and feedback tables.

V1 centers on one **Responder Supervisor Cortex Agent**. Predictive ML is deferred until the system has feedback labels from approvals, overrides, corrected severities, corrected resource needs, and responder ratings.

## V1 Command Surface

| Surface | Context injected | Example operator questions |
| --- | --- | --- |
| Global chat | active event, filters, role, time window | "What are the highest-risk clusters right now?" "Where are we short on EMTs?" |
| Incident dot chat | `incident_id` | "Why is this dot severe?" "What is missing before dispatch?" |
| Cluster chat | `cluster_id` | "Summarize this cluster." "Which incidents need boats or medical review?" |
| Dispatch approval | `dispatch_recommendation_id` | "Approve", "reject with reason", or "assign a different unit" |

The agent answers should be concise and evidence-first:

1. Decision or recommendation.
2. Confidence.
3. Cited incident or cluster evidence.
4. Uncertainty or missing information.
5. One clarifying follow-up question.

## Snowflake Runtime Boundary

Runtime intelligence stays inside Snowflake:

- **Cortex Agents** orchestrate the responder command UI.
- **Cortex Search** retrieves enriched incident-report evidence.
- **Cortex Analyst Semantic Views** answer structured questions over incidents, clusters, responders, assignments, heatmaps, and feedback.
- **AISQL functions** extract, classify, summarize, and score decision-support signals.
- **Streams and Tasks** move reports through enrichment, clustering, dispatch recommendation, and serving refresh.
- **Dynamic Tables** power current map, cluster, heatmap, roster, and recommendation views.
- **Geospatial and H3 logic** compute hotspots, cluster membership, route coverage, and resource gaps.
- **Stored procedures and UDFs** own deterministic dispatch, location confidence, and review workflows.

**Cortex Code is developer tooling only.** Use it to accelerate SQL, semantic views, search service definitions, and agent config authoring. Do not present Cortex Code as the runtime agent layer.

## Canonical Object

The canonical searchable object is an **Incident Report**, not a raw call.

An Incident Report is a normalized, redacted, enriched record created from text-first victim submissions. It may later include audio transcription metadata, but v1 should be transcript/text-first. Audio ingestion is stretch.

Each searchable incident document should include:

- `incident_id`
- redacted transcript or submission text
- summary
- extracted needs
- severity decision-support factors
- clinical risk flags
- location confidence and geography metadata
- cluster ids and duplicate/evidence links
- dispatch recommendation state
- timestamps and source metadata

## Data Design

| Schema | Owns |
| --- | --- |
| `RAW` | raw incident submissions, transcript text, optional staged audio metadata, source device/session metadata |
| `CLEAN` | normalized incident reports, redacted text, profile joins, extracted needs, location confidence, clinical risk flags |
| `GEO` | geocoded points, H3 cells, flood zones, route/coverage inputs, cluster snapshots, cluster membership history |
| `FEATURES` | severity factors, embedding vectors, resource-demand features, feedback labels for future ML |
| `SERVING` | current incident map view, current cluster view, severity heatmap, responder roster, dispatch recommendations, assignments |
| `AGENT` | Cortex Search service config, Semantic Views, agent request logs, feedback ratings, prompt versions, evaluation records |

## AI Behavior

### Search

Create one filtered Cortex Search service over enriched incident-report text and metadata. It should search summary, redacted text, evidence, reasons, cluster ids, resource needs, severity, time, and geography filters.

### Structured Analysis

Use Cortex Analyst with Semantic Views for structured questions:

- active incident counts by severity, category, time, and geography
- cluster summaries and resource needs
- responder availability and gaps
- dispatch recommendations and assignments
- severity heatmaps and hotspot cells
- feedback, overrides, and evaluation records

Use legacy YAML semantic models only as fallback if Semantic Views are unavailable in the target account.

### Severity

V1 severity is decision support, not a trained predictive claim. Combine Cortex extraction/classification with deterministic factors, confidence, and cited evidence. Avoid implying the system predicts outcomes.

### Clinical Safety

Clinical output is responder-only:

- risk flags
- missing-information prompts
- escalation cues

Do not provide diagnosis, treatment plans, or victim-facing medical advice. Unsafe medical questions should be redirected to escalation and evidence gathering.

## Agent Architecture

### V1

Use one **Responder Supervisor Cortex Agent** with these tools:

- incident Cortex Search
- Semantic Views for command-center metrics
- dispatch recommendation lookup and approval procedures
- feedback logging procedure
- optional prompt-version and evaluation lookup

### Later

Specialist agents are optional after v1 is stable:

- Severity review
- Location confidence review
- Clustering and duplicate review
- Dispatch review
- Clinical risk review

Do not split v1 into many agents unless the single supervisor becomes too hard to control or evaluate.

## Dispatch Flow

Snowflake produces a **Dispatch Recommendation**. A responder command user approves it before it becomes an `Assignment`.

Recommended flow:

1. Incident Report enters `CLEAN`.
2. Enrichment computes needs, severity factors, location confidence, and risk flags.
3. Cluster and H3 refresh update hotspot state.
4. Stored procedure creates or updates a Dispatch Recommendation.
5. Global, dot, or cluster chat explains the recommendation with evidence.
6. Responder approves, rejects, or overrides.
7. Approval writes an `Assignment`.
8. Feedback labels capture the decision for future ML.

## Snowflake-Native Differentiators

- **Live governed pipeline:** Streams and Tasks move raw reports through enrichment, clustering, dispatch recommendation, and serving views.
- **Dynamic serving layer:** Dynamic Tables power current map, cluster, heatmap, and roster outputs.
- **Geospatial story:** H3 cells, cluster membership, flood-zone context, route coverage, and resource gaps make the demo visibly Snowflake-native.
- **Governance story:** Synthetic data, role-scoped views, redaction path, audit logs, request logs, and evaluation tables.
- **Feedback loop:** approvals, overrides, corrected severity labels, corrected resource labels, thumbs ratings, and text ratings become future Snowpark ML training data.

## Demo Script

1. Start the Texas flood scenario.
2. Open the responder dashboard with global chat visible.
3. Ask: "What are the top three operational risks right now?"
4. Click a severe incident dot and ask: "Why is this severe and what should we dispatch?"
5. Click a cluster and ask: "What does this cluster need most?"
6. Show a Dispatch Recommendation, approve it, and confirm an Assignment appears.
7. Ask an unsafe medical question and show the agent refuses diagnosis/treatment while giving responder-safe escalation cues.
8. Open Snowflake objects live: Search service, Semantic View, Dynamic Table, Stream/Task, and feedback table.

## Test Plan

- Verify schema creation for layered Snowflake schemas and serving views.
- Insert sample Incident Reports and confirm enrichment, search indexing, clustering, and dispatch recommendations refresh.
- Test global, dot, and cluster chat with grounded answers.
- Test unsafe medical advice rejection.
- Test human approval converts a Dispatch Recommendation into an Assignment.
- Confirm role-scoped access prevents broad agent/search access to raw sensitive text.
- Confirm agent request logs, prompt versions, feedback ratings, and evaluation records are written.

## Roadmap

| Phase | Scope |
| --- | --- |
| V1 | single Responder Supervisor Cortex Agent, text-first Incident Reports, search + Semantic Views, human-approved Dispatch Recommendations |
| V1.5 | better evaluation records, prompt variants, richer feedback labels, improved cluster and duplicate review |
| V2 | specialist agents where useful, audio transcription, Snowpark ML models trained from feedback labels |

## Glossary Additions

Add these later to `docs/CONTEXT.md` when implementation begins:

**Incident Report**:
Normalized, redacted, enriched disaster report used as the canonical searchable object for responder decisions.
_Avoid_: raw call, victim call

**Dispatch Recommendation**:
Snowflake-generated proposed responder assignment requiring human approval before it becomes an Assignment.
_Avoid_: automatic dispatch, final assignment

**Clinical Risk Flag**:
Responder-only safety signal that identifies possible medical escalation needs or missing information. It is not a diagnosis or treatment recommendation.
_Avoid_: diagnosis, medical advice

## Sources

- Snowflake Cortex Agents: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents
- Snowflake Cortex Search: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview
- Snowflake Cortex Analyst: https://docs.snowflake.com/en/en/user-guide/snowflake-cortex/cortex-analyst
- Snowflake Cortex AISQL: https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql
- Snowflake Cortex Code: https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code
