"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import type {
  IncidentReport,
  RoadAccessFeatureCollection,
  RoadAccessSummary,
  RouteLeg,
  RoutingResponse,
  ResponderUnit,
} from "@/lib/types";
import { SEVERITY_VISUAL } from "@/lib/severity";

interface Props {
  incidents: IncidentReport[];
  responders: ResponderUnit[];
  routingResponse: RoutingResponse | null;
  flashing: Set<string>;
  onSelect: (id: string) => void;
}

// Galveston, Texas demo center
const TEXAS_DEMO_CENTER = { lng: -94.7977, lat: 29.3013, zoom: 12.7 };

const TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

function isRoadAccessFeatureCollection(
  roadAccess: RoadAccessSummary | RoadAccessFeatureCollection | null | undefined
): roadAccess is RoadAccessFeatureCollection {
  return roadAccess?.type === "FeatureCollection" && Array.isArray(roadAccess.features);
}

function getRoadAccessFeatureCollection(
  roadAccess: RoadAccessSummary | RoadAccessFeatureCollection | null | undefined
): RoadAccessFeatureCollection {
  if (isRoadAccessFeatureCollection(roadAccess)) return roadAccess;
  if (roadAccess?.feature_collection) return roadAccess.feature_collection;
  if (roadAccess?.features) {
    return { type: "FeatureCollection", features: roadAccess.features };
  }
  return { type: "FeatureCollection", features: [] };
}

function getRouteCoordinates(leg: RouteLeg): [number, number][] {
  if (leg.route_geometry?.coordinates?.length) return leg.route_geometry.coordinates;
  return [
    [leg.from_location.lng, leg.from_location.lat],
    [leg.to_location.lng, leg.to_location.lat],
  ];
}

export function MapView({ incidents, responders, routingResponse, flashing, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [initError, setInitError] = useState<string | null>(null);

  // ── init ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    if (!TOKEN) {
      console.warn("NEXT_PUBLIC_MAPBOX_TOKEN missing — map will not render");
      return;
    }
    mapboxgl.accessToken = TOKEN;
    let map: mapboxgl.Map;
    try {
      map = new mapboxgl.Map({
        container: containerRef.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [TEXAS_DEMO_CENTER.lng, TEXAS_DEMO_CENTER.lat],
        zoom: TEXAS_DEMO_CENTER.zoom,
        attributionControl: false,
      });
    } catch (err) {
      // Most common cause: WebGL unavailable (headless browser, hardware accel off,
      // very old browser). Never crash the rest of the dashboard.
      const msg = err instanceof Error ? err.message : String(err);
      console.error("Map init failed:", msg);
      setInitError(msg);
      return;
    }
    mapRef.current = map;
    map.on("error", (e) => {
      console.error("Mapbox error:", e?.error?.message ?? e);
    });

    map.on("load", () => {
      // Hide noisy street/POI labels per Pass 7 issue 7.1
      const labelLayers = ["road-label", "poi-label", "settlement-major-label", "settlement-minor-label"];
      for (const id of labelLayers) {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
      }

      map.addSource("road-access", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "road-access-fill",
        type: "fill",
        source: "road-access",
        paint: {
          "fill-color": [
            "match", ["get", "road_status"],
            "confirmed_closed", "#EF4444",
            "restricted", "#F97316",
            "limited", "#FACC15",
            "#64748B",
          ],
          "fill-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "road-access-outline",
        type: "line",
        source: "road-access",
        paint: {
          "line-color": [
            "match", ["get", "road_status"],
            "confirmed_closed", "#FCA5A5",
            "restricted", "#FDBA74",
            "limited", "#FDE68A",
            "#CBD5E1",
          ],
          "line-width": 1.5,
          "line-opacity": 0.75,
        },
      });

      map.addSource("responder-routes", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "responder-route-lines",
        type: "line",
        source: "responder-routes",
        layout: {
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": [
            "case",
            ["boolean", ["get", "degraded"], false], "#F97316",
            "#38BDF8",
          ],
          "line-width": [
            "case",
            ["boolean", ["get", "degraded"], false], 2.5,
            3.5,
          ],
          "line-opacity": 0.82,
          "line-dasharray": [
            "case",
            ["boolean", ["get", "degraded"], false], ["literal", [1.5, 1.2]],
            ["literal", [1, 0]],
          ],
        },
      });

      // P1 #6: cluster: true on the incident source
      map.addSource("incidents", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterMaxZoom: 14,
        clusterRadius: 50,
      });

      // Cluster circles colored by majority severity (Pass 7 issue 7.7)
      map.addLayer({
        id: "incident-clusters",
        type: "circle",
        source: "incidents",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": [
            "step", ["get", "point_count"],
            "#FACC15", 10, "#F97316", 30, "#EF4444",
          ],
          "circle-radius": ["step", ["get", "point_count"], 16, 10, 22, 30, 28],
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#0B0F19",
        },
      });
      map.addLayer({
        id: "incident-cluster-count",
        type: "symbol",
        source: "incidents",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-size": 12,
        },
        paint: { "text-color": "#0B0F19" },
      });

      // Unclustered: severity-colored circles
      map.addLayer({
        id: "incident-unclustered",
        type: "circle",
        source: "incidents",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "match", ["get", "severity"],
            "Immediate", SEVERITY_VISUAL.Immediate.color,
            "Delayed", SEVERITY_VISUAL.Delayed.color,
            "Minor", SEVERITY_VISUAL.Minor.color,
            "Deceased", SEVERITY_VISUAL.Deceased.color,
            "#94A3B8",
          ],
          "circle-radius": [
            "case",
            ["boolean", ["get", "flashing"], false], 12, 8,
          ],
          "circle-stroke-width": [
            "case",
            ["boolean", ["get", "flashing"], false], 3, 1.5,
          ],
          "circle-stroke-color": "#FFFFFF",
          "circle-opacity": [
            "case",
            ["boolean", ["get", "flashing"], false], 0.95, 0.85,
          ],
        },
      });

      // Responders layer
      map.addSource("responders", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "responder-units",
        type: "circle",
        source: "responders",
        paint: {
          "circle-color": [
            "match", ["get", "status"],
            "on_scene", "#22C55E",
            "en_route", "#38BDF8",
            "assigned", "#FACC15",
            "out_of_service", "#64748B",
            "#60A5FA",
          ],
          "circle-radius": [
            "case",
            ["==", ["get", "status"], "on_scene"], 7,
            6,
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#FFFFFF",
        },
      });
      map.addLayer({
        id: "responder-labels",
        type: "symbol",
        source: "responders",
        layout: {
          "text-field": ["get", "callsign"],
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-offset": [0, -1.2],
          "text-size": 11,
        },
        paint: { "text-color": "#F1F5F9", "text-halo-color": "#0B0F19", "text-halo-width": 1.5 },
      });

      // Click handler
      map.on("click", "incident-unclustered", (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const id = feature.properties?.id as string;
        if (id) onSelect(id);
      });
      map.on("mouseenter", "incident-unclustered", () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", "incident-unclustered", () => map.getCanvas().style.cursor = "");
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── data updates ─────────────────────────────────────────────────────────
  const incidentsGeoJSON = useMemo(() => ({
    type: "FeatureCollection" as const,
    features: incidents.map((i) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [i.location.lng, i.location.lat] },
      properties: {
        id: i.id,
        severity: i.severity,
        priority_score: i.priority_score,
        flashing: flashing.has(i.id),
      },
    })),
  }), [incidents, flashing]);

  const respondersGeoJSON = useMemo(() => ({
    type: "FeatureCollection" as const,
    features: responders.map((r) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [r.location.lng, r.location.lat] },
      properties: { id: r.id, callsign: r.callsign, type: r.type, status: r.status },
    })),
  }), [responders]);

  const routeLinesGeoJSON = useMemo(() => ({
    type: "FeatureCollection" as const,
    features: Object.entries(routingResponse?.routes ?? {}).flatMap(([responderId, legs]) =>
      legs.map((leg, index) => ({
        type: "Feature" as const,
        geometry: {
          type: "LineString" as const,
          coordinates: getRouteCoordinates(leg),
        },
        properties: {
          responder_id: responderId,
          leg_index: index,
          target_id: leg.target_id ?? leg.incident_id ?? null,
          target_type: leg.target_type ?? (leg.incident_id ? "incident" : null),
          incident_id: leg.incident_id ?? null,
          distance_km: leg.distance_km,
          eta_seconds: leg.eta_seconds,
          arrival_seconds: leg.arrival_seconds ?? null,
          degraded: leg.degraded ?? false,
          provider_status: leg.provider_status ?? null,
          assignment_reason: leg.assignment_reason ?? null,
        },
      }))
    ),
  }), [routingResponse]);

  const roadAccessGeoJSON = useMemo(
    () => getRoadAccessFeatureCollection(routingResponse?.road_access),
    [routingResponse]
  );

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("incidents") as mapboxgl.GeoJSONSource | undefined;
    if (src) src.setData(incidentsGeoJSON as any);
  }, [incidentsGeoJSON]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("responders") as mapboxgl.GeoJSONSource | undefined;
    if (src) src.setData(respondersGeoJSON as any);
  }, [respondersGeoJSON]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("responder-routes") as mapboxgl.GeoJSONSource | undefined;
    if (src) src.setData(routeLinesGeoJSON as any);
  }, [routeLinesGeoJSON]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("road-access") as mapboxgl.GeoJSONSource | undefined;
    if (src) src.setData(roadAccessGeoJSON as any);
  }, [roadAccessGeoJSON]);

  if (!TOKEN) {
    return (
      <div className="flex h-full items-center justify-center bg-bg-panel text-fg-muted">
        <div className="text-center">
          <div className="text-fg-secondary">Mapbox token missing</div>
          <div className="mono text-xs mt-2">Set NEXT_PUBLIC_MAPBOX_TOKEN in frontend/.env.local</div>
        </div>
      </div>
    );
  }

  if (initError) {
    return (
      <div className="flex h-full items-center justify-center bg-bg-panel text-fg-muted">
        <div className="max-w-md text-center px-6">
          <div className="text-fg-secondary">Map unavailable</div>
          <div className="mono text-xs mt-2 text-status-warn break-words">{initError}</div>
          <div className="mono text-xs mt-3 text-fg-muted">
            Dashboard continues to function. Check WebGL support in your browser.
          </div>
        </div>
      </div>
    );
  }

  return <div ref={containerRef} className="h-full w-full" />;
}
