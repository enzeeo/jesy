import { useEffect, useMemo, useRef } from 'react';
import mapboxgl from 'mapbox-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { LineLayer, ScatterplotLayer } from '@deck.gl/layers';
import { AnimatePresence, motion } from 'framer-motion';
import { useShallow } from 'zustand/react/shallow';

import 'mapbox-gl/dist/mapbox-gl.css';

import type { IncidentEnriched, RoutePreview, SeverityBand } from '@disaster/types';
import { severityBand } from '@disaster/types';

import { selectIncidents, selectRoutes, useDashboardStore } from '../lib/store';
import { SEVERITY_BAND_HEX } from './severity';

const HOUSTON = { lat: 29.7604, lng: -95.3698 };
const FALLBACK_BBOX = {
  minLat: 29.71,
  maxLat: 29.83,
  minLng: -95.6,
  maxLng: -95.3,
};

const TOKEN = import.meta.env.VITE_MAPBOX_PUBLIC_TOKEN ?? '';

function bandColor(band: SeverityBand): [number, number, number] {
  switch (band) {
    case 'critical':
      return [239, 68, 68];
    case 'high':
      return [251, 146, 60];
    case 'medium':
      return [245, 158, 11];
    case 'low':
      return [16, 185, 129];
    case 'info':
      return [56, 189, 248];
  }
}

interface RouteSegment {
  id: string;
  route: RoutePreview;
  from: { lat: number; lng: number };
  to: { lat: number; lng: number };
  isSelected: boolean;
}

function makeRouteSegments(
  routes: RoutePreview[],
  incidentsById: Record<string, IncidentEnriched>,
  respondersById: ReturnType<typeof useDashboardStore.getState>['respondersById'],
  selectedResponderId: string | null,
): RouteSegment[] {
  const segments: RouteSegment[] = [];
  for (const route of routes) {
    const responder = respondersById[route.responder_id];
    let current = responder?.current_location;
    if (!current) continue;

    const orderedStops = [...route.stops].sort((a, b) => a.order - b.order);
    for (const stop of orderedStops) {
      const incident = incidentsById[stop.incident_id];
      if (!incident) continue;
      segments.push({
        id: `${route.responder_id}-${stop.incident_id}-${stop.order}`,
        route,
        from: current,
        to: incident.location,
        isSelected:
          selectedResponderId === null ||
          selectedResponderId === route.responder_id,
      });
      current = incident.location;
    }
  }
  return segments;
}

export default function MapView() {
  if (TOKEN) return <MapboxMap />;
  return <FallbackMap />;
}

// ---------------------------------------------------------------
// Mapbox + deck.gl path
// ---------------------------------------------------------------

function MapboxMap() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);

  const incidents = useDashboardStore(useShallow(selectIncidents));
  const routes = useDashboardStore(useShallow(selectRoutes));
  const incidentsById = useDashboardStore((s) => s.incidentsById);
  const respondersById = useDashboardStore((s) => s.respondersById);
  const selectedResponderId = useDashboardStore((s) => s.selectedResponderId);
  const select = useDashboardStore((s) => s.selectIncident);

  const routeSegments = useMemo(
    () =>
      makeRouteSegments(
        routes,
        incidentsById,
        respondersById,
        selectedResponderId,
      ),
    [routes, incidentsById, respondersById, selectedResponderId],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    if (mapRef.current) return;

    mapboxgl.accessToken = TOKEN;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/satellite-streets-v12',
      center: [HOUSTON.lng, HOUSTON.lat],
      zoom: 11,
      attributionControl: false,
    });
    mapRef.current = map;

    const overlay = new MapboxOverlay({
      interleaved: true,
      layers: [],
    });
    overlayRef.current = overlay;
    map.addControl(overlay as unknown as mapboxgl.IControl);

    map.on('click', (e) => {
      // Hit-test deck.gl objects: get the rendered feature underneath.
      const features = (overlay as unknown as {
        pickObject?: (opts: { x: number; y: number; radius?: number }) => {
          object?: IncidentEnriched;
        } | null;
      }).pickObject?.({
        x: e.point.x,
        y: e.point.y,
        radius: 6,
      });
      const incident = features?.object;
      if (incident) select(incident.incident_id);
    });

    return () => {
      try {
        map.remove();
      } catch {
        /* noop */
      }
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, [select]);

  useEffect(() => {
    if (!overlayRef.current) return;

    const layers = [
      new LineLayer<RouteSegment>({
        id: 'route-lines',
        data: routeSegments,
        getSourcePosition: (s: RouteSegment) => [s.from.lng, s.from.lat],
        getTargetPosition: (s: RouteSegment) => [s.to.lng, s.to.lat],
        getColor: (s: RouteSegment) =>
          s.route.route_source === 'fallback'
            ? [245, 158, 11, s.isSelected ? 230 : 90]
            : s.route.route_source === 'cached'
              ? [148, 163, 184, s.isSelected ? 220 : 80]
              : [56, 189, 248, s.isSelected ? 230 : 90],
        getWidth: (s: RouteSegment) => (s.isSelected ? 4 : 2),
        widthUnits: 'pixels',
        updateTriggers: {
          getColor: selectedResponderId,
          getWidth: selectedResponderId,
        },
        transitions: {
          getSourcePosition: 250,
          getTargetPosition: 250,
          getColor: 200,
        },
      }),
      new ScatterplotLayer<IncidentEnriched>({
        id: 'incident-glow',
        data: incidents,
        stroked: false,
        filled: true,
        radiusUnits: 'pixels',
        getPosition: (i: IncidentEnriched) => [i.location.lng, i.location.lat],
        getRadius: (i: IncidentEnriched) =>
          severityBand(i.severity.score) === 'critical' ? 28 : 18,
        getFillColor: (i: IncidentEnriched) => {
          const c = bandColor(severityBand(i.severity.score));
          return [c[0], c[1], c[2], 60];
        },
      }),
      new ScatterplotLayer<IncidentEnriched>({
        id: 'incident-pins',
        data: incidents,
        pickable: true,
        stroked: true,
        filled: true,
        radiusUnits: 'pixels',
        getPosition: (i: IncidentEnriched) => [i.location.lng, i.location.lat],
        getRadius: (i: IncidentEnriched) =>
          severityBand(i.severity.score) === 'critical' ? 11 : 7,
        getFillColor: (i: IncidentEnriched) => {
          const c = bandColor(severityBand(i.severity.score));
          return [c[0], c[1], c[2], 230];
        },
        getLineColor: () => [9, 9, 11, 255],
        lineWidthMinPixels: 1.5,
        updateTriggers: {
          getRadius: incidents.length,
          getFillColor: incidents.length,
        },
        transitions: {
          getPosition: 250,
          getRadius: 250,
          getFillColor: 250,
        },
      }),
    ];

    overlayRef.current.setProps({ layers });
  }, [incidents, routeSegments, selectedResponderId]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="absolute inset-0" />
      <MapBadges />
    </div>
  );
}

// ---------------------------------------------------------------
// CSS / SVG fallback path
// ---------------------------------------------------------------

function FallbackMap() {
  const incidents = useDashboardStore(useShallow(selectIncidents));
  const routes = useDashboardStore(useShallow(selectRoutes));
  const incidentsById = useDashboardStore((s) => s.incidentsById);
  const respondersById = useDashboardStore((s) => s.respondersById);
  const selectedResponderId = useDashboardStore((s) => s.selectedResponderId);
  const select = useDashboardStore((s) => s.selectIncident);
  const selectedId = useDashboardStore((s) => s.selectedIncidentId);

  const clusters = useDashboardStore((s) => s.clustersById);
  const clusterCentroids = useMemo(
    () =>
      Object.values(clusters).filter((c) => c.incident_ids.length >= 2),
    [clusters],
  );

  const projected = useMemo(
    () =>
      incidents.map((i) => {
        const xPct =
          ((i.location.lng - FALLBACK_BBOX.minLng) /
            (FALLBACK_BBOX.maxLng - FALLBACK_BBOX.minLng)) *
          100;
        const yPct =
          ((FALLBACK_BBOX.maxLat - i.location.lat) /
            (FALLBACK_BBOX.maxLat - FALLBACK_BBOX.minLat)) *
          100;
        return { incident: i, xPct, yPct };
      }),
    [incidents],
  );

  const routeSegments = useMemo(
    () =>
      makeRouteSegments(
        routes,
        incidentsById,
        respondersById,
        selectedResponderId,
      ),
    [routes, incidentsById, respondersById, selectedResponderId],
  );

  const projectPoint = (point: { lat: number; lng: number }) => {
    const xPct =
      ((point.lng - FALLBACK_BBOX.minLng) /
        (FALLBACK_BBOX.maxLng - FALLBACK_BBOX.minLng)) *
      100;
    const yPct =
      ((FALLBACK_BBOX.maxLat - point.lat) /
        (FALLBACK_BBOX.maxLat - FALLBACK_BBOX.minLat)) *
      100;
    return { xPct, yPct };
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950">
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden
      >
        <defs>
          <pattern
            id="grid"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 6 0 L 0 0 0 6"
              fill="none"
              stroke="rgb(39,39,42)"
              strokeWidth="0.15"
            />
          </pattern>
          <linearGradient id="bayou" x1="0" x2="1">
            <stop offset="0" stopColor="rgb(30,58,138)" stopOpacity="0.4" />
            <stop offset="1" stopColor="rgb(30,58,138)" stopOpacity="0.2" />
          </linearGradient>
        </defs>
        <rect width="100" height="100" fill="url(#grid)" />
        {/* Stylized 'Buffalo Bayou' winding through */}
        <path
          d="M 0 62 Q 18 58, 30 64 T 60 60 T 100 56"
          stroke="url(#bayou)"
          strokeWidth="1.6"
          fill="none"
        />
        {/* Stylized I-10 and 610 */}
        <path
          d="M 0 40 L 100 40"
          stroke="rgb(82,82,91)"
          strokeWidth="0.35"
          strokeDasharray="1.5 1.5"
        />
        <path
          d="M 0 70 L 100 70"
          stroke="rgb(82,82,91)"
          strokeWidth="0.35"
          strokeDasharray="1.5 1.5"
        />
        <path
          d="M 30 0 L 30 100"
          stroke="rgb(82,82,91)"
          strokeWidth="0.35"
          strokeDasharray="1.5 1.5"
        />
        <path
          d="M 70 0 L 70 100"
          stroke="rgb(82,82,91)"
          strokeWidth="0.35"
          strokeDasharray="1.5 1.5"
        />
        {routeSegments.map((segment) => {
          const start = projectPoint(segment.from);
          const end = projectPoint(segment.to);
          const stroke =
            segment.route.route_source === 'fallback'
              ? 'rgb(245,158,11)'
              : segment.route.route_source === 'cached'
                ? 'rgb(148,163,184)'
                : 'rgb(56,189,248)';
          return (
            <motion.line
              key={segment.id}
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{
                pathLength: 1,
                opacity: segment.isSelected ? 0.9 : 0.35,
              }}
              transition={{ duration: 0.35 }}
              x1={start.xPct}
              y1={start.yPct}
              x2={end.xPct}
              y2={end.yPct}
              stroke={stroke}
              strokeWidth={segment.isSelected ? 0.75 : 0.4}
              strokeDasharray={
                segment.route.route_source === 'fallback' ? '1.2 1.2' : undefined
              }
            />
          );
        })}
      </svg>

      {/* Cluster rings */}
      {clusterCentroids.map((c) => {
        const x =
          ((c.centroid.lng - FALLBACK_BBOX.minLng) /
            (FALLBACK_BBOX.maxLng - FALLBACK_BBOX.minLng)) *
          100;
        const y =
          ((FALLBACK_BBOX.maxLat - c.centroid.lat) /
            (FALLBACK_BBOX.maxLat - FALLBACK_BBOX.minLat)) *
          100;
        const size = 36 + c.incident_ids.length * 10;
        return (
          <motion.div
            key={c.cluster_id}
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 0.75 }}
            transition={{ type: 'spring', stiffness: 200, damping: 18 }}
            className="pointer-events-none absolute rounded-full border border-purple-400/50 bg-purple-500/15"
            style={{
              left: `calc(${x}% - ${size / 2}px)`,
              top: `calc(${y}% - ${size / 2}px)`,
              width: size,
              height: size,
            }}
          />
        );
      })}

      <AnimatePresence>
        {projected.map(({ incident, xPct, yPct }) => {
          const band = severityBand(incident.severity.score);
          const isCritical = band === 'critical';
          const isSelected = incident.incident_id === selectedId;
          return (
            <motion.button
              key={incident.incident_id}
              type="button"
              onClick={() => select(incident.incident_id)}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              transition={{
                type: 'spring',
                stiffness: 280,
                damping: 22,
              }}
              className="absolute -translate-x-1/2 -translate-y-1/2 cursor-pointer"
              style={{ left: `${xPct}%`, top: `${yPct}%` }}
              title={`${incident.incident_id} — sev ${incident.severity.score}`}
            >
              {isCritical && (
                <span
                  className="absolute inset-0 -m-3 animate-ping rounded-full opacity-60"
                  style={{ background: SEVERITY_BAND_HEX[band] }}
                />
              )}
              <span
                className={
                  'relative block rounded-full ring-2 ring-zinc-950 ' +
                  (isSelected ? 'h-5 w-5' : isCritical ? 'h-4 w-4' : 'h-3 w-3')
                }
                style={{ background: SEVERITY_BAND_HEX[band] }}
              />
            </motion.button>
          );
        })}
      </AnimatePresence>

      <MapBadges />
    </div>
  );
}

// ---------------------------------------------------------------
// Shared overlay badges
// ---------------------------------------------------------------

function MapBadges() {
  const mode = useDashboardStore((s) => s.connectionLabel);

  return (
    <>
      <div className="pointer-events-none absolute left-3 top-3 z-10 rounded border border-zinc-800 bg-zinc-950/85 px-2 py-1.5 backdrop-blur">
        <div className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-zinc-400">
          Severity
        </div>
        <div className="grid grid-cols-1 gap-0.5 text-[10px]">
          <Legend label="90-100 Critical" color={SEVERITY_BAND_HEX.critical} />
          <Legend label="75-89 High" color={SEVERITY_BAND_HEX.high} />
          <Legend label="50-74 Medium" color={SEVERITY_BAND_HEX.medium} />
          <Legend label="25-49 Low" color={SEVERITY_BAND_HEX.low} />
          <Legend label="0-24 Info" color={SEVERITY_BAND_HEX.info} />
        </div>
      </div>
      <div className="pointer-events-none absolute right-4 bottom-3 z-10 rounded border border-amber-500/30 bg-amber-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-widest text-amber-300 backdrop-blur">
        {mode === 'fixture' ? 'Fixture data — Mock' : 'Live data'}
      </div>
    </>
  );
}

function Legend({ label, color }: { label: string; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="h-2 w-2 rounded-full"
        style={{ background: color }}
      />
      <span className="text-zinc-300">{label}</span>
    </div>
  );
}
