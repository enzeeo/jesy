"""
Dispatch policies for the AAR's counterfactual A/B/C panel.

Each Policy is (label, scorer, solver, solver_kwargs). The scorer turns an
IncidentReport into a sort key (more-negative = higher priority); the solver
is one of `greedy_assign` / `solve_vrp_deterministic`. The counterfactual
runner (counterfactual.py) replays a frozen incident stream through every
policy and returns the comparison metrics.

  POLICIES
  ├── greedy        — current production behavior (greedy nearest by priority)
  ├── vrp_current   — VRP in DETERMINISTIC mode (no time budget, no GLS)
  └── vrp_vulnpri   — VRP with vulnerability-priority scorer (elderly/child first)

Scorer values are negative because sorted(ascending) puts the smallest first;
"more negative = higher priority" matches Python's natural sort.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from disaster.models import IncidentReport
from disaster.routing import Assignment, greedy_assign
from disaster.routing.vrp import solve_vrp

# ── Vulnerability normalization ──────────────────────────────────────────────
#
# Victim.vulnerabilities is a free-form list[str] (no enum). Producers vary:
# the simulator emits lowercase canonical strings ("elderly", "child"), the
# stub extractor in /demo/trigger-call does too, but the real OpenAI extractor
# is unconstrained and might emit "ELDERLY", "elderly_person", "is_disabled",
# "non_ambulatory", etc. Vulnerability metrics silently miss real cases unless
# we normalize. One canonical class per known alias; unknown strings return None
# (still counted as incident, just not in any vuln class).

_VULN_ALIASES: dict[str, set[str]] = {
    "elderly": {"elderly", "elder", "senior", "old", "aged"},
    "child": {"child", "minor", "kid", "infant", "baby", "toddler"},
    "disabled": {
        "disabled", "disability", "handicapped", "non_ambulatory",
        "non_mobile", "wheelchair", "wheelchair_user",
    },
    "medical_dependency": {
        "medical_dependency", "medical_dep", "ventilator", "oxygen",
        "dialysis", "insulin", "pacemaker",
    },
}

# All canonical vulnerability classes the AAR reports on.
VULN_CLASSES: tuple[str, ...] = tuple(_VULN_ALIASES.keys())


def normalize_vulnerability(raw: str) -> str | None:
    """
    Map a raw vulnerability string to one of VULN_CLASSES, or None if unknown.

    Matches case-insensitively after replacing spaces/hyphens with underscores.
    Direct alias hit OR canonical class name appearing as substring.
    """
    s = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if not s:
        return None
    for canonical, aliases in _VULN_ALIASES.items():
        if s in aliases:
            return canonical
        if canonical in s:
            return canonical
    return None


def has_vulnerable_victim(incident: IncidentReport) -> bool:
    """True if ANY victim has at least one vulnerability that maps to a known class."""
    for victim in incident.victims:
        for raw in victim.vulnerabilities:
            if normalize_vulnerability(raw) is not None:
                return True
    return False


def incident_vuln_classes(incident: IncidentReport) -> set[str]:
    """All distinct canonical vulnerability classes present in this incident."""
    out: set[str] = set()
    for victim in incident.victims:
        for raw in victim.vulnerabilities:
            canonical = normalize_vulnerability(raw)
            if canonical is not None:
                out.add(canonical)
    return out


# ── Scorers ──────────────────────────────────────────────────────────────────

def score_default(incident: IncidentReport) -> float:
    """Sort key: more-negative = higher priority. Mirrors greedy.py's current behavior."""
    return -incident.priority_score


def score_vulnerability_priority(incident: IncidentReport) -> float:
    """
    Scorer that bumps incidents with vulnerable victims up the priority queue.
    Bonus of 0.2 is clamped so total stays within [0, 1] before negation.
    """
    bonus = 0.2 if has_vulnerable_victim(incident) else 0.0
    return -min(1.0, incident.priority_score + bonus)


# ── Solver adapters (unified signature for the counterfactual runner) ────────
#
# Each solver takes (incidents, responders) and returns an Assignment. We wrap
# greedy_assign and solve_vrp so the runner can call them through one interface
# without caring about kwargs.

SolverFn = Callable[[list[IncidentReport], list[Any]], Assignment]


def _greedy_solver(incidents: list[IncidentReport], responders: list[Any]) -> Assignment:
    return greedy_assign(incidents, responders, vehicle_capacity=5)


def _vrp_deterministic_solver(incidents: list[IncidentReport], responders: list[Any]) -> Assignment:
    """
    VRP for counterfactual replay. Bounded to 2s of solver wall time so
    infeasible inputs (total demand > total capacity, no disjunction
    penalties configured) raise NoFeasibleSolution instead of looping
    forever in OR-Tools C code and starving the asyncio loop. Bounding
    activates Guided Local Search, so results are not bit-stable across
    runs — acceptable trade for the AAR not hanging the whole worker.
    """
    return solve_vrp(incidents, responders, time_budget_s=2.0, vehicle_capacity=5)


# ── Policy registry ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Policy:
    """A named dispatch policy: scorer + solver. Used by counterfactual replay."""
    key: str
    label: str
    scorer: Callable[[IncidentReport], float]
    solver: SolverFn
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


POLICIES: dict[str, Policy] = {
    "greedy": Policy(
        key="greedy",
        label="Greedy (current)",
        scorer=score_default,
        solver=_greedy_solver,
        notes="Highest priority_score first, nearest available responder, chain up to vehicle_capacity",
    ),
    "vrp_current": Policy(
        key="vrp_current",
        label="VRP (deterministic)",
        scorer=score_default,
        solver=_vrp_deterministic_solver,
        notes="OR-Tools VRP with first-solution heuristic only (no GLS, no time budget)",
    ),
    "vrp_vulnpri": Policy(
        key="vrp_vulnpri",
        label="VRP + vulnerability priority",
        scorer=score_vulnerability_priority,
        solver=_vrp_deterministic_solver,
        notes="Same as vrp_current but vulnerable victims (elderly/child/disabled/medical_dep) get +0.2 priority bump",
    ),
}


def apply_scorer_to_incidents(
    incidents: list[IncidentReport],
    scorer: Callable[[IncidentReport], float],
) -> list[IncidentReport]:
    """
    Re-rank incidents by the policy's scorer, returning a NEW list. Uses a
    stable secondary sort on id so equal scores don't depend on Python's
    sort stability across versions (it IS stable in CPython, but explicit > clever).
    """
    return sorted(incidents, key=lambda i: (scorer(i), str(i.id)))
