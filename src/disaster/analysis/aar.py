"""
AAR orchestrator. Assembles the full AARResponse for a sim_run_id.

  GET /api/analysis/{sim_run_id}
       │
       ▼
   get_or_compute_aar (this module)
       │
       ├── single-flight cache key on (sim_run_id, max_event_ts_epoch, n_incidents)
       │   where max_event_ts is max(last incident ts, last responder arrival ts)
       ├── active-run gate: if sim_run_id == AppState.active_sim_run_id → skip
       │   counterfactual / arrivals / route-runs, set is_live=true + badge
       ▼
   _compute_aar
       │
       ├── load incidents from IncidentStore (Snowflake fallback TBD)
       ├── load estimated ETAs from SERVING.RESPONDER_DISPATCHES
       ├── load real arrivals from SERVING.RESPONDER_ARRIVALS (3-way merge)
       ├── load aggregate route-run stats from SERVING.ROUTE_RECOMMENDATIONS +
       │   ROUTE_LEGS (solver mix, real fleet km, degraded %, provider, elapsed)
       ├── load road-access snapshot in effect during the run
       ├── load cortex alerts that fired during the run window
       ├── scorecard (assignment %, est ETA percentiles, actual ETA percentiles,
       │   actuals coverage, vuln gap, fleet km from real routes)
       ├── vulnerability breakdown (Python-side from victims)
       ├── timeline (cumulative incidents over time)
       └── counterfactual (3-policy replay + enriched actual row, ONLY if not is_live)
       ▼
   AARResponse
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from disaster.analysis.counterfactual import pick_winner, run_all_policies
from disaster.analysis.models import (
    AARResponse,
    AARScorecard,
    CortexAlertEvent,
    CounterfactualPanel,
    IncidentGeoPoint,
    PolicyResult,
    RoadAccessContext,
    TimelineSlice,
)
from disaster.analysis.policies import has_vulnerable_victim
from disaster.analysis.vulnerability import compute_breakdown
from disaster.models import IncidentReport
from disaster.routing import greedy_assign

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)

# Hide the actual-vs-estimated delta tile below this coverage — median across a
# tiny sample is misleading. UI still shows the coverage badge for context.
_MIN_DELTA_COVERAGE = 0.30

# Per-query budget for every Snowflake call out of AAR. The query runner shares
# one connection across the whole app; if Snowflake half-closes a session
# (CLOSE_WAIT), unprotected calls block forever and starve the executor pool,
# wedging /healthz and every other endpoint. With a timeout we drop the bad
# query, log a warning, and fall through to the in-memory / synthesized path.
_SF_QUERY_TIMEOUT_S = 4.0


async def _run_with_timeout(runner, sql: str, params: tuple, *, label: str):
    """Wrap a runner call so a hung Snowflake query can't wedge the event loop."""
    return await asyncio.wait_for(runner(sql, params), timeout=_SF_QUERY_TIMEOUT_S)


class AARNotFound(Exception):
    """No incidents with this sim_run_id exist in any source."""


@dataclass(frozen=True)
class ResolvedETA:
    """One incident's response time + provenance for the 3-way merge."""
    seconds: float
    source: str            # "actual" | "estimated" | "synthesized_greedy"


@dataclass(frozen=True)
class RouteRunsSummary:
    """Aggregate over every ROUTE_RECOMMENDATIONS row stamped with this sim."""
    optimization_count: int
    total_fleet_distance_km: float
    solver_mix: dict[str, int]
    elapsed_ms_p50: float | None
    elapsed_ms_p90: float | None
    degraded_leg_pct: float | None
    provider_status: str | None


_EMPTY_ROUTE_RUNS = RouteRunsSummary(
    optimization_count=0,
    total_fleet_distance_km=0.0,
    solver_mix={},
    elapsed_ms_p50=None,
    elapsed_ms_p90=None,
    degraded_leg_pct=None,
    provider_status=None,
)


# Single-flight cache. Key: (sim_run_id, max_event_ts_epoch, n_incidents).
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

    max_incident_ts = max(i.timestamp.timestamp() for i in incidents)
    # Arrivals can land after the last incident timestamp; include them in the
    # cache key so a late arrival invalidates a stale AAR.
    max_arrival_ts = await _max_arrival_ts(sim_run_id, state)
    max_event_ts = max(max_incident_ts, max_arrival_ts)
    key = (sim_run_id, max_event_ts, len(incidents))

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

    # 3-way merge: real arrivals → estimated dispatches → synthesized greedy.
    # Live runs skip arrivals (churny + queries are extra latency on the polling path).
    resolved_etas, data_source = await _resolve_etas(
        sim_run_id, state, incidents, responders, is_live=is_live,
    )

    # Aggregate route-optimization metadata for the run.
    route_runs = await _load_route_runs_summary(sim_run_id, state, is_live=is_live)

    road_access = await _load_road_access_context(sim_run_id, state)

    started_at = min(i.timestamp for i in incidents)
    ended_at = max(i.timestamp for i in incidents)
    cortex_alerts = await _load_cortex_alerts(state, started_at, ended_at, is_live=is_live)

    # Existing builders take a flat dict[UUID, float] of seconds. Project the
    # resolved map down so we don't need to touch their signatures.
    estimated_etas = {iid: r.seconds for iid, r in resolved_etas.items()}

    scorecard = _build_scorecard(incidents, resolved_etas, route_runs)
    vulnerability = compute_breakdown(incidents, estimated_etas)
    timeline = _build_timeline(incidents, estimated_etas)
    incidents_geo = _build_geo(incidents, estimated_etas)

    counterfactual: CounterfactualPanel | None = None
    if not is_live:
        actual = _build_actual_policy_result(incidents, resolved_etas, route_runs)
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
        road_access_context=road_access,
        cortex_alerts=cortex_alerts,
    )


# ── Loaders ──────────────────────────────────────────────────────────────────

async def _load_incidents(sim_run_id: str, state: AppState) -> list[IncidentReport]:
    """
    For the hackathon demo, in-memory IS the source of truth. Snowflake is for
    when a teammate wants to query historical runs after the demo ends.

    NOTE: cold-start after a server restart will return no incidents from the
    in-memory store — Snowflake read path is a deferred TODO.
    """
    all_incidents = await state.incidents.list()
    return [i for i in all_incidents if i.sim_run_id == sim_run_id]


async def _resolve_etas(
    sim_run_id: str,
    state: AppState,
    incidents: list[IncidentReport],
    responders: list,
    *,
    is_live: bool,
) -> tuple[dict[UUID, ResolvedETA], str]:
    """
    Merge sources in priority order:
      1. SERVING.RESPONDER_ARRIVALS — wheels-on-scene actual seconds
      2. SERVING.RESPONDER_DISPATCHES — estimated ETA stamped at dispatch time
      3. greedy_assign() over the recorded incidents — last-resort synthesizer

    Returns (incident_id → ResolvedETA, data_source). data_source is "snowflake"
    iff any rows came from sources 1 or 2; otherwise "in_memory".
    """
    runner = getattr(state, "_sf_query_runner", None)
    resolved: dict[UUID, ResolvedETA] = {}
    snowflake_hit = False

    if runner is not None:
        # Real arrivals first (skip on live runs — extra latency on polling path
        # for data that's mostly partial mid-run).
        if not is_live:
            try:
                arrival_rows = await _run_with_timeout(
                    runner,
                    """
                    SELECT d.INCIDENT_ID, a.ARRIVAL_TIMESTAMP, d.STARTED_AT
                    FROM SERVING.RESPONDER_ARRIVALS a
                    JOIN SERVING.RESPONDER_DISPATCHES d
                      ON d.RESPONDER_ID = a.RESPONDER_ID
                     AND d.INCIDENT_ID = a.INCIDENT_ID
                    JOIN CLEAN.INCIDENTS i ON i.INCIDENT_ID = d.INCIDENT_ID
                    WHERE i.SIM_RUN_ID = %s
                    """,
                    (sim_run_id,),
                    label="arrivals",
                )
                for row in arrival_rows:
                    iid = _row_uuid(row, "INCIDENT_ID")
                    seconds = _seconds_between(
                        _row_dt(row, "STARTED_AT"),
                        _row_dt(row, "ARRIVAL_TIMESTAMP"),
                    )
                    if iid is None or seconds is None or seconds < 0:
                        continue
                    existing = resolved.get(iid)
                    # Earliest (smallest) arrival wins on dup.
                    if existing is None or seconds < existing.seconds:
                        resolved[iid] = ResolvedETA(seconds=seconds, source="actual")
                if arrival_rows:
                    snowflake_hit = True
            except TimeoutError as e:
                log.warning("aar: arrivals query timed out (%s) — falling through", e)
            except Exception as e:  # noqa: BLE001 — diverse connector errors
                log.warning("aar: arrivals query failed (%s) — falling through", e)

        # Estimated ETAs from dispatches — fills the gap for incidents that
        # were dispatched but haven't arrived yet (or where arrival rows are missing).
        try:
            dispatch_rows = await _run_with_timeout(
                runner,
                """
                SELECT d.INCIDENT_ID, d.ETA_SECONDS, d.STARTED_AT
                FROM SERVING.RESPONDER_DISPATCHES d
                JOIN CLEAN.INCIDENTS i ON i.INCIDENT_ID = d.INCIDENT_ID
                WHERE i.SIM_RUN_ID = %s
                ORDER BY d.STARTED_AT
                """,
                (sim_run_id,),
                label="dispatches",
            )
            for row in dispatch_rows:
                iid = _row_uuid(row, "INCIDENT_ID")
                eta = _row_float(row, "ETA_SECONDS")
                if iid is None or eta is None or iid in resolved:
                    continue
                resolved[iid] = ResolvedETA(seconds=eta, source="estimated")
            if dispatch_rows:
                snowflake_hit = True
        except TimeoutError as e:
            log.warning("aar: dispatches query timed out (%s) — falling through", e)
        except Exception as e:  # noqa: BLE001 — diverse connector errors
            log.warning("aar: dispatches query failed (%s) — falling through", e)

    # Synthesized fallback for anything still unresolved. Needed when:
    #   - Snowflake isn't configured at all (most demo runs)
    #   - Snowflake is configured but the dispatcher hadn't clicked anything
    if responders:
        missing = [i for i in incidents if i.id not in resolved]
        if missing:
            assignment = greedy_assign(missing, responders, vehicle_capacity=5)
            for legs in assignment.routes.values():
                for leg in legs:
                    if leg.incident_id not in resolved:
                        resolved[leg.incident_id] = ResolvedETA(
                            seconds=leg.eta_seconds, source="synthesized_greedy",
                        )

    data_source = "snowflake" if snowflake_hit else "in_memory"
    return resolved, data_source


async def _max_arrival_ts(sim_run_id: str, state: AppState) -> float:
    """
    Cheap one-row query for the cache key. Returns 0.0 when no Snowflake or
    no arrivals yet — preserves the old cache key behavior for those cases.
    """
    runner = getattr(state, "_sf_query_runner", None)
    if runner is None:
        return 0.0
    try:
        rows = await _run_with_timeout(
            runner,
            """
            SELECT MAX(a.ARRIVAL_TIMESTAMP) AS MAX_TS
            FROM SERVING.RESPONDER_ARRIVALS a
            JOIN SERVING.RESPONDER_DISPATCHES d
              ON d.RESPONDER_ID = a.RESPONDER_ID AND d.INCIDENT_ID = a.INCIDENT_ID
            JOIN CLEAN.INCIDENTS i ON i.INCIDENT_ID = d.INCIDENT_ID
            WHERE i.SIM_RUN_ID = %s
            """,
            (sim_run_id,),
            label="max_arrival_ts",
        )
        if not rows:
            return 0.0
        ts = _row_dt(rows[0], "MAX_TS")
        return ts.timestamp() if ts is not None else 0.0
    except TimeoutError as e:
        log.warning("aar: max_arrival_ts query timed out (%s)", e)
        return 0.0
    except Exception as e:  # noqa: BLE001
        log.warning("aar: max_arrival_ts query failed (%s)", e)
        return 0.0


async def _load_route_runs_summary(
    sim_run_id: str, state: AppState, *, is_live: bool,
) -> RouteRunsSummary:
    """
    Aggregate every ROUTE_RECOMMENDATIONS row stamped with this sim. Returns
    scalar metrics suitable for the actual-policy column footer + scorecard
    fleet distance. Empty summary when Snowflake unconfigured / no runs / live.
    """
    if is_live:
        return _EMPTY_ROUTE_RUNS
    runner = getattr(state, "_sf_query_runner", None)
    if runner is None:
        return _EMPTY_ROUTE_RUNS
    try:
        rows = await _run_with_timeout(
            runner,
            """
            SELECT
              r.SOLVER AS SOLVER,
              COUNT(DISTINCT r.ROUTE_ID) AS N_RUNS,
              MEDIAN(r.ELAPSED_MS) AS P50_MS,
              APPROX_PERCENTILE(r.ELAPSED_MS, 0.9) AS P90_MS,
              SUM(l.DISTANCE_KM) AS TOTAL_KM,
              SUM(CASE WHEN l.DEGRADED AND l.INCIDENT_ID IS NOT NULL
                       THEN 1 ELSE 0 END) AS DEGRADED_LEGS,
              SUM(CASE WHEN l.INCIDENT_ID IS NOT NULL THEN 1 ELSE 0 END)
                AS INCIDENT_LEGS,
              LISTAGG(DISTINCT l.PROVIDER_STATUS, ',') AS PROVIDERS
            FROM SERVING.ROUTE_RECOMMENDATIONS r
            LEFT JOIN SERVING.ROUTE_LEGS l USING(ROUTE_ID)
            WHERE r.SIM_RUN_ID = %s
            GROUP BY r.SOLVER
            """,
            (sim_run_id,),
            label="route_runs",
        )
    except TimeoutError as e:
        log.warning("aar: route_runs query timed out (%s)", e)
        return _EMPTY_ROUTE_RUNS
    except Exception as e:  # noqa: BLE001
        log.warning("aar: route_runs query failed (%s)", e)
        return _EMPTY_ROUTE_RUNS

    if not rows:
        return _EMPTY_ROUTE_RUNS

    solver_mix: dict[str, int] = {}
    total_km = 0.0
    degraded_legs = 0
    incident_legs = 0
    elapsed_p50_weighted: list[tuple[float, int]] = []
    elapsed_p90_weighted: list[tuple[float, int]] = []
    provider_counts: Counter[str] = Counter()
    optimization_count = 0
    for row in rows:
        solver = (row.get("SOLVER") or row.get("solver") or "unknown") or "unknown"
        n_runs = int(_row_float(row, "N_RUNS") or 0)
        solver_mix[solver] = n_runs
        optimization_count += n_runs
        total_km += float(_row_float(row, "TOTAL_KM") or 0.0)
        degraded_legs += int(_row_float(row, "DEGRADED_LEGS") or 0)
        incident_legs += int(_row_float(row, "INCIDENT_LEGS") or 0)
        p50 = _row_float(row, "P50_MS")
        p90 = _row_float(row, "P90_MS")
        if p50 is not None and n_runs > 0:
            elapsed_p50_weighted.append((p50, n_runs))
        if p90 is not None and n_runs > 0:
            elapsed_p90_weighted.append((p90, n_runs))
        for prov in _split_csv(row.get("PROVIDERS") or row.get("providers")):
            provider_counts[prov] += n_runs

    elapsed_p50 = _weighted_mean(elapsed_p50_weighted)
    elapsed_p90 = _weighted_mean(elapsed_p90_weighted)
    degraded_pct = (degraded_legs / incident_legs) if incident_legs > 0 else None
    provider_top = provider_counts.most_common(1)[0][0] if provider_counts else None

    return RouteRunsSummary(
        optimization_count=optimization_count,
        total_fleet_distance_km=total_km,
        solver_mix=solver_mix,
        elapsed_ms_p50=elapsed_p50,
        elapsed_ms_p90=elapsed_p90,
        degraded_leg_pct=degraded_pct,
        provider_status=provider_top,
    )


async def _load_road_access_context(
    sim_run_id: str, state: AppState,
) -> RoadAccessContext | None:
    """
    Most recent road-access snapshot referenced by any optimization run in
    this sim. Falls back to the in-memory current snapshot via state.road_access
    when Snowflake yields nothing.
    """
    runner = getattr(state, "_sf_query_runner", None)
    if runner is not None:
        try:
            rows = await _run_with_timeout(
                runner,
                """
                SELECT s.FEATURE_COUNT, s.HARD_AVOID_COUNT, s.SOFT_PENALTY_COUNT,
                       s.PROVIDER, s.LOADED_AT
                FROM CLEAN.ROAD_ACCESS_SNAPSHOTS s
                JOIN SERVING.ROUTE_RECOMMENDATIONS r ON r.ROAD_ACCESS_ID = s.ROAD_ACCESS_ID
                WHERE r.SIM_RUN_ID = %s AND s.ROAD_ACCESS_ID IS NOT NULL
                ORDER BY s.LOADED_AT DESC
                LIMIT 1
                """,
                (sim_run_id,),
                label="road_access_context",
            )
            if rows:
                row = rows[0]
                return RoadAccessContext(
                    feature_count=int(_row_float(row, "FEATURE_COUNT") or 0),
                    hard_avoid_count=int(_row_float(row, "HARD_AVOID_COUNT") or 0),
                    soft_penalty_count=int(_row_float(row, "SOFT_PENALTY_COUNT") or 0),
                    provider=row.get("PROVIDER") or row.get("provider"),
                    loaded_at=_row_dt(row, "LOADED_AT"),
                )
        except TimeoutError as e:
            log.warning("aar: road_access query timed out (%s) — falling through", e)
        except Exception as e:  # noqa: BLE001
            log.warning("aar: road_access query failed (%s) — falling through", e)

    # In-memory fallback: synthesize from the current snapshot. Better than None
    # for the demo path where Snowflake isn't configured.
    try:
        from disaster.routing.weighted import summarize_road_access
        snapshot = await state.road_access.get()
        summary = summarize_road_access(snapshot)
        if summary.get("feature_count", 0) == 0:
            return None
        return RoadAccessContext(
            feature_count=int(summary.get("feature_count", 0)),
            hard_avoid_count=int(summary.get("hard_avoid_count", 0)),
            soft_penalty_count=int(summary.get("soft_penalty_count", 0)),
            provider=summary.get("provider"),
            loaded_at=None,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("aar: road_access in-memory fallback failed (%s)", e)
        return None


async def _load_cortex_alerts(
    state: AppState,
    started_at: datetime | None,
    ended_at: datetime | None,
    *,
    is_live: bool,
) -> list[CortexAlertEvent]:
    """
    Alerts that fired during the run window. Alerts aren't sim-stamped (they're
    sensor-scoped), so the temporal filter is the natural join. Capped at 50.
    """
    if is_live or started_at is None or ended_at is None:
        return []
    runner = getattr(state, "_sf_query_runner", None)
    if runner is None:
        return []
    try:
        rows = await _run_with_timeout(
            runner,
            """
            SELECT ALERT_ID, ALERT_TYPE, SEVERITY, MESSAGE, DETECTED_AT, SECTOR_ID
            FROM SERVING.CORTEX_ALERTS
            WHERE DETECTED_AT BETWEEN %s AND %s
            ORDER BY DETECTED_AT
            LIMIT 50
            """,
            (started_at.isoformat(), ended_at.isoformat()),
            label="cortex_alerts",
        )
    except TimeoutError as e:
        log.warning("aar: cortex_alerts query timed out (%s)", e)
        return []
    except Exception as e:  # noqa: BLE001
        log.warning("aar: cortex_alerts query failed (%s)", e)
        return []

    alerts: list[CortexAlertEvent] = []
    for row in rows:
        detected = _row_dt(row, "DETECTED_AT")
        if detected is None:
            continue
        alert_id = row.get("ALERT_ID") or row.get("alert_id")
        if not alert_id:
            continue
        alerts.append(CortexAlertEvent(
            alert_id=str(alert_id),
            alert_type=str(row.get("ALERT_TYPE") or row.get("alert_type") or "cluster"),
            severity=str(row.get("SEVERITY") or row.get("severity") or "info"),
            message=row.get("MESSAGE") or row.get("message"),
            detected_at=detected,
            sector_id=row.get("SECTOR_ID") or row.get("sector_id"),
        ))
    return alerts


# ── Scorecard + timeline builders ────────────────────────────────────────────

def _build_scorecard(
    incidents: list[IncidentReport],
    resolved_etas: dict[UUID, ResolvedETA],
    route_runs: RouteRunsSummary,
) -> AARScorecard:
    assigned_etas = [resolved_etas[i.id].seconds for i in incidents if i.id in resolved_etas]
    actual_etas = [
        resolved_etas[i.id].seconds
        for i in incidents
        if i.id in resolved_etas and resolved_etas[i.id].source == "actual"
    ]
    estimated_etas = [
        resolved_etas[i.id].seconds
        for i in incidents
        if i.id in resolved_etas and resolved_etas[i.id].source != "actual"
    ]
    vuln_incidents = [i for i in incidents if has_vulnerable_victim(i)]
    vuln_assigned_etas = [
        resolved_etas[i.id].seconds for i in vuln_incidents if i.id in resolved_etas
    ]
    voice_confidences = [i.confidence for i in incidents if i.source.value == "voice"]

    actuals_coverage = len(actual_etas) / len(assigned_etas) if assigned_etas else 0.0
    delta = None
    if (
        actuals_coverage >= _MIN_DELTA_COVERAGE
        and actual_etas
        and estimated_etas
    ):
        delta = statistics.median(actual_etas) - statistics.median(estimated_etas)

    return AARScorecard(
        incident_count=len(incidents),
        assigned_count=len(assigned_etas),
        assigned_pct=len(assigned_etas) / len(incidents) if incidents else 0.0,
        p50_eta_seconds=statistics.median(assigned_etas) if assigned_etas else None,
        p90_eta_seconds=_percentile(assigned_etas, 0.9) if assigned_etas else None,
        total_fleet_distance_km=route_runs.total_fleet_distance_km,
        vulnerable_incident_count=len(vuln_incidents),
        vulnerable_assigned_count=len(vuln_assigned_etas),
        vulnerable_eta_p50_seconds=statistics.median(vuln_assigned_etas) if vuln_assigned_etas else None,
        extraction_confidence_p50=statistics.median(voice_confidences) if voice_confidences else None,
        actual_eta_p50_seconds=statistics.median(actual_etas) if actual_etas else None,
        actual_eta_p90_seconds=_percentile(actual_etas, 0.9) if actual_etas else None,
        eta_actual_vs_estimated_p50_delta_seconds=delta,
        actuals_coverage_pct=actuals_coverage,
    )


def _build_actual_policy_result(
    incidents: list[IncidentReport],
    resolved_etas: dict[UUID, ResolvedETA],
    route_runs: RouteRunsSummary,
) -> PolicyResult:
    """
    The 'actual' column of the counterfactual panel. p50/p90 stay on the same
    yardstick as the replays (estimated ETAs) so the comparison is apples-to-
    apples. Real solver-run aggregates (solver mix, fleet km, degraded %, etc.)
    are surfaced as extra fields for the UI footer.
    """
    assigned_etas = [resolved_etas[i.id].seconds for i in incidents if i.id in resolved_etas]
    vuln_etas = [
        resolved_etas[i.id].seconds
        for i in incidents
        if i.id in resolved_etas and has_vulnerable_victim(i)
    ]
    return PolicyResult(
        key="actual",
        label="Actual dispatch",
        is_actual=True,
        assigned_count=len(assigned_etas),
        total_fleet_distance_km=route_runs.total_fleet_distance_km,
        p50_eta_seconds=statistics.median(assigned_etas) if assigned_etas else None,
        p90_eta_seconds=_percentile(assigned_etas, 0.9) if assigned_etas else None,
        vulnerable_assigned_count=len(vuln_etas),
        vulnerable_eta_p50_seconds=statistics.median(vuln_etas) if vuln_etas else None,
        solver_mix=route_runs.solver_mix or None,
        elapsed_ms_p50=route_runs.elapsed_ms_p50,
        elapsed_ms_p90=route_runs.elapsed_ms_p90,
        degraded_leg_pct=route_runs.degraded_leg_pct,
        provider_status=route_runs.provider_status,
        optimization_count=route_runs.optimization_count or None,
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
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[idx]


def _weighted_mean(pairs: list[tuple[float, int]]) -> float | None:
    """Aggregate per-solver percentiles back into one number, weighted by run count."""
    total_weight = sum(w for _, w in pairs)
    if total_weight <= 0:
        return None
    return sum(v * w for v, w in pairs) / total_weight


def _split_csv(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(p) for p in value if p]
    return [p.strip() for p in str(value).split(",") if p.strip()]


def _row_uuid(row: dict[str, Any], col: str) -> UUID | None:
    raw = row.get(col) or row.get(col.lower())
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _row_float(row: dict[str, Any], col: str) -> float | None:
    raw = row.get(col)
    if raw is None:
        raw = row.get(col.lower())
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _row_dt(row: dict[str, Any], col: str) -> datetime | None:
    raw = row.get(col) or row.get(col.lower())
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return (end - start).total_seconds()


def clear_cache() -> None:
    """Test helper. Wipes the single-flight cache so tests don't see stale results."""
    _aar_cache.clear()
    _aar_inflight.clear()
