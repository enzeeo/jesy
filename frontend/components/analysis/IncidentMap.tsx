"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import type { IncidentGeoPoint } from "@/lib/aar";

interface Props {
  points: IncidentGeoPoint[];
  cursorTSeconds: number;
  startedAt: string | null;
}

// Hilo Bay center — matches the main dashboard's MapView for visual continuity.
const HILO = { lng: -155.0900, lat: 19.7297, zoom: 13.0 };
const TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

function colorForEta(eta: number | null): string {
  if (eta == null) return "#64748B";                  // fg-muted: unassigned
  if (eta < 5 * 60) return "#22C55E";                 // status-good: < 5min
  if (eta < 10 * 60) return "#FACC15";                // warn: 5-10min
  return "#EF4444";                                   // bad: > 10min
}

export function IncidentMap({ points, cursorTSeconds, startedAt }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [initError, setInitError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    if (!TOKEN) return;
    mapboxgl.accessToken = TOKEN;
    let map: mapboxgl.Map;
    try {
      map = new mapboxgl.Map({
        container: containerRef.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [HILO.lng, HILO.lat],
        zoom: HILO.zoom,
        attributionControl: false,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setInitError(msg);
      return;
    }
    mapRef.current = map;
    map.on("load", () => {
      const labelLayers = ["road-label", "poi-label", "settlement-major-label", "settlement-minor-label"];
      for (const id of labelLayers) {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
      }
      map.addSource("incidents", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "incident-dots",
        type: "circle",
        source: "incidents",
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 4, 14, 8],
          "circle-stroke-color": "#0B0F19",
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });
    });
    return () => { map.remove(); mapRef.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const t0Ms = startedAt ? new Date(startedAt).getTime() : 0;

  const geojson = useMemo(() => ({
    type: "FeatureCollection" as const,
    features: points
      .filter((p) => {
        if (!startedAt) return true;
        const offset = (new Date(p.timestamp).getTime() - t0Ms) / 1000;
        return offset <= cursorTSeconds;
      })
      .map((p) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [p.lng, p.lat] },
        properties: {
          id: p.id,
          severity: p.severity,
          color: colorForEta(p.eta_seconds),
        },
      })),
  }), [points, cursorTSeconds, startedAt, t0Ms]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("incidents") as mapboxgl.GeoJSONSource | undefined;
    if (src) src.setData(geojson as any);
  }, [geojson]);

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
          <div className="mono text-xs mt-2 text-status-warn">{initError}</div>
        </div>
      </div>
    );
  }
  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      <div className="absolute bottom-3 left-3 bg-bg-panel/90 border border-border-strong p-2 text-[10px] mono">
        <div className="text-fg-muted uppercase tracking-wider mb-1">Response time</div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-status-good inline-block" /> &lt;5min</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ background: "#FACC15" }} /> 5–10min</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ background: "#EF4444" }} /> &gt;10min</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-fg-muted inline-block" /> unassigned</span>
        </div>
      </div>
    </div>
  );
}
