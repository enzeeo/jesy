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

SIMULATED_ROAD_BLOCK_FEATURES: list[dict[str, Any]] = [
    {
        "type": "Feature",
        "properties": {
            "road_status": "likely_flooded",
            "label": "Broadway underpass flood",
            "confidence": 0.81,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-94.8180, 29.2976],
                [-94.8148, 29.2976],
                [-94.8148, 29.3001],
                [-94.8180, 29.3001],
                [-94.8180, 29.2976],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "confirmed_closed",
            "label": "61st Street debris closure",
            "confidence": 0.86,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-94.8340, 29.2769],
                [-94.8308, 29.2769],
                [-94.8308, 29.2795],
                [-94.8340, 29.2795],
                [-94.8340, 29.2769],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "likely_flooded",
            "label": "East End standing water",
            "confidence": 0.78,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-94.7654, 29.3157],
                [-94.7622, 29.3157],
                [-94.7622, 29.3184],
                [-94.7654, 29.3184],
                [-94.7654, 29.3157],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "confirmed_closed",
            "label": "Market Street washout",
            "confidence": 0.84,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-94.7998, 29.3040],
                [-94.7965, 29.3040],
                [-94.7965, 29.3066],
                [-94.7998, 29.3066],
                [-94.7998, 29.3040],
            ]],
        },
    },
]


def demo_road_access() -> dict[str, Any]:
    """Return an isolated copy of the default demo blocked-road GeoJSON."""

    return deepcopy(DEMO_ROAD_ACCESS)


def demo_road_access_with_simulated_blocks(block_count: int) -> dict[str, Any]:
    """Return demo road access with staged simulator road blocks appended."""

    feature_collection = demo_road_access()
    feature_collection["features"].extend(deepcopy(SIMULATED_ROAD_BLOCK_FEATURES[:max(0, block_count)]))
    return feature_collection


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
