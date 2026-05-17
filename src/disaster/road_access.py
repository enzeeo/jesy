"""Shared demo road-access state for routing and map rendering."""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

HARD_BLOCKED_ROAD_STATUSES = {"confirmed_closed", "likely_flooded"}
ASHEVILLE_ROAD_ACCESS_SOURCE = "helene_curated_asheville"
ASHEVILLE_ROAD_ACCESS_VERSION = "helene-2024-asheville-v1"
ASHEVILLE_ROAD_ACCESS_LOADED_AT = "2024-10-05T00:00:00+00:00"
ASHEVILLE_ROAD_ACCESS_ID = "road-access-helene-asheville-v1"
HELENE_ARCGIS_SOURCE = "helene_arcgis_cached"
HELENE_ARCGIS_VERSION = "helene-2024-arcgis-asheville-v1"
MAX_IMPORTED_FLOOD_FEATURES = 8
HELENE_SOURCE_URLS = [
    "https://services2.arcgis.com/C8EMgrsFcRFL6LrL/ArcGIS/rest/services/HeleneOct05/FeatureServer",
    "https://www.climate.gov/news-features/event-tracker/hurricane-helenes-extreme-rainfall-and-catastrophic-inland-flooding",
    "https://www.ncdot.gov/news/press-releases/Pages/2024/2024-09-28-avoid-traveling-western-nc-recovery-helene.aspx",
    "https://www.usace.army.mil/Helene/",
]
HELENE_NWM_QUERY_URL = (
    "https://services2.arcgis.com/C8EMgrsFcRFL6LrL/ArcGIS/rest/services/"
    "HeleneOct05/FeatureServer/0/query"
)

DEMO_ROAD_ACCESS: dict[str, Any] = {
    "type": "FeatureCollection",
    "metadata": {
        "road_access_id": ASHEVILLE_ROAD_ACCESS_ID,
        "source": ASHEVILLE_ROAD_ACCESS_SOURCE,
        "version": ASHEVILLE_ROAD_ACCESS_VERSION,
        "loaded_at": ASHEVILLE_ROAD_ACCESS_LOADED_AT,
        "source_urls": HELENE_SOURCE_URLS,
    },
    "features": [
        {
            "type": "Feature",
            "properties": {
                "road_status": "confirmed_closed",
                "label": "River Arts District flood zone",
                "confidence": 0.91,
                "feature_id": "asheville-river-arts-flood",
                "hazard": "french_broad_flooding",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-82.5840, 35.5740],
                    [-82.5620, 35.5740],
                    [-82.5620, 35.5890],
                    [-82.5840, 35.5890],
                    [-82.5840, 35.5740],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "road_status": "likely_flooded",
                "label": "Biltmore Village Swannanoa flood zone",
                "confidence": 0.89,
                "feature_id": "asheville-biltmore-swannanoa-flood",
                "hazard": "swannanoa_river_flooding",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-82.5525, 35.5555],
                    [-82.5295, 35.5555],
                    [-82.5295, 35.5697],
                    [-82.5525, 35.5697],
                    [-82.5525, 35.5555],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "road_status": "likely_flooded",
                "label": "Hominy Creek flood zone",
                "confidence": 0.86,
                "feature_id": "asheville-hominy-creek-flood",
                "hazard": "hominy_creek_flooding",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-82.6165, 35.5575],
                    [-82.5960, 35.5575],
                    [-82.5960, 35.5725],
                    [-82.6165, 35.5725],
                    [-82.6165, 35.5575],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "road_status": "confirmed_closed",
                "label": "I-40 east washout corridor",
                "confidence": 0.84,
                "feature_id": "asheville-i40-east-washout",
                "hazard": "helene_road_washout",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-82.5170, 35.5630],
                    [-82.4910, 35.5630],
                    [-82.4910, 35.5770],
                    [-82.5170, 35.5770],
                    [-82.5170, 35.5630],
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
            "label": "Riverside Drive debris closure",
            "confidence": 0.82,
            "feature_id": "asheville-riverside-debris",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-82.5968, 35.6070],
                [-82.5864, 35.6070],
                [-82.5864, 35.6165],
                [-82.5968, 35.6165],
                [-82.5968, 35.6070],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "confirmed_closed",
            "label": "Tunnel Road underpass flood",
            "confidence": 0.86,
            "feature_id": "asheville-tunnel-road-underpass",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-82.5380, 35.5835],
                [-82.5255, 35.5835],
                [-82.5255, 35.5905],
                [-82.5380, 35.5905],
                [-82.5380, 35.5835],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "likely_flooded",
            "label": "Swannanoa River Road bridge approach",
            "confidence": 0.78,
            "feature_id": "asheville-swannanoa-river-road-bridge",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-82.4885, 35.5965],
                [-82.4755, 35.5965],
                [-82.4755, 35.6050],
                [-82.4885, 35.6050],
                [-82.4885, 35.5965],
            ]],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "road_status": "confirmed_closed",
            "label": "Amboy Road limited access",
            "confidence": 0.84,
            "feature_id": "asheville-amboy-road-limited",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-82.5900, 35.5590],
                [-82.5785, 35.5590],
                [-82.5785, 35.5680],
                [-82.5900, 35.5680],
                [-82.5900, 35.5590],
            ]],
        },
    },
]


def demo_road_access() -> dict[str, Any]:
    """Return an isolated copy of the default demo blocked-road GeoJSON."""

    return deepcopy(DEMO_ROAD_ACCESS)


def load_helene_cached_road_access(*, refresh: bool = False) -> dict[str, Any]:
    """Load the Asheville Helene road-access snapshot, refreshing ArcGIS only on request."""

    if not refresh:
        cached = _read_cached_snapshot()
        if cached is not None:
            return cached
        return demo_road_access()

    try:
        feature_collection = _fetch_helene_arcgis_snapshot()
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
        return demo_road_access()
    _write_cached_snapshot(feature_collection)
    return feature_collection


def demo_road_access_with_simulated_blocks(block_count: int) -> dict[str, Any]:
    """Return demo road access with staged simulator road blocks appended."""

    feature_collection = demo_road_access()
    feature_collection["features"].extend(deepcopy(SIMULATED_ROAD_BLOCK_FEATURES[:max(0, block_count)]))
    if block_count > 0:
        metadata = dict(feature_collection.get("metadata", {}))
        metadata["source"] = f"{ASHEVILLE_ROAD_ACCESS_SOURCE}_simulated_updates"
        metadata["version"] = f"{ASHEVILLE_ROAD_ACCESS_VERSION}+staged-{block_count}"
        metadata["road_access_id"] = stable_road_access_id(feature_collection, metadata=metadata)
        feature_collection["metadata"] = metadata
    return feature_collection


def stable_road_access_id(
    feature_collection: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Return a deterministic ID for a compact road-access FeatureCollection."""

    effective_metadata = metadata or _metadata(feature_collection)
    canonical = {
        "source": effective_metadata.get("source"),
        "version": effective_metadata.get("version"),
        "features": feature_collection.get("features", []),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"road-access-{digest[:16]}"


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

    metadata = _metadata(isolated_feature_collection)
    return {
        "blocked_count": len(blocked_roads),
        "hard_avoid_count": hard_avoid_count,
        "blocked_roads": blocked_roads,
        "feature_collection": isolated_feature_collection,
        "road_access_id": metadata.get("road_access_id"),
        "source": metadata.get("source"),
        "version": metadata.get("version"),
        "loaded_at": metadata.get("loaded_at"),
    }


def _metadata(feature_collection: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = feature_collection.get("metadata")
    return raw_metadata if isinstance(raw_metadata, dict) else {}


def _cache_path() -> Path:
    raw_path = os.environ.get("HELENE_ROAD_ACCESS_CACHE")
    if raw_path:
        return Path(raw_path)
    return Path(".cache/helene_road_access.geojson")


def _read_cached_snapshot() -> dict[str, Any] | None:
    path = _cache_path()
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        return None
    return payload


def _write_cached_snapshot(feature_collection: dict[str, Any]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(feature_collection, handle, sort_keys=True, separators=(",", ":"))


def _fetch_helene_arcgis_snapshot() -> dict[str, Any]:
    query_urls = _arcgis_query_urls()
    last_error: Exception | None = None
    for url in query_urls:
        try:
            response = httpx.get(
                url,
                params={
                    "where": "1=1",
                    "outFields": "*",
                    "returnGeometry": "true",
                    "f": "geojson",
                    "outSR": "4326",
                    "geometry": "-82.75,35.45,-82.35,35.75",
                    "geometryType": "esriGeometryEnvelope",
                    "spatialRel": "esriSpatialRelIntersects",
                    "resultRecordCount": str(MAX_IMPORTED_FLOOD_FEATURES),
                },
                timeout=5.0,
            )
            response.raise_for_status()
            return _normalize_arcgis_feature_collection(response.json(), source_url=url)
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as caught:
            last_error = caught
    if last_error is not None:
        raise last_error
    raise ValueError("no Helene ArcGIS query URLs configured")


def _arcgis_query_urls() -> list[str]:
    urls = []
    if os.environ.get("HELENE_ARCGIS_QUERY_URL"):
        urls.append(os.environ["HELENE_ARCGIS_QUERY_URL"])
    urls.append(HELENE_NWM_QUERY_URL)
    return urls


def _normalize_arcgis_feature_collection(payload: dict[str, Any], *, source_url: str) -> dict[str, Any]:
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("ArcGIS response did not contain GeoJSON features")

    features: list[dict[str, Any]] = []
    for index, feature in enumerate(raw_features[:MAX_IMPORTED_FLOOD_FEATURES], start=1):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        features.append({
            "type": "Feature",
            "properties": {
                **properties,
                "road_status": "likely_flooded",
                "label": properties.get("label") or f"Helene imported flood extent {index}",
                "confidence": properties.get("confidence", 0.72),
                "feature_id": properties.get("feature_id") or f"helene-arcgis-{index:03d}",
            },
            "geometry": _round_geometry(geometry),
        })

    if not features:
        raise ValueError("ArcGIS response had no usable Asheville flood polygons")

    feature_collection = {
        "type": "FeatureCollection",
        "metadata": {
            "source": HELENE_ARCGIS_SOURCE,
            "version": HELENE_ARCGIS_VERSION,
            "loaded_at": datetime.now(UTC).isoformat(),
            "source_urls": [source_url, *HELENE_SOURCE_URLS],
        },
        "features": features,
    }
    feature_collection["metadata"]["road_access_id"] = stable_road_access_id(feature_collection)
    return feature_collection


def _round_geometry(geometry: dict[str, Any], precision: int = 5) -> dict[str, Any]:
    return {
        "type": geometry.get("type"),
        "coordinates": _round_coordinates(geometry.get("coordinates"), precision),
    }


def _round_coordinates(value: Any, precision: int) -> Any:
    if isinstance(value, list):
        return [_round_coordinates(item, precision) for item in value]
    if isinstance(value, float):
        return round(value, precision)
    return value
