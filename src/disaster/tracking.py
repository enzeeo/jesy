"""Responder location tracking and arrival detection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class ArrivalDetectionResult:
    arrival_detected: bool
    distance_m: float
    detection_method: str | None = None
    already_arrived: bool = False


@dataclass
class _ArrivalDwellState:
    inside_ping_count: int = 0
    first_inside_at: datetime | None = None
    arrived: bool = False


class ResponderTrackingStore:
    """Stateful geofence+dwell detector for phone-style responder pings."""

    def __init__(
        self,
        *,
        arrival_radius_m: float = 50.0,
        dwell_seconds: float = 30.0,
        required_inside_pings: int = 2,
    ) -> None:
        self.arrival_radius_m = arrival_radius_m
        self.dwell_seconds = dwell_seconds
        self.required_inside_pings = required_inside_pings
        self._states: dict[tuple[UUID, UUID], _ArrivalDwellState] = {}

    def record_ping(
        self,
        *,
        responder_id: UUID,
        incident_id: UUID,
        timestamp: datetime,
        distance_m: float,
    ) -> ArrivalDetectionResult:
        key = (responder_id, incident_id)
        state = self._states.setdefault(key, _ArrivalDwellState())
        if state.arrived:
            return ArrivalDetectionResult(
                arrival_detected=False,
                distance_m=distance_m,
                detection_method="already_arrived",
                already_arrived=True,
            )

        if distance_m > self.arrival_radius_m:
            state.inside_ping_count = 0
            state.first_inside_at = None
            return ArrivalDetectionResult(arrival_detected=False, distance_m=distance_m)

        if state.first_inside_at is None:
            state.first_inside_at = timestamp
        state.inside_ping_count += 1

        dwell_met = (timestamp - state.first_inside_at).total_seconds() >= self.dwell_seconds
        pings_met = state.inside_ping_count >= self.required_inside_pings
        if dwell_met or pings_met:
            state.arrived = True
            method = "geofence_dwell" if dwell_met else "geofence_two_pings"
            return ArrivalDetectionResult(
                arrival_detected=True,
                distance_m=distance_m,
                detection_method=method,
            )

        return ArrivalDetectionResult(arrival_detected=False, distance_m=distance_m)
