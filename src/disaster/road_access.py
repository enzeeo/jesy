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
                "label": "Bayfront Hwy flood closure",
                "confidence": 0.92,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-155.0924, 19.7244],
                    [-155.0887, 19.7244],
                    [-155.0887, 19.7274],
                    [-155.0924, 19.7274],
                    [-155.0924, 19.7244],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "road_status": "confirmed_closed",
                "label": "Kamehameha Ave/Mamo St closure",
                "confidence": 0.88,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-155.0899, 19.7259],
                    [-155.0864, 19.7259],
                    [-155.0864, 19.7290],
                    [-155.0899, 19.7290],
                    [-155.0899, 19.7259],
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
            "label": "Banyan Drive debris closure",
            "confidence": 0.81,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-155.0762, 19.7247],
                [-155.0728, 19.7247],
                [-155.0728, 19.7281],
                [-155.0762, 19.7281],
                [-155.0762, 19.7247],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "confirmed_closed",
            "label": "Wailoa Bridge standing water",
            "confidence": 0.86,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-155.0840, 19.7219],
                [-155.0806, 19.7219],
                [-155.0806, 19.7250],
                [-155.0840, 19.7250],
                [-155.0840, 19.7219],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "likely_flooded",
            "label": "Hilo Harbor access restriction",
            "confidence": 0.78,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-155.0958, 19.7318],
                [-155.0919, 19.7318],
                [-155.0919, 19.7352],
                [-155.0958, 19.7352],
                [-155.0958, 19.7318],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "confirmed_closed",
            "label": "Reeds Bay washout",
            "confidence": 0.84,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-155.0749, 19.7288],
                [-155.0711, 19.7288],
                [-155.0711, 19.7322],
                [-155.0749, 19.7322],
                [-155.0749, 19.7288],
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
