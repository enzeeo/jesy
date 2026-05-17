"""
AAR orchestrator. Assembles the full AARResponse for a sim_run_id.

  GET /api/analysis/{sim_run_id}
       │
       ▼
   get_or_compute_aar (this module)
       │
       ├── single-flight cache key on (sim_run_id, max_ts_epoch, n_incidents)
       ├── active-run gate: if sim_run_id == AppState.active_sim_run_id → skip counterfactual
       │                                                                   set is_live=true + badge
       ▼
   _compute_aar
       │
       ├── load incidents from Snowflake or IncidentStore
       ├── load dispatches from Snowflake (or synthesize via greedy if no Snowflake)
       ├── scorecard (assignment %, ETA percentiles, fleet distance, vuln gap)
       ├── vulnerability breakdown (Python-side from victims)
       ├── timeline (cumulative incidents over time)
       └── counterfactual (3-policy replay, ONLY if not is_live)
       ▼
   AARResponse
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import UUID

from disaster.analysis.counterfactual import pick_winner, run_all_policies
from disaster.analysis.models import (
    AARResponse,
    AARScorecard,
    CounterfactualPanel,
    IncidentGeoPoint,
    PolicyResult,
    TimelineSlice,
)
from disaster.analysis.policies import has_vulnerable_victim
from disaster.analysis.vulnerability import compute_breakdown
from disaster.models import IncidentReport
from disaster.routing import greedy_assign

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)


class AARNotFound(Exception):
    """No incidents with this sim_run_id exist in any source."""


# Single-flight cache. Key: (sim_run_id, max_ts_epoch, n_incidents).
# Value: cached AARResponse (immutable past) or the in-flight Future computing it.
# Live runs are NOT cached (their key would shift on every refresh).
_aar_cache: dict[tuple[str, float, int], AARResponse] = {}
_aar_inflight: dict[tuple[str, float, int], asyncio.Future[AARResponse]] = {}


async def get_or_compute_aar(sim_run_id: str, state: AppState) -> AARResponse:
    """
    Public entry point. Handles caching + active-run gating + delegates to
    _compute_aar for the heavy lifting.
    """
    is_live = state.active_sim_run_id == sim_run_id

    # Live runs: never cache, never run counterfactual (the incident stream is
    # still growing — replay results would shift on every refresh).
    if is_live:
        return await _compute_aar(sim_run_id, state, is_live=True)

    # Past runs: load incidents once to build the cache key, then single-flight.
    incidents = await _load_incidents(sim_run_id, state)
    if not incidents:
        raise AARNotFound(f"no incidents found for sim_run_id={sim_run_id}")

    max_ts = max(i.timestamp.timestamp() for i in incidents)
    key = (sim_run_id, max_ts, len(incidents))

    cached = _aar_cache.get(key)
    if cached is not None:
        return cached

    inflight = _aar_inflight.get(key)
    if inflight is not None:
        return await inflight

    fut: asyncio.Future[AARResponse] = asyncio.get_running_loop().create_future()
    _aar_inflight[key] = fut
    try:
        result = await _compute_aar(sim_run_id, state, is_live=False, preloaded_incidents=incidents)
        _aar_cache[key] = result
        fut.set_result(result)
        return result
    except Exception as e:
        fut.set_exception(e)
        raise
    finally:
        _aar_inflight.pop(key, None)


async def _compute_aar(
    sim_run_id: str,
    state: AppState,
    *,
    is_live: bool,
    preloaded_incidents: list[IncidentReport] | None = None,
) -> AARResponse:
    """Build the AARResponse from scratch. Called by get_or_compute_aar."""
    incidents = preloaded_incidents or await _load_incidents(sim_run_id, state)
    if not incidents:
        raise AARNotFound(f"no incidents found for sim_run_id={sim_run_id}")

    responders = await state.responders.list()
    dispatches_eta, data_source = await _load_dispatch_etas(sim_run_id, state, incidents, responders)

    scorecard = _build_scorecard(incidents, dispatches_eta)
    vulnerability = compute_breakdown(incidents, dispatches_eta)
    timeline = _build_timeline(incidents, dispatches_eta)
    incidents_geo = _build_geo(incidents, dispatches_eta)

    counterfactual: CounterfactualPanel | None = None
    if not is_live:
        actual = _build_actual_policy_result(incidents, dispatches_eta)
        policy_results = run_all_policies(incidents, responders)
        counterfactual = CounterfactualPanel(
            actual=actual,
            policies=policy_results,
            winner_by_assignment=pick_winner(
                policy_results, lambda r: -r.assigned_count,  # negate: largest wins
            ),
            winner_by_vulnerable_eta=pick_winner(
                policy_results, lambda r: r.vulnerable_eta_p50_seconds,
            ),
        )

    started_at = min(i.timestamp for i in incidents)
    ended_at = max(i.timestamp for i in incidents)

    return AARResponse(
        sim_run_id=sim_run_id,
        started_at=started_at,
        ended_at=ended_at,
        is_live=is_live,
        badge="Run in progress — numbers may shift" if is_live else None,
        scorecard=scorecard,
        counterfactual=counterfactual,
        vulnerability=vulnerability,
        timeline=timeline,
        incidents_geo=incidents_geo,
        data_source=data_source,
    )


# ── Loaders ──────────────────────────────────────────────────────────────────

async def _load_incidents(sim_run_id: str, state: AppState) -> list[IncidentReport]:
    """
    Try Snowflake first, fall back to IncidentStore. The in-memory store always
    has the freshest data anyway; Snowflake might lag by up to 5s due to the
    writer's batching window.

    For the hackathon demo, in-memory IS the source of truth. Snowflake is for
    when a teammate wants to query historical runs after the demo ends. So we
    actually invert the priority: in-memory first.
    """
    all_incidents = await state.incidents.list()
    matching = [i for i in all_incidents if i.sim_run_id == sim_run_id]
    return matching


async def _load_dispatch_etas(
    sim_run_id: str,
    state: AppState,
    incidents: list[IncidentReport],
    responders: list,
) -> tuple[dict[UUID, float], str]:
    """
    Returns (incident_id → eta_seconds, data_source).

    With Snowflake configured: query responder_dispatches WHERE sim_run_id=?,
    take the EARLIEST dispatch per incident (multiple writes possible if a
    rerouting happened). Returns "snowflake".

    Without Snowflake (or if the query fails or returns empty): synthesize via
    one greedy_assign() pass over the recorded incidents + current responder
    positions. This is a degraded mode — the dispatch ETAs reflect what greedy
    WOULD do now, not what happened during the run. Returns "in_memory".
    """
    runner = getattr(state, "_sf_query_runner", None)
    if runner is not None:
        try:
            rows = await runner(
                "SELECT incident_id, eta_seconds FROM responder_dispatches "
                "WHERE sim_run_id = %s ORDER BY dispatched_at",
                (sim_run_id,),
            )
            etas: dict[UUID, float] = {}
            for row in rows:
                inc_id = UUID(str(row.get("INCIDENT_ID") or row.get("incident_id")))
                eta = float(row.get("ETA_SECONDS") or row.get("eta_seconds"))
                if inc_id not in etas:  # earliest dispatch wins
                    etas[inc_id] = eta
            if etas:
                return etas, "snowflake"
        except Exception as e:  # noqa: BLE001 — diverse connector errors
            log.warning("aar: snowflake dispatches query failed (%s) — using in-memory fallback", e)

    # In-memory degraded mode: run a single greedy pass for the "actual" baseline.
    if not responders:
        return {}, "in_memory"
    assignment = greedy_assign(incidents, responders, vehicle_capacity=5)
    etas = {leg.incident_id: leg.eta_seconds for legs in assignment.routes.values() for leg in legs}
    return etas, "in_memory"


# ── Scorecard + timeline builders ────────────────────────────────────────────

def _build_scorecard(
    incidents: list[IncidentReport],
    dispatches_eta: dict[UUID, float],
) -> AARScorecard:
    assigned_etas = [dispatches_eta[i.id] for i in incidents if i.id in dispatches_eta]
    vuln_incidents = [i for i in incidents if has_vulnerable_victim(i)]
    vuln_assigned_etas = [dispatches_eta[i.id] for i in vuln_incidents if i.id in dispatches_eta]
    voice_confidences = [i.confidence for i in incidents if i.source.value == "voice"]

    # Fleet distance can't be reconstructed from dispatches_eta alone (no km field
    # in the dict). We could query it separately but for v1 we expose what we have.
    fleet_km = 0.0

    return AARScorecard(
        incident_count=len(incidents),
        assigned_count=len(assigned_etas),
        assigned_pct=len(assigned_etas) / len(incidents) if incidents else 0.0,
        p50_eta_seconds=statistics.median(assigned_etas) if assigned_etas else None,
        p90_eta_seconds=_percentile(assigned_etas, 0.9) if assigned_etas else None,
        total_fleet_distance_km=fleet_km,
        vulnerable_incident_count=len(vuln_incidents),
        vulnerable_assigned_count=len(vuln_assigned_etas),
        vulnerable_eta_p50_seconds=statistics.median(vuln_assigned_etas) if vuln_assigned_etas else None,
        extraction_confidence_p50=statistics.median(voice_confidences) if voice_confidences else None,
    )


def _build_actual_policy_result(
    incidents: list[IncidentReport],
    dispatches_eta: dict[UUID, float],
) -> PolicyResult:
    """The 'actual' column of the counterfactual panel — what really happened."""
    assigned_etas = [dispatches_eta[i.id] for i in incidents if i.id in dispatches_eta]
    vuln_etas = [
        dispatches_eta[i.id]
        for i in incidents
        if i.id in dispatches_eta and has_vulnerable_victim(i)
    ]
    return PolicyResult(
        key="actual",
        label="Actual dispatch",
        is_actual=True,
        assigned_count=len(assigned_etas),
        total_fleet_distance_km=0.0,
        p50_eta_seconds=statistics.median(assigned_etas) if assigned_etas else None,
        p90_eta_seconds=_percentile(assigned_etas, 0.9) if assigned_etas else None,
        vulnerable_assigned_count=len(vuln_etas),
        vulnerable_eta_p50_seconds=statistics.median(vuln_etas) if vuln_etas else None,
    )


def _build_timeline(
    incidents: list[IncidentReport],
    dispatches_eta: dict[UUID, float],
) -> list[TimelineSlice]:
    """
    One bucket per ~1 second from first incident to last. Cumulative counts so
    the scrubber animates a monotonically-growing curve.

    For runs with very few incidents (<10), uses 1s buckets; for larger runs
    (≥10) widens to (run_duration / 60) buckets to keep the chart digestible.
    """
    if not incidents:
        return []
    sorted_inc = sorted(incidents, key=lambda i: i.timestamp)
    t0 = sorted_inc[0].timestamp
    t_end = sorted_inc[-1].timestamp
    duration_s = max(1.0, (t_end - t0).total_seconds())

    n_buckets = max(10, min(60, int(duration_s)))
    bucket_size = max(1.0, duration_s / n_buckets)

    counts_by_bucket: dict[int, dict[str, int]] = defaultdict(lambda: {"total": 0, "assigned": 0})
    for inc in sorted_inc:
        offset = (inc.timestamp - t0).total_seconds()
        b = int(offset // bucket_size)
        counts_by_bucket[b]["total"] += 1
        if inc.id in dispatches_eta:
            counts_by_bucket[b]["assigned"] += 1

    # Build cumulative timeline
    timeline: list[TimelineSlice] = []
    cum_total = 0
    cum_assigned = 0
    for b in range(n_buckets + 1):
        bucket = counts_by_bucket.get(b, {"total": 0, "assigned": 0})
        cum_total += bucket["total"]
        cum_assigned += bucket["assigned"]
        timeline.append(TimelineSlice(
            t_seconds=int(b * bucket_size),
            incidents_total=cum_total,
            incidents_assigned=cum_assigned,
        ))
    return timeline


def _build_geo(
    incidents: list[IncidentReport],
    dispatches_eta: dict[UUID, float],
) -> list[IncidentGeoPoint]:
    """Slim per-incident projection for the AAR map + scrubber. Sorted by timestamp."""
    sorted_inc = sorted(incidents, key=lambda i: i.timestamp)
    return [
        IncidentGeoPoint(
            id=str(i.id),
            lat=i.location.lat,
            lng=i.location.lng,
            timestamp=i.timestamp,
            severity=i.severity.value,
            eta_seconds=dispatches_eta.get(i.id),
            has_vulnerable=has_vulnerable_victim(i),
        )
        for i in sorted_inc
    ]


def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile. Empty input MUST NOT reach here."""
    if not values:
        raise ValueError("percentile: empty input")
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def clear_cache() -> None:
    """Test helper. Wipes the single-flight cache so tests don't see stale results."""
    _aar_cache.clear()
    _aar_inflight.clear()
