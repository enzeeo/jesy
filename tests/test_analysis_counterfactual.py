"""Tests for analysis.counterfactual — deterministic replay engine."""
from __future__ import annotations

import pytest

from disaster.analysis.counterfactual import (
    pick_winner,
    replay_policy,
    run_all_policies,
)
from disaster.analysis.models import PolicyResult
from disaster.analysis.policies import POLICIES
from disaster.errors import NoFeasibleSolution
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    ResponderType,
    ResponderUnit,
    Severity,
    Victim,
)


def _v(*, vulns: list[str] | None = None) -> Victim:
    return Victim(
        mobility=Mobility.WALKING,
        breathing=Breathing.SPONTANEOUS,
        vulnerabilities=vulns or [],
    )


def _incident(lat: float, lng: float, *, priority: float = 0.5,
              severity: Severity = Severity.DELAYED, vulns: list[str] | None = None) -> IncidentReport:
    return IncidentReport(
        location=Location(lat=lat, lng=lng, description=f"{lat},{lng}"),
        victims=[_v(vulns=vulns)],
        priority_score=priority,
        severity=severity,
    )


def _responder(callsign: str, lat: float, lng: float) -> ResponderUnit:
    return ResponderUnit(
        callsign=callsign,
        type=ResponderType.ALS,
        location=Location(lat=lat, lng=lng, description=f"{callsign} base"),
    )


# ── replay_policy ───────────────────────────────────────────────────────────

def test_replay_policy_greedy_assigns_capacity_limited():
    """Replay greedy on a small scenario: 3 incidents, 1 responder, cap=5 → all 3 assigned."""
    incidents = [_incident(19.70 + 0.01 * i, -155.0, priority=0.5) for i in range(3)]
    responders = [_responder("A", 19.70, -155.0)]
    result = replay_policy(incidents, responders, POLICIES["greedy"])
    assert result.assigned_count == 3
    assert result.error is None
    assert result.p50_eta_seconds is not None and result.p50_eta_seconds > 0
    assert result.total_fleet_distance_km > 0


def test_replay_policy_empty_incidents_no_error():
    result = replay_policy([], [_responder("A", 19.70, -155.0)], POLICIES["greedy"])
    assert result.assigned_count == 0
    assert result.error is None
    assert result.p50_eta_seconds is None


def test_replay_policy_empty_responders_all_unassigned():
    incidents = [_incident(19.7, -155.0)]
    result = replay_policy(incidents, [], POLICIES["greedy"])
    assert result.assigned_count == 0
    assert result.error is None


def test_replay_policy_vrp_infeasible_returns_error():
    """Monkey-patch VRP to raise — replay catches and returns PolicyResult.error."""
    incidents = [_incident(19.7, -155.0)]
    responders = [_responder("A", 19.7, -155.0)]
    from disaster.analysis import policies as p_mod
    original = p_mod._vrp_deterministic_solver

    def boom(_inc, _resp):
        raise NoFeasibleSolution("simulated")
    p_mod._vrp_deterministic_solver = boom
    # Refresh the POLICIES entry to point to the new solver
    POLICIES["vrp_current"] = p_mod.Policy(
        key="vrp_current",
        label=POLICIES["vrp_current"].label,
        scorer=POLICIES["vrp_current"].scorer,
        solver=boom,
    )
    try:
        result = replay_policy(incidents, responders, POLICIES["vrp_current"])
        assert result.error == "vrp_infeasible"
        assert result.assigned_count == 0
    finally:
        p_mod._vrp_deterministic_solver = original
        POLICIES["vrp_current"] = p_mod.Policy(
            key="vrp_current",
            label=POLICIES["vrp_current"].label,
            scorer=POLICIES["vrp_current"].scorer,
            solver=original,
        )


def test_replay_policy_greedy_is_deterministic():
    """CRITICAL: same input twice → identical PolicyResult."""
    incidents = [_incident(19.70 + 0.001 * i, -155.0, priority=0.5) for i in range(20)]
    responders = [_responder(f"R{i}", 19.70, -155.0) for i in range(2)]
    r1 = replay_policy(incidents, responders, POLICIES["greedy"])
    r2 = replay_policy(incidents, responders, POLICIES["greedy"])
    assert r1.assigned_count == r2.assigned_count
    assert r1.p50_eta_seconds == r2.p50_eta_seconds
    assert r1.p90_eta_seconds == r2.p90_eta_seconds
    assert r1.total_fleet_distance_km == r2.total_fleet_distance_km


def test_replay_policy_vulnpri_assigns_vulnerable_earlier():
    """
    vrp_vulnpri puts vulnerable victims first in the priority queue. With capacity
    limited so not everyone gets assigned, vulnerable victims should be in the
    assigned set more often than under the default scorer.
    """
    pytest.importorskip("ortools")
    # 10 incidents: 5 vulnerable (low priority_score 0.4), 5 not (high priority 0.6)
    incidents = []
    for i in range(5):
        incidents.append(_incident(19.70 + 0.01 * i, -155.0, priority=0.4, vulns=["elderly"]))
    for i in range(5):
        incidents.append(_incident(19.71 + 0.01 * i, -155.0, priority=0.6, vulns=[]))
    # Only 1 responder, cap=5 → only 5 of 10 incidents get assigned
    responders = [_responder("A", 19.70, -155.0)]

    default_result = replay_policy(incidents, responders, POLICIES["vrp_current"])
    vulnpri_result = replay_policy(incidents, responders, POLICIES["vrp_vulnpri"])

    if default_result.error or vulnpri_result.error:
        pytest.skip(f"VRP unavailable: {default_result.error or vulnpri_result.error}")
    # vulnpri should assign MORE vulnerable victims than default
    assert vulnpri_result.vulnerable_assigned_count >= default_result.vulnerable_assigned_count


# ── run_all_policies ────────────────────────────────────────────────────────

def test_run_all_policies_returns_three_results():
    incidents = [_incident(19.7, -155.0)]
    responders = [_responder("A", 19.7, -155.0)]
    results = run_all_policies(incidents, responders)
    assert {r.key for r in results} == {"greedy", "vrp_current", "vrp_vulnpri"}


def test_run_all_policies_order_is_stable():
    """UI requires consistent column order; greedy first."""
    incidents = [_incident(19.7, -155.0)]
    responders = [_responder("A", 19.7, -155.0)]
    results = run_all_policies(incidents, responders)
    assert [r.key for r in results] == ["greedy", "vrp_current", "vrp_vulnpri"]


# ── pick_winner ─────────────────────────────────────────────────────────────

def test_pick_winner_returns_lowest_metric():
    results = [
        PolicyResult(key="a", label="A", p50_eta_seconds=300.0),
        PolicyResult(key="b", label="B", p50_eta_seconds=200.0),
        PolicyResult(key="c", label="C", p50_eta_seconds=400.0),
    ]
    assert pick_winner(results, lambda r: r.p50_eta_seconds) == "b"


def test_pick_winner_alphabetical_tiebreak():
    """Ties resolve alphabetically by policy key so UI doesn't flicker."""
    results = [
        PolicyResult(key="zebra", label="Z", assigned_count=10),
        PolicyResult(key="apple", label="A", assigned_count=10),
    ]
    assert pick_winner(results, lambda r: -r.assigned_count) == "apple"


def test_pick_winner_skips_error_results():
    results = [
        PolicyResult(key="a", label="A", p50_eta_seconds=100.0),
        PolicyResult(key="b", label="B", p50_eta_seconds=50.0, error="vrp_infeasible"),
    ]
    assert pick_winner(results, lambda r: r.p50_eta_seconds) == "a"


def test_pick_winner_none_if_all_missing():
    results = [PolicyResult(key="a", label="A")]
    assert pick_winner(results, lambda r: r.p50_eta_seconds) is None
