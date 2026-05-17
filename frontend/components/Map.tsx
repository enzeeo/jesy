"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import type {
  BlockedRoadsResponse,
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
  roadAccess?: RoadAccessSummary | BlockedRoadsResponse | RoadAccessFeatureCollection | null;
  acceptedRoutes: AcceptedRouteLine[];
  acceptedRouteKeys: Set<string>;
  flashing: Set<string>;
  onSelect: (id: string) => void;
}

interface AcceptedRouteLine {
  routeId: string;
  legId: string;
  responderId: string;
  leg: RouteLeg;
}

// Hilo Bay demo center
const HILO_DEMO_CENTER = { lng: -155.0900, lat: 19.7297, zoom: 13.2 };

const TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

function isRoadAccessFeatureCollection(
  roadAccess: RoadAccessSummary | BlockedRoadsResponse | RoadAccessFeatureCollection | null | undefined
): roadAccess is RoadAccessFeatureCollection {
  return Boolean(
    roadAccess
    && "type" in roadAccess
    && roadAccess.type === "FeatureCollection"
    && "features" in roadAccess
    && Array.isArray(roadAccess.features)
  );
}

function getRoadAccessFeatureCollection(
  roadAccess: RoadAccessSummary | BlockedRoadsResponse | RoadAccessFeatureCollection | null | undefined
): RoadAccessFeatureCollection {
  if (isRoadAccessFeatureCollection(roadAccess)) return roadAccess;
  if (roadAccess?.feature_collection) return roadAccess.feature_collection;
  if (roadAccess && "features" in roadAccess && roadAccess.features) {
    return { type: "FeatureCollection", features: roadAccess.features };
  }
  return { type: "FeatureCollection", features: [] };
}

function normalizeRoadAccessFeatureCollection(
  featureCollection: RoadAccessFeatureCollection
): RoadAccessFeatureCollection {
  return {
    type: "FeatureCollection",
    features: featureCollection.features.map((feature) => {
      const properties = feature.properties ?? {};
      const roadStatus = properties.road_status ?? properties.status ?? null;
      return {
        ...feature,
        properties: {
          ...properties,
          road_status: roadStatus,
        },
      };
    }),
  };
}

function getRouteCoordinates(leg: RouteLeg): [number, number][] {
  if (leg.route_geometry?.coordinates?.length) return leg.route_geometry.coordinates;
  return [
    [leg.from_location.lng, leg.from_location.lat],
    [leg.to_location.lng, leg.to_location.lat],
  ];
}

function routeFeatureKey(routeId: string | null | undefined, leg: RouteLeg): string | null {
  if (!routeId || !leg.leg_id) return null;
  return `${routeId}:${leg.leg_id}`;
}

function getLegIncidentId(leg: RouteLeg): string | null {
  return leg.incident_id ?? (leg.target_type === "incident" ? leg.target_id ?? null : null);
}

function acceptedRouteIncidentKey(route: AcceptedRouteLine): string | null {
  const incidentId = getLegIncidentId(route.leg);
  if (!incidentId) return null;
  return `${route.responderId}:${incidentId}`;
}

function isCurrentOnSceneAssignment(responder: ResponderUnit | undefined, leg: RouteLeg): boolean {
  if (responder?.status !== "on_scene" || !responder.assigned_incident_id) return false;
  return getLegIncidentId(leg) === responder.assigned_incident_id;
}

export function MapView({
  incidents,
  responders,
  routingResponse,
  roadAccess,
  acceptedRoutes,
  acceptedRouteKeys,
  flashing,
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [initError, setInitError] = useState<string | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

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
        center: [HILO_DEMO_CENTER.lng, HILO_DEMO_CENTER.lat],
        zoom: HILO_DEMO_CENTER.zoom,
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
        filter: [
          "match", ["geometry-type"],
          ["Polygon", "MultiPolygon"], true,
          false,
        ],
        paint: {
          "fill-color": [
            "match", ["get", "road_status"],
            "confirmed_closed", "#EF4444",
            "likely_flooded", "#EF4444",
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
            "likely_flooded", "#FCA5A5",
            "restricted", "#FDBA74",
            "limited", "#FDE68A",
            "#CBD5E1",
          ],
          "line-width": 1.5,
          "line-opacity": 0.75,
        },
      });
      map.addLayer({
        id: "road-access-blocked-roads",
        type: "line",
        source: "road-access",
        filter: [
          "match", ["geometry-type"],
          ["LineString", "MultiLineString"], true,
          false,
        ],
        layout: {
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": [
            "match", ["get", "road_status"],
            "confirmed_closed", "#EF4444",
            "likely_flooded", "#EF4444",
            "restricted", "#F97316",
            "limited", "#FACC15",
            "#EF4444",
          ],
          "line-width": [
            "case",
            ["match", ["get", "road_status"], ["confirmed_closed", "likely_flooded"], true, false], 5,
            3.5,
          ],
          "line-opacity": 0.95,
        },
      });
      map.addLayer({
        id: "road-access-labels",
        type: "symbol",
        source: "road-access",
        filter: ["has", "label"],
        layout: {
          "text-field": ["get", "label"],
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-size": 11,
          "text-offset": [0, 1.1],
          "text-anchor": "top",
          "text-allow-overlap": false,
        },
        paint: {
          "text-color": "#FCA5A5",
          "text-halo-color": "#0B0F19",
          "text-halo-width": 1.5,
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
            ["boolean", ["get", "accepted"], false], "#38BDF8",
            ["boolean", ["get", "recommended"], false], "#A855F7",
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
      setMapLoaded(true);
    });

    return () => {
      setMapLoaded(false);
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

  const routeLinesGeoJSON = useMemo(() => {
    const acceptedRoutesByKey = new Map(
      acceptedRoutes.map((route) => [`${route.routeId}:${route.legId}`, route])
    );
    const acceptedRoutesByResponderIncident = new Map<string, AcceptedRouteLine>();
    for (const route of acceptedRoutes) {
      const incidentKey = acceptedRouteIncidentKey(route);
      if (incidentKey) acceptedRoutesByResponderIncident.set(incidentKey, route);
    }

    const renderedAcceptedKeys = new Set<string>();
    const features = Object.entries(routingResponse?.routes ?? {}).flatMap(([responderId, legs]) => {
      const responder = responders.find((unit) => unit.id === responderId);
      return legs.flatMap((leg, index) => {
        if (isCurrentOnSceneAssignment(responder, leg)) return [];
        const routeKey = routeFeatureKey(routingResponse?.route_id, leg);
        const incidentId = getLegIncidentId(leg);
        const incidentKey = incidentId ? `${responderId}:${incidentId}` : null;
        const acceptedRoute = (routeKey ? acceptedRoutesByKey.get(routeKey) : undefined)
          ?? (incidentKey ? acceptedRoutesByResponderIncident.get(incidentKey) : undefined);
        const displayLeg = acceptedRoute?.leg ?? leg;
        const accepted = Boolean(acceptedRoute) || (routeKey ? acceptedRouteKeys.has(routeKey) : false);
        if (acceptedRoute) renderedAcceptedKeys.add(`${acceptedRoute.routeId}:${acceptedRoute.legId}`);
        return [{
          type: "Feature" as const,
          geometry: {
            type: "LineString" as const,
            coordinates: getRouteCoordinates(displayLeg),
          },
          properties: {
            route_key: routeKey,
            accepted,
            recommended: !accepted,
            responder_id: responderId,
            leg_index: index,
            target_id: displayLeg.target_id ?? displayLeg.incident_id ?? null,
            target_type: displayLeg.target_type ?? (displayLeg.incident_id ? "incident" : null),
            incident_id: displayLeg.incident_id ?? null,
            distance_km: displayLeg.distance_km,
            eta_seconds: displayLeg.eta_seconds,
            arrival_seconds: displayLeg.arrival_seconds ?? null,
            degraded: displayLeg.degraded ?? false,
            provider_status: displayLeg.provider_status ?? null,
            assignment_reason: displayLeg.assignment_reason ?? null,
          },
        }];
      });
    });

    for (const acceptedRoute of acceptedRoutes) {
      const responder = responders.find((unit) => unit.id === acceptedRoute.responderId);
      const acceptedKey = `${acceptedRoute.routeId}:${acceptedRoute.legId}`;
      if (renderedAcceptedKeys.has(acceptedKey)) continue;
      const incidentId = getLegIncidentId(acceptedRoute.leg);
      if (isCurrentOnSceneAssignment(responder, acceptedRoute.leg)) continue;
      features.push({
        type: "Feature" as const,
        geometry: {
          type: "LineString" as const,
          coordinates: getRouteCoordinates(acceptedRoute.leg),
        },
        properties: {
          route_key: acceptedKey,
          accepted: true,
          recommended: false,
          responder_id: acceptedRoute.responderId,
          leg_index: 0,
          target_id: acceptedRoute.leg.target_id ?? acceptedRoute.leg.incident_id ?? null,
          target_type: acceptedRoute.leg.target_type ?? (incidentId ? "incident" : null),
          incident_id: incidentId,
          distance_km: acceptedRoute.leg.distance_km,
          eta_seconds: acceptedRoute.leg.eta_seconds,
          arrival_seconds: acceptedRoute.leg.arrival_seconds ?? null,
          degraded: acceptedRoute.leg.degraded ?? false,
          provider_status: acceptedRoute.leg.provider_status ?? null,
          assignment_reason: acceptedRoute.leg.assignment_reason ?? null,
        },
      });
    }

    return {
      type: "FeatureCollection" as const,
      features,
    };
  }, [acceptedRouteKeys, acceptedRoutes, responders, routingResponse]);

  const roadAccessGeoJSON = useMemo(
    () => normalizeRoadAccessFeatureCollection(
      getRoadAccessFeatureCollection(roadAccess ?? routingResponse?.road_access)
    ),
    [roadAccess, routingResponse]
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
  }, [mapLoaded, roadAccessGeoJSON]);

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
