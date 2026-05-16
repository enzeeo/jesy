"use client";
import { useEffect, useMemo, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import type { IncidentReport, ResponderUnit } from "@/lib/types";
import { SEVERITY_VISUAL } from "@/lib/severity";

interface Props {
  incidents: IncidentReport[];
  responders: ResponderUnit[];
  flashing: Set<string>;
  onSelect: (id: string) => void;
}

// Hilo Bay center
const HILO = { lng: -155.0900, lat: 19.7297, zoom: 13.5 };

const TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

export function MapView({ incidents, responders, flashing, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

  // ── init ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    if (!TOKEN) {
      console.warn("NEXT_PUBLIC_MAPBOX_TOKEN missing — map will not render");
      return;
    }
    mapboxgl.accessToken = TOKEN;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: "mapbox://styles/mapbox/dark-v11",
      center: [HILO.lng, HILO.lat],
      zoom: HILO.zoom,
      attributionControl: false,
    });
    mapRef.current = map;

    map.on("load", () => {
      // Hide noisy street/POI labels per Pass 7 issue 7.1
      const labelLayers = ["road-label", "poi-label", "settlement-major-label", "settlement-minor-label"];
      for (const id of labelLayers) {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
      }

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
          "circle-color": "#60A5FA",
          "circle-radius": 6,
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

  return <div ref={containerRef} className="h-full w-full" />;
}
