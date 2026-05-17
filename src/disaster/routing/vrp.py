"""
OR-Tools VRP solver.

Capacitated VRP: each responder is a vehicle with capacity = how many incidents
they can chain. Distance matrix in meters via haversine. Time-limited; raises
NoFeasibleSolution on timeout/infeasible so the caller can greedy-fallback.

Used in the writeup ("we ran real VRP") and as a backup if greedy produces a
visibly suboptimal route on demo day.
"""
from __future__ import annotations

import logging
import time
from uuid import UUID

from disaster.errors import NoFeasibleSolution
from disaster.models import IncidentReport, ResponderUnit
from disaster.routing.greedy import _haversine_km

log = logging.getLogger(__name__)


def solve_vrp(
    incidents: list[IncidentReport],
    responders: list[ResponderUnit],
    *,
    time_budget_s: float | None = 2.0,
    vehicle_capacity: int = 5,
):
    """
    Returns an Assignment. Raises NoFeasibleSolution on infeasible/timeout.

    Set time_budget_s=None for the deterministic replay path: skips guided local
    search and uses only the first-solution heuristic (PATH_CHEAPEST_ARC). The
    output becomes bit-stable across runs at the cost of optimality.
    """
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError as e:
        raise NoFeasibleSolution(f"ortools not installed: {e}") from e

    from disaster.routing.optimize import Assignment, RouteLeg

    t0 = time.monotonic()
    n_responders = len(responders)
    n_incidents = len(incidents)
    if n_responders == 0 or n_incidents == 0:
        return Assignment(solver="vrp")

    # Node 0..n_responders-1 are depots (responder starting locations).
    # Nodes n_responders..n_responders+n_incidents-1 are incidents.
    n_nodes = n_responders + n_incidents
    locations: list[tuple[float, float]] = [
        (r.location.lat, r.location.lng) for r in responders
    ] + [(i.location.lat, i.location.lng) for i in incidents]

    distance_m = [[0] * n_nodes for _ in range(n_nodes)]
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i == j:
                continue
            distance_m[i][j] = int(_haversine_km(locations[i], locations[j]) * 1000)

    # Capacity demand: 1 per incident node, 0 per depot
    demands = [0] * n_responders + [1] * n_incidents
    vehicle_capacities = [vehicle_capacity] * n_responders

    starts = list(range(n_responders))
    ends = list(range(n_responders))   # return to start (acceptable for hackathon)

    manager = pywrapcp.RoutingIndexManager(n_nodes, n_responders, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_idx, to_idx):
        return distance_m[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    def demand_callback(from_idx):
        return demands[manager.IndexToNode(from_idx)]

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx, 0, vehicle_capacities, True, "Capacity",
    )

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    if time_budget_s is not None:
        # Wall-clock-bounded GLS: better solutions, non-deterministic across runs.
        search.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search.time_limit.FromSeconds(int(time_budget_s))
    # else: deterministic first-solution-only mode for replay (no GLS, no time budget)

    solution = routing.SolveWithParameters(search)
    if solution is None:
        raise NoFeasibleSolution(f"vrp: no solution (time_budget={time_budget_s}s)")

    routes: dict[UUID, list[RouteLeg]] = {r.id: [] for r in responders}
    assigned_nodes: set[int] = set()
    for v in range(n_responders):
        responder = responders[v]
        idx = routing.Start(v)
        prev_node = manager.IndexToNode(idx)
        while not routing.IsEnd(idx):
            next_idx = solution.Value(routing.NextVar(idx))
            node = manager.IndexToNode(next_idx)
            if node >= n_responders:   # an incident node
                assigned_nodes.add(node)
                incident = incidents[node - n_responders]
                dist_km = distance_m[prev_node][node] / 1000.0
                eta_s = (dist_km / 50.0) * 3600.0
                # Build a RouteLeg using actual coordinates
                from_lat, from_lng = locations[prev_node]
                routes[responder.id].append(RouteLeg(
                    incident_id=incident.id,
                    from_location=responder.location.model_copy(
                        update={"lat": from_lat, "lng": from_lng},
                    ),
                    to_location=incident.location,
                    distance_km=dist_km,
                    eta_seconds=eta_s,
                ))
            prev_node = node
            idx = next_idx

    unassigned: list[UUID] = []
    for i, incident in enumerate(incidents):
        if (n_responders + i) not in assigned_nodes:
            unassigned.append(incident.id)

    return Assignment(
        routes=routes,
        unassigned=unassigned,
        solver="vrp",
        elapsed_ms=(time.monotonic() - t0) * 1000.0,
    )
