"""Tests for dashboard demo seed and trigger-call fixtures."""
from __future__ import annotations

import math

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.app.routes.demo import _TRANSCRIPTS, _stub_extraction
from disaster.simulator.disaster_sim import ASHEVILLE_CALLER_ANCHORS


def test_stub_trigger_call_locations_are_spread_across_asheville():
    incidents = [
        _stub_extraction(scenario, record["transcript"])
        for scenario, record in _TRANSCRIPTS.items()
    ]
    points = [(incident.location.lat, incident.location.lng) for incident in incidents]
    approved_points = {
        (latitude, longitude)
        for latitude, longitude, _description in ASHEVILLE_CALLER_ANCHORS
    }

    assert set(points) <= approved_points

    for left_index, left_point in enumerate(points):
        for right_point in points[left_index + 1:]:
            assert _haversine_km(left_point, right_point) >= 4.0


def test_legacy_west_asheville_stub_alias_uses_woodfin_land_anchor():
    incident = _stub_extraction("west_asheville_minor", "legacy transcript")

    assert (incident.location.lat, incident.location.lng) == (35.6472, -82.5607)


async def test_legacy_west_asheville_trigger_call_alias_persists_woodfin_incident():
    state = AppState()
    app = create_app(state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/demo/trigger-call?scenario=west_asheville_minor")

    assert response.status_code == 200
    assert response.json()["scenario"] == "woodfin_minor"

    incidents = await state.incidents.list()
    assert len(incidents) == 1
    assert (incidents[0].location.lat, incidents[0].location.lng) == (35.6472, -82.5607)


def _haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_latitude, left_longitude = left
    right_latitude, right_longitude = right
    earth_radius_km = 6371.0
    latitude_delta = math.radians(right_latitude - left_latitude)
    longitude_delta = math.radians(right_longitude - left_longitude)
    a = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(math.radians(left_latitude))
        * math.cos(math.radians(right_latitude))
        * math.sin(longitude_delta / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
