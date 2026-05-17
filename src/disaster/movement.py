"""Server-owned responder movement and location update helpers."""
from __future__ import annotations

import asyncio
import contextlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from disaster.models import IncidentStatus, Location, ResponderStatus
from disaster.routing.greedy import _haversine_km
from disaster.store import ActiveDispatch

if TYPE_CHECKING:
    from disaster.app.deps import AppState


DEFAULT_MOVEMENT_INTERVAL_S = 1.5
DEFAULT_ROUTE_STEPS = 12
DEFAULT_FINAL_DWELL_PINGS = 2
DEFAULT_ACCURACY_M = 12.0


async def serialize_active_dispatch(
    state: AppState,
    dispatch: ActiveDispatch,
) -> dict[str, Any] | None:
    """Return the frontend hydration shape for one active dispatch."""

    responder = await state.responders.get(dispatch.responder_id)
    incident = await state.incidents.get(dispatch.incident_id)
    if responder is None or incident is None:
        return None

    route_leg = deepcopy(dispatch.leg)
    route_progress: float | None = None
    remaining_route_geometry: dict[str, Any] | None = None
    movement = getattr(state, "dispatch_movement", None)
    progress_for = getattr(movement, "progress_for", None)
    if callable(progress_for):
        progress = progress_for(dispatch.responder_id, dispatch.dispatch_id)
        if progress is not None:
            route_progress = progress["route_progress"]
            remaining_route_geometry = progress["remaining_route_geometry"]
            route_leg["route_geometry"] = remaining_route_geometry

    payload = {
        "assignment_id": dispatch.dispatch_id,
        "route_id": dispatch.route_id,
        "leg_id": dispatch.leg_id,
        "responder_id": str(dispatch.responder_id),
        "incident_id": str(dispatch.incident_id),
        "status": responder.status.value,
        "eta_seconds": dispatch.leg.get("eta_seconds"),
        "distance_km": dispatch.leg.get("distance_km"),
        "route_leg": route_leg,
        "leg": route_leg,
        "responder": responder.model_dump(mode="json"),
        "incident": incident.model_dump(mode="json"),
    }
    if route_progress is not None:
        payload["route_progress"] = route_progress
    if remaining_route_geometry is not None:
        payload["remaining_route_geometry"] = remaining_route_geometry
    return payload


async def record_responder_location(
    state: AppState,
    *,
    responder_id: UUID,
    location: Location,
    timestamp: datetime,
    accuracy_m: float,
    speed_mps: float | None = None,
    heading: float | None = None,
    assignment: dict[str, Any] | None = None,
    route_progress: float | None = None,
    remaining_route_geometry: dict[str, Any] | None = None,
    emit_location_ping: bool = False,
) -> dict[str, Any]:
    """Update responder location, emit SSE, and run arrival detection."""

    responder = await state.responders.get(responder_id)
    if responder is None:
        raise KeyError(f"responder {responder_id} not found")

    updated_responder = responder.model_copy(update={"location": location})
    await state.responders.upsert(updated_responder)

    active_dispatch = await state.active_dispatches.get_for_responder(responder_id)
    if assignment is None and active_dispatch is not None:
        assignment = await serialize_active_dispatch(state, active_dispatch)

    if emit_location_ping and state.snowflake is not None:
        from disaster.snowflake import ingest
        ingest.emit_location_ping(
            state.snowflake,
            responder_id=str(responder_id),
            lat=location.lat,
            lng=location.lng,
            accuracy_m=accuracy_m,
            timestamp=timestamp,
            assigned_incident_id=str(updated_responder.assigned_incident_id)
            if updated_responder.assigned_incident_id
            else None,
            route_id=active_dispatch.route_id if active_dispatch else None,
            leg_id=active_dispatch.leg_id if active_dispatch else None,
            status=updated_responder.status.value,
            speed_mps=speed_mps,
            heading=heading,
        )

    event_data: dict[str, Any] = {
        "responder_id": str(responder_id),
        "responder": updated_responder.model_dump(mode="json"),
        "callsign": updated_responder.callsign,
        "status": updated_responder.status.value,
        "location": location.model_dump(),
        "accuracy_m": accuracy_m,
        "timestamp": timestamp.isoformat(),
        "speed_mps": speed_mps,
        "heading": heading,
    }
    if assignment is not None:
        event_data["assignment"] = assignment
    if route_progress is not None:
        event_data["route_progress"] = route_progress
    if remaining_route_geometry is not None:
        event_data["remaining_route_geometry"] = remaining_route_geometry

    await state.events.publish({
        "type": "responder_location_updated",
        "data": event_data,
        "sequence_id": state.events.next_sequence_id(),
    })

    incident_id = updated_responder.assigned_incident_id
    if incident_id is None:
        return {
            "responder_id": str(responder_id),
            "arrival_detected": False,
            "incident_id": None,
        }

    incident = await state.incidents.get(incident_id)
    if incident is None:
        return {
            "responder_id": str(responder_id),
            "arrival_detected": False,
            "incident_id": str(incident_id),
            "warning": "assigned incident not found",
        }

    distance_m = _haversine_km(
        (location.lat, location.lng),
        (incident.location.lat, incident.location.lng),
    ) * 1000.0
    detection = state.responder_tracking.record_ping(
        responder_id=responder_id,
        incident_id=incident.id,
        timestamp=timestamp,
        distance_m=distance_m,
    )

    if not detection.arrival_detected:
        return {
            "responder_id": str(responder_id),
            "arrival_detected": False,
            "incident_id": str(incident.id),
            "distance_m": detection.distance_m,
        }

    on_scene_responder = updated_responder.model_copy(update={"status": ResponderStatus.ON_SCENE})
    await state.responders.upsert(on_scene_responder)
    on_scene_incident = incident.model_copy(update={"status": IncidentStatus.ON_SCENE})
    await state.incidents.update(on_scene_incident)
    active_dispatch = await state.active_dispatches.get_for_responder(responder_id)

    snowflake_row = {
        "responder_id": str(on_scene_responder.id),
        "callsign": on_scene_responder.callsign,
        "incident_id": str(incident.id),
        "cluster_id": None,
        "arrival_timestamp": timestamp.isoformat(),
        "ping_lat": location.lat,
        "ping_lng": location.lng,
        "accuracy_m": accuracy_m,
        "route_id": active_dispatch.route_id if active_dispatch is not None else None,
        "assignment_id": active_dispatch.dispatch_id if active_dispatch is not None else str(incident.id),
        "detection_method": detection.detection_method,
        "distance_m": detection.distance_m,
    }
    if state.snowflake is not None:
        from disaster.snowflake import ingest
        ingest.emit_arrival(state.snowflake, snowflake_row)

    await state.events.publish({
        "type": "responder_arrived",
        "data": {
            "responder_id": str(responder_id),
            "responder": on_scene_responder.model_dump(mode="json"),
            "callsign": on_scene_responder.callsign,
            "incident_id": str(incident.id),
            "arrival_timestamp": timestamp.isoformat(),
            "location": location.model_dump(),
            "distance_m": detection.distance_m,
            "accuracy_m": accuracy_m,
            "detection_method": detection.detection_method,
        },
        "sequence_id": state.events.next_sequence_id(),
    })

    return {
        "responder_id": str(responder_id),
        "arrival_detected": True,
        "incident_id": str(incident.id),
        "distance_m": detection.distance_m,
        "detection_method": detection.detection_method,
    }


class DispatchMovementService:
    """Advance active dispatches by emitting authoritative location updates."""

    def __init__(
        self,
        *,
        state: AppState,
        interval_s: float = DEFAULT_MOVEMENT_INTERVAL_S,
        route_steps: int = DEFAULT_ROUTE_STEPS,
        final_dwell_pings: int = DEFAULT_FINAL_DWELL_PINGS,
        accuracy_m: float = DEFAULT_ACCURACY_M,
    ) -> None:
        self._state = state
        self.interval_s = max(0.001, interval_s)
        self.route_steps = max(1, route_steps)
        self.final_dwell_pings = max(0, final_dwell_pings)
        self.accuracy_m = accuracy_m
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._dispatch_ids: dict[UUID, str] = {}
        self._progress: dict[UUID, dict[str, Any]] = {}

    async def start(self, dispatch: ActiveDispatch) -> None:
        """Start movement for a dispatch unless that dispatch is already moving."""

        responder_id = dispatch.responder_id
        existing_task = self._tasks.get(responder_id)
        if (
            existing_task is not None
            and not existing_task.done()
            and self._dispatch_ids.get(responder_id) == dispatch.dispatch_id
        ):
            return

        await self.cancel(responder_id)
        self._dispatch_ids[responder_id] = dispatch.dispatch_id
        self._tasks[responder_id] = asyncio.create_task(
            self._run(responder_id, dispatch.dispatch_id),
            name=f"dispatch-movement-{responder_id}",
        )

    async def cancel(self, responder_id: UUID) -> None:
        task = self._tasks.pop(responder_id, None)
        self._dispatch_ids.pop(responder_id, None)
        self._progress.pop(responder_id, None)
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def cancel_all(self) -> None:
        responder_ids = list(self._tasks)
        for responder_id in responder_ids:
            await self.cancel(responder_id)

    def progress_for(self, responder_id: UUID, dispatch_id: str) -> dict[str, Any] | None:
        if self._dispatch_ids.get(responder_id) != dispatch_id:
            return None
        progress = self._progress.get(responder_id)
        return deepcopy(progress) if progress is not None else None

    async def _run(self, responder_id: UUID, dispatch_id: str) -> None:
        try:
            ping_limit = self.route_steps + self.final_dwell_pings
            for ping_index in range(1, ping_limit + 1):
                await asyncio.sleep(self.interval_s)
                dispatch = await self._state.active_dispatches.get_for_responder(responder_id)
                if dispatch is None or dispatch.dispatch_id != dispatch_id:
                    return

                responder = await self._state.responders.get(responder_id)
                if responder is None or responder.status == ResponderStatus.ON_SCENE:
                    return

                coordinates = _route_coordinates(dispatch.leg)
                progress = min(1.0, ping_index / self.route_steps)
                lng, lat = _interpolate_route_point(coordinates, progress)
                remaining_route_geometry = {
                    "type": "LineString",
                    "coordinates": _remaining_route_coordinates(coordinates, progress),
                }
                self._progress[responder_id] = {
                    "route_progress": progress,
                    "remaining_route_geometry": remaining_route_geometry,
                }

                assignment = await serialize_active_dispatch(self._state, dispatch)
                result = await record_responder_location(
                    self._state,
                    responder_id=responder_id,
                    location=Location(lat=lat, lng=lng, description="server movement"),
                    timestamp=datetime.now(UTC),
                    accuracy_m=self.accuracy_m,
                    assignment=assignment,
                    route_progress=progress,
                    remaining_route_geometry=remaining_route_geometry,
                    emit_location_ping=True,
                )
                if result.get("arrival_detected"):
                    return
        finally:
            current_task = asyncio.current_task()
            if self._tasks.get(responder_id) is current_task:
                self._tasks.pop(responder_id, None)
                self._dispatch_ids.pop(responder_id, None)
                self._progress.pop(responder_id, None)


def _route_coordinates(leg: dict[str, Any]) -> list[tuple[float, float]]:
    geometry = leg.get("route_geometry")
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, list) and coordinates:
        parsed = []
        for coordinate in coordinates:
            if (
                isinstance(coordinate, list)
                and len(coordinate) >= 2
                and isinstance(coordinate[0], int | float)
                and isinstance(coordinate[1], int | float)
            ):
                parsed.append((float(coordinate[0]), float(coordinate[1])))
        if len(parsed) >= 2:
            return parsed

    from_location = leg["from_location"]
    to_location = leg["to_location"]
    return [
        (float(from_location["lng"]), float(from_location["lat"])),
        (float(to_location["lng"]), float(to_location["lat"])),
    ]


def _interpolate_route_point(
    coordinates: list[tuple[float, float]],
    progress: float,
) -> tuple[float, float]:
    if len(coordinates) == 1:
        return coordinates[0]

    segment_lengths = [
        _coordinate_distance(coordinates[index], coordinates[index + 1])
        for index in range(len(coordinates) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length <= 0:
        return coordinates[-1]

    remaining_distance = max(0.0, min(1.0, progress)) * total_length
    for index, segment_length in enumerate(segment_lengths):
        if remaining_distance > segment_length:
            remaining_distance -= segment_length
            continue
        previous = coordinates[index]
        next_coordinate = coordinates[index + 1]
        segment_progress = remaining_distance / segment_length if segment_length > 0 else 1.0
        return (
            previous[0] + (next_coordinate[0] - previous[0]) * segment_progress,
            previous[1] + (next_coordinate[1] - previous[1]) * segment_progress,
        )
    return coordinates[-1]


def _remaining_route_coordinates(
    coordinates: list[tuple[float, float]],
    progress: float,
) -> list[list[float]]:
    if len(coordinates) < 2:
        return [[coordinates[0][0], coordinates[0][1]]] if coordinates else []

    clamped_progress = max(0.0, min(1.0, progress))
    if clamped_progress <= 0:
        return [[lng, lat] for lng, lat in coordinates]
    if clamped_progress >= 1:
        final_lng, final_lat = coordinates[-1]
        return [[final_lng, final_lat], [final_lng, final_lat]]

    segment_lengths = [
        _coordinate_distance(coordinates[index], coordinates[index + 1])
        for index in range(len(coordinates) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length <= 0:
        return [[lng, lat] for lng, lat in coordinates]

    traveled_distance = clamped_progress * total_length
    for index, segment_length in enumerate(segment_lengths):
        if traveled_distance > segment_length:
            traveled_distance -= segment_length
            continue
        previous = coordinates[index]
        next_coordinate = coordinates[index + 1]
        segment_progress = traveled_distance / segment_length if segment_length > 0 else 1.0
        current = (
            previous[0] + (next_coordinate[0] - previous[0]) * segment_progress,
            previous[1] + (next_coordinate[1] - previous[1]) * segment_progress,
        )
        return [[current[0], current[1]], *[[lng, lat] for lng, lat in coordinates[index + 1:]]]

    final_lng, final_lat = coordinates[-1]
    return [[final_lng, final_lat], [final_lng, final_lat]]


def _coordinate_distance(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    return ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
