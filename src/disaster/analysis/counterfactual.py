"""
Counterfactual replay engine.

  incidents (frozen)  ──┐
  responders (frozen) ──┼─▶ for each Policy:
                        │     1. scorer re-ranks incidents
                        │     2. solver assigns
                        │     3. compute PolicyResult metrics
                        └─▶ list[PolicyResult]

IMPORTANT: results live ONLY in the AAR response. They are NEVER written to
responder_dispatches (which is the source-of-truth for "what actually happened").
Persisting replays to that table would corrupt the live actual baseline.

VRP infeasibility / timeout is caught and returned as PolicyResult(error="..."),
NOT silently fallen back to greedy. The counterfactual MUST be honest — a
greedy fallback labelled "vrp_vulnpri" is worse than a missing comparison.
"""
from __future__ import annotations

import logging
import statistics
from collections.abc import Callable
from uuid import UUID

from disaster.analysis.models import PolicyResult
from disaster.analysis.policies import (
    POLICIES,
    Policy,
    apply_scorer_to_incidents,
    has_vulnerable_victim,
)
from disaster.errors import NoFeasibleSolution
from disaster.models import IncidentReport, ResponderUnit

log = logging.getLogger(__name__)


def replay_policy(
    incidents: list[IncidentReport],
    responders: list[ResponderUnit],
    policy: Policy,
) -> PolicyResult:
    """
    Run one policy against a frozen incident stream + responder set. Returns a
    PolicyResult (with `error` set on solver failure rather than raising).

    Empty incidents → assigned_count=0 with no error.
    Empty responders → assigned_count=0 (all unassigned) with no error.
    VRP infeasibility → assigned_count=0, error="vrp_infeasible".
    """
    ranked = apply_scorer_to_incidents(incidents, policy.scorer)

    try:
        assignment = policy.solver(ranked, responders)
    except NoFeasibleSolution as e:
        log.info("counterfactual: %s infeasible: %s", policy.key, e)
        return PolicyResult(
            key=policy.key,
            label=policy.label,
            assigned_count=0,
            total_fleet_distance_km=0.0,
            error="vrp_infeasible",
        )

    assigned_legs = [leg for legs in assignment.routes.values() for leg in legs]
    etas = [leg.eta_seconds for leg in assigned_legs]
    fleet_km = sum(leg.distance_km for leg in assigned_legs)

    # vulnerable-victim ETA subset
    incident_by_id = {i.id: i for i in incidents}
    vuln_etas: list[float] = []
    vuln_assigned = 0
    for leg in assigned_legs:
        inc = incident_by_id.get(leg.incident_id)
        if inc is not None and has_vulnerable_victim(inc):
            vuln_etas.append(leg.eta_seconds)
            vuln_assigned += 1

    return PolicyResult(
        key=policy.key,
        label=policy.label,
        assigned_count=len(assigned_legs),
        total_fleet_distance_km=fleet_km,
        p50_eta_seconds=statistics.median(etas) if etas else None,
        p90_eta_seconds=_percentile(etas, 0.9) if etas else None,
        vulnerable_assigned_count=vuln_assigned,
        vulnerable_eta_p50_seconds=statistics.median(vuln_etas) if vuln_etas else None,
    )


def run_all_policies(
    incidents: list[IncidentReport],
    responders: list[ResponderUnit],
    policies: dict[str, Policy] | None = None,
) -> list[PolicyResult]:
    """Run every registered policy in deterministic order. Defaults to POLICIES."""
    policies = policies if policies is not None else POLICIES
    # Order matters for the UI: greedy first (familiar baseline), then VRP variants.
    order = ["greedy", "vrp_current", "vrp_vulnpri"]
    out: list[PolicyResult] = []
    for key in order:
        if key not in policies:
            continue
        out.append(replay_policy(incidents, responders, policies[key]))
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────

def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile. Empty input MUST NOT reach here."""
    if not values:
        raise ValueError("percentile: empty input")
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def pick_winner(results: list[PolicyResult], key_fn: Callable[[PolicyResult], float | None]) -> str | None:
    """
    Choose the winning policy by some metric (smaller is better for ETAs, larger
    for assignment counts — caller flips sign via key_fn). Ties resolve alphabetically
    by policy key so the UI doesn't flicker. Returns None if no policy has a value.
    """
    candidates = [r for r in results if key_fn(r) is not None and r.error is None]
    if not candidates:
        return None
    # Sort key: (metric, key) → first is winner
    sorted_candidates = sorted(candidates, key=lambda r: (key_fn(r), r.key))  # type: ignore[arg-type]
    return sorted_candidates[0].key


def _resolve_uuid(value: str | UUID) -> UUID:
    """Normalize str | UUID → UUID. Used by /api/analysis to thread the URL param through."""
    return value if isinstance(value, UUID) else UUID(value)
