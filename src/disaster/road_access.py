"""Shared demo road-access state for routing and map rendering."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

HARD_BLOCKED_ROAD_STATUSES = {"confirmed_closed", "likely_flooded"}

DEMO_ROAD_ACCESS: dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "road_status": "confirmed_closed",
                "label": "Harbor flood closure",
                "confidence": 0.92,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-94.7899, 29.3097],
                    [-94.7873, 29.3097],
                    [-94.7873, 29.3123],
                    [-94.7899, 29.3123],
                    [-94.7899, 29.3097],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "road_status": "confirmed_closed",
                "label": "Seawall washout",
                "confidence": 0.88,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-94.8057, 29.2796],
                    [-94.8012, 29.2796],
                    [-94.8012, 29.2824],
                    [-94.8057, 29.2824],
                    [-94.8057, 29.2796],
                ]],
            },
        },
    ],
}


def demo_road_access() -> dict[str, Any]:
    """Return an isolated copy of the default demo blocked-road GeoJSON."""

    return deepcopy(DEMO_ROAD_ACCESS)


def blocked_roads_stub(feature_collection: dict[str, Any]) -> dict[str, Any]:
    """Return map-ready blocked-road stub data from road-access GeoJSON."""

    isolated_feature_collection = deepcopy(feature_collection)
    raw_features = isolated_feature_collection.get("features", [])
    features = raw_features if isinstance(raw_features, list) else []
    blocked_roads: list[dict[str, Any]] = []
    hard_avoid_count = 0

    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        road_status = str(properties.get("road_status") or properties.get("status") or "").strip().lower()
        if not road_status:
            continue
        if road_status in HARD_BLOCKED_ROAD_STATUSES:
            hard_avoid_count += 1
        blocked_roads.append({
            "label": properties.get("label") or "Blocked road",
            "road_status": road_status,
            "confidence": properties.get("confidence"),
            "geometry": deepcopy(feature.get("geometry")),
        })

    return {
        "blocked_count": len(blocked_roads),
        "hard_avoid_count": hard_avoid_count,
        "blocked_roads": blocked_roads,
        "feature_collection": isolated_feature_collection,
    }
