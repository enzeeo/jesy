"""
Fan-out Snowflake writes across RAW / CLEAN / SERVING layers.

Call sites use these helpers instead of writing to legacy flat tables.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from disaster.snowflake.tables import (
    SCHEMA_CLEAN,
    SCHEMA_RAW,
    SCHEMA_SERVING,
)

if TYPE_CHECKING:
    from disaster.snowflake.writer import SnowflakeWriter


def _now() -> datetime:
    return datetime.now(UTC)


def _uid() -> str:
    return str(uuid.uuid4())


def _age_band(age: int | None) -> str | None:
    if age is None:
        return None
    if age <= 12:
        return "child"
    if age >= 75:
        return "elderly"
    return "adult"


def _sector_id(lat: float) -> str:
    if lat > 29.31:
        return "NORTH"
    if lat < 29.29:
        return "SOUTH"
    return "CENTRAL"


def emit_incident(
    writer: SnowflakeWriter,
    report: dict[str, Any],
    *,
    source_system: str = "hilo_dispatch",
) -> None:
    """Persist incident to RAW + CLEAN (+ victim rows)."""
    received = report.get("timestamp") or _now()
    if isinstance(received, str):
        received_at = received
    else:
        received_at = received.isoformat() if hasattr(received, "isoformat") else str(received)

    incident_id = str(report.get("id"))
    loc = report.get("location") or {}

    writer.write(f"{SCHEMA_RAW}.RAW_INCIDENT_SUBMISSIONS", {
        "RAW_ID": _uid(),
        "SUBMISSION_ID": incident_id,
        "SOURCE": report.get("source", "manual"),
        "RECEIVED_AT": received_at,
        "PAYLOAD": json.dumps(report),
        "_SOURCE_SYSTEM": source_system,
    })

    victims = report.get("victims") or []
    user_id = report.get("user_id") or ("simulator" if report.get("source") == "simulated" else "system")
    writer.write(f"{SCHEMA_CLEAN}.INCIDENTS", {
        "INCIDENT_ID": incident_id,
        "SUBMISSION_ID": incident_id,
        "TIMESTAMP": received_at,
        "LAT": loc.get("lat"),
        "LNG": loc.get("lng"),
        "PRIORITY_SCORE": report.get("priority_score", 0.5),
        "STATUS": report.get("status", "new"),
        "USER_ID": user_id,
        "SEVERITY": report.get("severity"),
        "SOURCE": report.get("source"),
        "LOCATION_DESCRIPTION": loc.get("description"),
        "VICTIM_COUNT": len(victims),
        "CONFIDENCE": report.get("confidence", 1.0),
        "SIM_RUN_ID": report.get("sim_run_id"),
        "FIRST_REPORTED_AT": received_at,
        "LAST_UPDATED_AT": received_at,
    })

    for ordinal, victim in enumerate(victims, start=1):
        vulns = victim.get("vulnerabilities") or []
        injuries = victim.get("injuries") or []
        writer.write(f"{SCHEMA_CLEAN}.VICTIMS", {
            "INCIDENT_ID": incident_id,
            "VICTIM_ORDINAL": ordinal,
            "AGE_BAND": _age_band(victim.get("age_estimate")),
            "VULNERABILITIES": sorted(vulns) if vulns else [],
            "INJURIES": injuries if injuries else [],
            "CONSCIOUSNESS": victim.get("consciousness", "unknown"),
            "EXTRACTED_AT": received_at,
        })


def emit_voice_call(
    writer: SnowflakeWriter,
    *,
    call_id: str,
    incident_id: str,
    transcript: str,
    model: str,
    tokens: int,
    payload: dict[str, Any] | None = None,
) -> None:
    received_at = _now().isoformat()
    writer.write(f"{SCHEMA_RAW}.RAW_VOICE_CALLS", {
        "RAW_ID": _uid(),
        "CALL_ID": call_id,
        "TRANSCRIPT": transcript,
        "TRANSCRIPT_TOKENS": tokens,
        "MODEL": model,
        "RECEIVED_AT": received_at,
        "PAYLOAD": json.dumps(payload or {"incident_id": incident_id}),
    })


def emit_responder(writer: SnowflakeWriter, unit: dict[str, Any]) -> None:
    loc = unit.get("location") or {}
    caps = unit.get("capabilities") or []
    writer.write(f"{SCHEMA_CLEAN}.RESPONDERS", {
        "RESPONDER_ID": str(unit.get("id")),
        "CALLSIGN": unit.get("callsign"),
        "RESPONDER_TYPE": unit.get("type"),
        "STATUS": unit.get("status", "idle"),
        "LAT": loc.get("lat"),
        "LNG": loc.get("lng"),
        "LOCATION_DESCRIPTION": loc.get("description"),
        "CAPABILITIES": ",".join(caps) if caps else None,
        "ASSIGNED_INCIDENT_ID": str(unit["assigned_incident_id"]) if unit.get("assigned_incident_id") else None,
        "UPDATED_AT": _now().isoformat(),
    })


def emit_dispatch_start(
    writer: SnowflakeWriter,
    *,
    dispatch_id: str,
    route_id: str | None,
    leg_id: str | None,
    responder_id: str,
    incident_id: str,
    started_by: str | None,
    started_at: datetime | str,
    solver: str,
    distance_km: float,
    eta_seconds: float,
    leg: dict[str, Any] | None,
    status: str = "active",
) -> None:
    dispatched_at = started_at.isoformat() if isinstance(started_at, datetime) else started_at

    payload = {
        "dispatch_id": dispatch_id,
        "route_id": route_id,
        "leg_id": leg_id,
        "responder_id": responder_id,
        "incident_id": incident_id,
        "solver": solver,
        "leg": leg,
    }

    writer.write(f"{SCHEMA_RAW}.RAW_DISPATCHES", {
        "RAW_ID": _uid(),
        "RESPONDER_ID": responder_id,
        "INCIDENT_ID": incident_id,
        "DISPATCHED_AT": dispatched_at,
        "DISTANCE_KM": distance_km,
        "ETA_SECONDS": eta_seconds,
        "SOLVER": solver,
        "PAYLOAD": json.dumps(payload),
    })

    writer.write(f"{SCHEMA_CLEAN}.DISPATCHES", {
        "DISPATCH_ID": dispatch_id,
        "RESPONDER_ID": responder_id,
        "INCIDENT_ID": incident_id,
        "DISPATCHED_AT": dispatched_at,
        "DISTANCE_KM": distance_km,
        "ETA_SECONDS": eta_seconds,
        "SOLVER": solver,
        "DECIDED_BY": started_by,
    })

    writer.write(f"{SCHEMA_SERVING}.RESPONDER_DISPATCHES", {
        "DISPATCH_ID": dispatch_id,
        "ROUTE_ID": route_id,
        "LEG_ID": leg_id,
        "RESPONDER_ID": responder_id,
        "INCIDENT_ID": incident_id,
        "STARTED_BY": started_by,
        "STARTED_AT": dispatched_at,
        "SOLVER": solver,
        "DISTANCE_KM": distance_km,
        "ETA_SECONDS": eta_seconds,
        "LEG": json.dumps(leg) if leg else None,
        "STATUS": status,
    })


def emit_location_ping(
    writer: SnowflakeWriter,
    *,
    responder_id: str,
    lat: float,
    lng: float,
    accuracy_m: float | None,
    timestamp: datetime | str,
    assigned_incident_id: str | None = None,
    route_id: str | None = None,
    leg_id: str | None = None,
    status: str = "idle",
    speed_mps: float | None = None,
    heading: float | None = None,
) -> None:
    reported_at = timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp

    payload = {
        "responder_id": responder_id,
        "lat": lat,
        "lng": lng,
        "accuracy_m": accuracy_m,
        "assigned_incident_id": assigned_incident_id,
    }

    writer.write(f"{SCHEMA_RAW}.RAW_RESPONDER_STATUS", {
        "RAW_ID": _uid(),
        "RESPONDER_ID": responder_id,
        "REPORTED_AT": reported_at,
        "LAT": lat,
        "LNG": lng,
        "STATUS": status,
        "PAYLOAD": json.dumps(payload),
    })

    writer.write(f"{SCHEMA_SERVING}.RESPONDER_LOCATION_PINGS", {
        "PING_ID": _uid(),
        "RESPONDER_ID": responder_id,
        "LAT": lat,
        "LNG": lng,
        "ACCURACY_M": accuracy_m,
        "TIMESTAMP": reported_at,
        "SPEED_MPS": speed_mps,
        "HEADING": heading,
        "ASSIGNED_INCIDENT_ID": assigned_incident_id,
        "ROUTE_ID": route_id,
        "LEG_ID": leg_id,
    })


def emit_arrival(writer: SnowflakeWriter, row: dict[str, Any]) -> None:
    """``row`` uses snake_case keys from responders route."""
    writer.write(f"{SCHEMA_SERVING}.RESPONDER_ARRIVALS", {
        "ASSIGNMENT_ID": row.get("assignment_id") or _uid(),
        "RESPONDER_ID": row["responder_id"],
        "CALLSIGN": row["callsign"],
        "INCIDENT_ID": row["incident_id"],
        "CLUSTER_ID": row.get("cluster_id"),
        "ARRIVAL_TIMESTAMP": row["arrival_timestamp"],
        "PING_LAT": row["ping_lat"],
        "PING_LNG": row["ping_lng"],
        "ACCURACY_M": row.get("accuracy_m"),
        "ROUTE_ID": row.get("route_id"),
        "DETECTION_METHOD": row["detection_method"],
        "DISTANCE_M": row.get("distance_m"),
    })


def emit_cortex_alert(writer: SnowflakeWriter, alert: dict[str, Any]) -> None:
    detected = alert.get("detected_at") or _now()
    detected_at = detected.isoformat() if isinstance(detected, datetime) else str(detected)

    sector = alert.get("sector")
    writer.write(f"{SCHEMA_SERVING}.CORTEX_ALERTS", {
        "ALERT_ID": _uid(),
        "ALERT_TYPE": alert.get("type", alert.get("alert_type", "cluster")),
        "SEVERITY": alert.get("severity", "warning"),
        "SECTOR_ID": sector,
        "PAYLOAD": json.dumps(alert),
        "MESSAGE": alert.get("message", ""),
        "DETECTED_AT": detected_at,
    })


def emit_route_optimization(
    writer: SnowflakeWriter,
    *,
    route_id: str,
    solver: str,
    elapsed_ms: int,
    payload: dict[str, Any],
    routing_input_id: str | None = None,
    road_access_id: str | None = None,
) -> None:
    created_at = _now().isoformat()
    routes = payload.get("routes") or {}
    input_responder_ids = list(routes.keys())
    input_incident_ids: list[str] = []
    for legs in routes.values():
        for leg in legs:
            iid = leg.get("incident_id")
            if iid:
                input_incident_ids.append(str(iid))

    writer.write(f"{SCHEMA_SERVING}.ROUTING_INPUTS", {
        "ROUTING_INPUT_ID": routing_input_id or _uid(),
        "CREATED_AT": created_at,
        "RESPONDERS": json.dumps(payload.get("responders")),
        "INCIDENTS": json.dumps(payload.get("incidents")),
        "CLUSTERS": json.dumps(payload.get("clusters")),
        "ROAD_ACCESS": json.dumps(payload.get("road_access")),
        "ACCEPTED_ASSIGNMENTS": json.dumps(payload.get("accepted_assignments")),
        "ROUTE_STOP_LIMIT": payload.get("route_stop_limit"),
        "MAX_CANDIDATES": payload.get("max_candidates"),
    })

    writer.write(f"{SCHEMA_SERVING}.ROUTE_RECOMMENDATIONS", {
        "ROUTE_ID": route_id,
        "SOLVER": solver,
        "CREATED_AT": created_at,
        "ELAPSED_MS": elapsed_ms,
        "INPUT_INCIDENT_IDS": json.dumps(sorted(set(input_incident_ids))),
        "INPUT_CLUSTER_IDS": json.dumps(payload.get("input_cluster_ids") or []),
        "INPUT_RESPONDER_IDS": json.dumps(input_responder_ids),
        "ACCEPTED_ASSIGNMENTS": json.dumps(payload.get("accepted_assignments")),
        "ROUTE_STOP_LIMIT": payload.get("route_stop_limit"),
        "MAX_CANDIDATES": payload.get("max_candidates"),
        "ROAD_ACCESS_ID": road_access_id,
        "ROAD_ACCESS_SUMMARY": json.dumps(payload.get("road_access_summary")),
        "UNASSIGNED": json.dumps(payload.get("unassigned") or []),
        "PAYLOAD": json.dumps(payload),
    })

    seq = 0
    for responder_id, legs in routes.items():
        for leg in legs:
            from_loc = leg.get("from_location") or {}
            to_loc = leg.get("to_location") or {}
            writer.write(f"{SCHEMA_SERVING}.ROUTE_LEGS", {
                "ROUTE_ID": route_id,
                "LEG_ID": leg.get("leg_id", f"{route_id}:{responder_id}:{seq}"),
                "SEQUENCE_INDEX": seq,
                "RESPONDER_ID": responder_id,
                "INCIDENT_ID": leg.get("incident_id"),
                "TARGET_ID": leg.get("target_id"),
                "TARGET_TYPE": leg.get("target_type"),
                "FROM_LAT": from_loc.get("lat"),
                "FROM_LNG": from_loc.get("lng"),
                "FROM_LOCATION_DESCRIPTION": from_loc.get("description"),
                "TO_LAT": to_loc.get("lat"),
                "TO_LNG": to_loc.get("lng"),
                "TO_LOCATION_DESCRIPTION": to_loc.get("description"),
                "DISTANCE_KM": leg.get("distance_km"),
                "ETA_SECONDS": leg.get("eta_seconds"),
                "ARRIVAL_SECONDS": leg.get("arrival_seconds"),
                "MEMBER_INCIDENT_IDS": json.dumps(leg.get("member_incident_ids") or []),
                "ROUTE_GEOMETRY": json.dumps(leg.get("route_geometry")),
                "DEGRADED": leg.get("degraded", False),
                "PROVIDER_STATUS": leg.get("provider_status"),
                "WARNINGS": json.dumps(leg.get("warnings") or []),
                "ASSIGNMENT_REASON": leg.get("assignment_reason"),
                "CREATED_AT": created_at,
            })
            seq += 1
