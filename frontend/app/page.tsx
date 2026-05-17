"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import { useSeverityFlash } from "@/lib/useSeverityFlash";
import type {
  IncidentReport,
  BlockedRoadsResponse,
  RoadAccessSummary,
  ResponderArrivedData,
  ResponderLocationUpdatedData,
  ResponderUnit,
  RouteLeg,
  RoutingResponse,
  DispatchCompletedData,
  DispatchStartedData,
  SeverityUpgradedData,
  CortexAlertData,
} from "@/lib/types";
import { MapView } from "@/components/Map";
import { IncidentList } from "@/components/IncidentList";
import { IncidentDetail, type RecommendedDispatch } from "@/components/IncidentDetail";
import { InfraPanel } from "@/components/InfraPanel";
import { OpsPanel } from "@/components/OpsPanel";
import { SnowflakeTiles } from "@/components/SnowflakeTiles";
import { CortexChat } from "@/components/CortexChat";
import { CortexToasts } from "@/components/CortexToast";
import { TopBar } from "@/components/TopBar";
import { ErrorBoundary } from "@/components/ErrorBoundary";

interface Toast { id: number; data: CortexAlertData }
interface AcceptedRoute {
  routeId: string;
  legId: string;
  responderId: string;
  originalLeg: RouteLeg;
  leg: RouteLeg;
}

interface TrackingTimerState {
  timer: ReturnType<typeof setInterval>;
  pingIndex: number;
  inFlight: boolean;
}

const TRACKING_INTERVAL_MS = 1500;
const TRACKING_ROUTE_STEPS = 12;
const TRACKING_FINAL_DWELL_PINGS = 2;

function getRecommendedDispatch(
  incident: IncidentReport | null,
  responders: ResponderUnit[],
  routingResponse: RoutingResponse | null
): RecommendedDispatch | null {
  if (!incident || !routingResponse) return null;
  if (incident.status !== "new" && incident.status !== "dispatched") return null;
  if (responders.some((responder) => responder.assigned_incident_id === incident.id)) return null;

  const routeId = routingResponse.route_id ?? null;
  const candidates: RecommendedDispatch[] = [];

  for (const [responderId, legs] of Object.entries(routingResponse.routes)) {
    const responder = responders.find((unit) => unit.id === responderId);
    if (responder?.assigned_incident_id && responder.status !== "on_scene") continue;
    if (
      responder
      && responder.status !== "idle"
      && responder.status !== "assigned"
      && responder.status !== "on_scene"
    ) {
      continue;
    }

    for (const leg of legs) {
      const targetIncidentId = getLegIncidentId(leg);
      if (targetIncidentId !== incident.id) continue;
      candidates.push({
        routeId,
        responderId,
        responder,
        leg,
      });
    }
  }

  candidates.sort((a, b) => {
    const left = a.leg.arrival_seconds ?? a.leg.eta_seconds;
    const right = b.leg.arrival_seconds ?? b.leg.eta_seconds;
    return left - right;
  });
  return candidates[0] ?? null;
}

function getLegIncidentId(leg: RouteLeg): string | null {
  return leg.incident_id ?? (leg.target_type === "incident" ? leg.target_id ?? null : null);
}

function routeAssignmentKey(routeId: string | null | undefined, legId: string | null | undefined): string | null {
  if (!routeId || !legId) return null;
  return `${routeId}:${legId}`;
}

function getRouteCoordinates(leg: RouteLeg): [number, number][] {
  if (leg.route_geometry?.coordinates?.length) return leg.route_geometry.coordinates;
  return [
    [leg.from_location.lng, leg.from_location.lat],
    [leg.to_location.lng, leg.to_location.lat],
  ];
}

function interpolateRoutePoint(coordinates: [number, number][], progress: number): [number, number] {
  if (coordinates.length === 0) return [0, 0];
  if (coordinates.length === 1) return coordinates[0];

  const segmentLengths = coordinates.slice(1).map((coordinate, index) => {
    const previous = coordinates[index];
    return Math.hypot(coordinate[0] - previous[0], coordinate[1] - previous[1]);
  });
  const totalLength = segmentLengths.reduce((sum, length) => sum + length, 0);
  if (totalLength <= 0) return coordinates[coordinates.length - 1];

  let remainingDistance = Math.max(0, Math.min(1, progress)) * totalLength;
  for (let index = 0; index < segmentLengths.length; index += 1) {
    const segmentLength = segmentLengths[index];
    if (remainingDistance > segmentLength) {
      remainingDistance -= segmentLength;
      continue;
    }
    const previous = coordinates[index];
    const next = coordinates[index + 1];
    const segmentProgress = segmentLength > 0 ? remainingDistance / segmentLength : 1;
    return [
      previous[0] + (next[0] - previous[0]) * segmentProgress,
      previous[1] + (next[1] - previous[1]) * segmentProgress,
    ];
  }
  return coordinates[coordinates.length - 1];
}

function getRemainingRouteCoordinates(coordinates: [number, number][], progress: number): [number, number][] {
  if (coordinates.length < 2) return coordinates;

  const segmentLengths = coordinates.slice(1).map((coordinate, index) => {
    const previous = coordinates[index];
    return Math.hypot(coordinate[0] - previous[0], coordinate[1] - previous[1]);
  });
  const totalLength = segmentLengths.reduce((sum, length) => sum + length, 0);
  if (totalLength <= 0) return coordinates;

  const clampedProgress = Math.max(0, Math.min(1, progress));
  if (clampedProgress <= 0) return coordinates;
  if (clampedProgress >= 1) {
    const finalCoordinate = coordinates[coordinates.length - 1];
    return [finalCoordinate, finalCoordinate];
  }

  let traveledDistance = clampedProgress * totalLength;
  for (let index = 0; index < segmentLengths.length; index += 1) {
    const segmentLength = segmentLengths[index];
    if (traveledDistance > segmentLength) {
      traveledDistance -= segmentLength;
      continue;
    }
    const previous = coordinates[index];
    const next = coordinates[index + 1];
    const segmentProgress = segmentLength > 0 ? traveledDistance / segmentLength : 1;
    const current: [number, number] = [
      previous[0] + (next[0] - previous[0]) * segmentProgress,
      previous[1] + (next[1] - previous[1]) * segmentProgress,
    ];
    return [current, ...coordinates.slice(index + 1)];
  }

  const finalCoordinate = coordinates[coordinates.length - 1];
  return [finalCoordinate, finalCoordinate];
}

function routeLegWithRemainingGeometry(leg: RouteLeg, progress: number): RouteLeg {
  return {
    ...leg,
    route_geometry: {
      type: "LineString",
      coordinates: getRemainingRouteCoordinates(getRouteCoordinates(leg), progress),
    },
  };
}

function findRouteLeg(
  routingResponse: RoutingResponse | null,
  responderId: string | null | undefined,
  legId: string | null | undefined
): RouteLeg | null {
  if (!routingResponse || !responderId || !legId) return null;
  return routingResponse.routes[responderId]?.find((leg) => leg.leg_id === legId) ?? null;
}

function acceptedRouteIsActive(acceptedRoute: AcceptedRoute, responders: ResponderUnit[]): boolean {
  const responder = responders.find((unit) => unit.id === acceptedRoute.responderId);
  if (
    !responder
    || responder.status === "idle"
    || responder.status === "on_scene"
    || responder.status === "out_of_service"
  ) {
    return false;
  }
  const incidentId = getLegIncidentId(acceptedRoute.originalLeg);
  return Boolean(incidentId && responder.assigned_incident_id === incidentId);
}

export default function Dashboard() {
  const [incidents, setIncidents] = useState<IncidentReport[]>([]);
  const [responders, setResponders] = useState<ResponderUnit[]>([]);
  const [routingResponse, setRoutingResponse] = useState<RoutingResponse | null>(null);
  const [roadAccess, setRoadAccess] = useState<RoadAccessSummary | BlockedRoadsResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [callsHandled, setCallsHandled] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [chatOpen, setChatOpen] = useState(true);
  const [tileRefreshSignal, setTileRefreshSignal] = useState(0);
  const [dispatchingKey, setDispatchingKey] = useState<string | null>(null);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [acceptedRoutes, setAcceptedRoutes] = useState<Record<string, AcceptedRoute>>({});
  const lastLocalOptimizeAtRef = useRef(0);
  const trackingTimersRef = useRef<Map<string, TrackingTimerState>>(new Map());
  const { flashing, register } = useSeverityFlash();

  const refresh = useCallback(async () => {
    const [inc, resp] = await Promise.all([
      api.listIncidents().catch(() => []),
      api.responders().catch(() => []),
    ]);
    setIncidents(inc);
    setResponders(resp);
    setTileRefreshSignal((n) => n + 1);
  }, []);

  const refreshRouting = useCallback(async () => {
    lastLocalOptimizeAtRef.current = Date.now();
    const routing = await api.optimize().catch(() => null);
    if (routing) setRoutingResponse(routing);
  }, []);

  const refreshRoadAccess = useCallback(async () => {
    const latestRoadAccess = await api.blockedRoads().catch(() => null);
    if (latestRoadAccess) setRoadAccess(latestRoadAccess);
  }, []);

  // Initial load
  useEffect(() => {
    refresh();
    refreshRouting();
    refreshRoadAccess();
  }, [refresh, refreshRouting, refreshRoadAccess]);

  useEffect(() => {
    const trackingTimers = trackingTimersRef.current;
    return () => {
      for (const trackingState of trackingTimers.values()) {
        clearInterval(trackingState.timer);
      }
      trackingTimers.clear();
    };
  }, []);

  useEffect(() => {
    const stopTracking = (routeKey: string) => {
      const trackingState = trackingTimersRef.current.get(routeKey);
      if (!trackingState) return;
      clearInterval(trackingState.timer);
      trackingTimersRef.current.delete(routeKey);
    };

    const removeAcceptedRoute = (routeKey: string) => {
      setAcceptedRoutes((previous) => {
        if (!previous[routeKey]) return previous;
        const next = { ...previous };
        delete next[routeKey];
        return next;
      });
    };

    for (const routeKey of trackingTimersRef.current.keys()) {
      const acceptedRoute = acceptedRoutes[routeKey];
      const responder = acceptedRoute
        ? responders.find((unit) => unit.id === acceptedRoute.responderId)
        : null;
      if (!acceptedRoute || !acceptedRouteIsActive(acceptedRoute, responders) || responder?.status === "on_scene") {
        stopTracking(routeKey);
      }
    }

    for (const [routeKey, acceptedRoute] of Object.entries(acceptedRoutes)) {
      if (trackingTimersRef.current.has(routeKey)) continue;
      if (!acceptedRouteIsActive(acceptedRoute, responders)) continue;
      const responder = responders.find((unit) => unit.id === acceptedRoute.responderId);
      if (!responder || responder.status === "on_scene") continue;

      const coordinates = getRouteCoordinates(acceptedRoute.originalLeg);
      if (coordinates.length < 2) continue;

      const trackingState: TrackingTimerState = {
        pingIndex: 0,
        inFlight: false,
        timer: setInterval(async () => {
          const currentTrackingState = trackingTimersRef.current.get(routeKey);
          if (!currentTrackingState || currentTrackingState.inFlight) return;
          currentTrackingState.inFlight = true;
          currentTrackingState.pingIndex += 1;

          const progress = Math.min(1, currentTrackingState.pingIndex / TRACKING_ROUTE_STEPS);
          const [lng, lat] = progress >= 1
            ? [acceptedRoute.originalLeg.to_location.lng, acceptedRoute.originalLeg.to_location.lat]
            : interpolateRoutePoint(coordinates, progress);
          try {
            const response = await api.updateResponderLocation(acceptedRoute.responderId, {
              lat,
              lng,
              accuracy_m: 12,
              timestamp: new Date().toISOString(),
            });
            setAcceptedRoutes((previous) => {
              const currentAcceptedRoute = previous[routeKey];
              if (!currentAcceptedRoute) return previous;
              return {
                ...previous,
                [routeKey]: {
                  ...currentAcceptedRoute,
                  leg: routeLegWithRemainingGeometry(currentAcceptedRoute.originalLeg, progress),
                },
              };
            });
            const finalPingLimit = TRACKING_ROUTE_STEPS + TRACKING_FINAL_DWELL_PINGS;
            if (response.arrival_detected || currentTrackingState.pingIndex >= finalPingLimit) {
              if (response.arrival_detected) {
                const arrivalLocation = {
                  ...acceptedRoute.originalLeg.to_location,
                  lat,
                  lng,
                };
                setResponders((previous) => previous.map((responder) =>
                  responder.id === acceptedRoute.responderId
                    ? { ...responder, status: "on_scene", location: arrivalLocation }
                    : responder
                ));
                if (response.incident_id) {
                  setIncidents((previous) => previous.map((incident) =>
                    incident.id === response.incident_id ? { ...incident, status: "on_scene" } : incident
                  ));
                }
              }
              stopTracking(routeKey);
              removeAcceptedRoute(routeKey);
            }
          } catch (error) {
            console.warn("demo tracking stopped:", error);
            stopTracking(routeKey);
          } finally {
            currentTrackingState.inFlight = false;
          }
        }, TRACKING_INTERVAL_MS),
      };
      trackingTimersRef.current.set(routeKey, trackingState);
    }
  }, [acceptedRoutes, responders, routingResponse]);

  // SSE handler
  const { connected } = useSSE((evt) => {
    if (evt.type === "incident_created") {
      const data = evt.data as IncidentReport;
      setIncidents((prev) => {
        if (prev.find((i) => i.id === data.id)) return prev;
        return [data, ...prev];
      });
      if (data.source === "voice") setCallsHandled((n) => n + 1);
      setTileRefreshSignal((n) => n + 1);
    } else if (evt.type === "severity_upgraded") {
      const data = evt.data as SeverityUpgradedData;
      register(evt.sequence_id, data.incident_id);
      setIncidents((prev) => prev.map((i) =>
        i.id === data.incident_id
          ? {
              ...i,
              severity: data.to,
              ...(data.to_priority != null ? { priority_score: data.to_priority } : {}),
            }
          : i
      ));
      setTileRefreshSignal((n) => n + 1);
    } else if (evt.type === "cortex_alert") {
      const data = evt.data as CortexAlertData;
      setToasts((prev) => [...prev, { id: evt.sequence_id ?? Date.now(), data }]);
    } else if (evt.type === "responders_seeded" || evt.type === "sim_started") {
      refresh();
      refreshRouting();
    } else if (evt.type === "dispatch_started") {
      const data = evt.data as DispatchStartedData;
      const responderId = data.responder_id ?? data.responder?.id;
      const routeKey = routeAssignmentKey(data.route_id, data.leg_id);
      const leg = data.assignment?.route_leg
        ?? data.assignment?.leg
        ?? findRouteLeg(routingResponse, responderId, data.leg_id);
      if (routeKey && responderId && data.route_id && data.leg_id && leg) {
        setAcceptedRoutes((prev) => ({
          ...prev,
          [routeKey]: {
            routeId: data.route_id!,
            legId: data.leg_id!,
            responderId,
            originalLeg: leg,
            leg,
          },
        }));
      }
      const responderUpdate = data.responder;
      if (responderUpdate) {
        setResponders((prev) => prev.map((responder) =>
          responder.id === responderUpdate.id ? responderUpdate : responder
        ));
      }
      refresh();
    } else if (evt.type === "state_reset") {
      setIncidents([]); setResponders([]); setSelectedId(null);
      setRoutingResponse(null);
      setRoadAccess(null);
      setAcceptedRoutes({});
      setCallsHandled(0); setToasts([]);
      refreshRoadAccess();
    } else if (evt.type === "route_recomputed") {
      setTileRefreshSignal((n) => n + 1);
      refresh();
      refreshRoadAccess();
      if (Date.now() - lastLocalOptimizeAtRef.current > 1500) {
        refreshRouting();
      }
    } else if (evt.type === "road_access_updated") {
      setRoadAccess(evt.data as RoadAccessSummary);
      refreshRoadAccess();
    } else if (evt.type === "responder_location_updated") {
      const data = evt.data as ResponderLocationUpdatedData;
      const responder = "responder" in data ? data.responder : data;
      if (responder) {
        setResponders((prev) => {
          const exists = prev.some((existingResponder) => existingResponder.id === responder.id);
          if (!exists) return [...prev, responder];
          return prev.map((existingResponder) =>
            existingResponder.id === responder.id
              ? existingResponder.status === "on_scene" && responder.status !== "on_scene"
                ? { ...existingResponder, location: responder.location }
                : responder
              : existingResponder
          );
        });
      }
    } else if (evt.type === "responder_arrived") {
      const data = evt.data as ResponderArrivedData;
      setResponders((prev) => prev.map((responder) =>
        responder.id === data.responder_id
          ? {
              ...responder,
              ...data.responder,
              status: "on_scene",
              location: data.location,
              assigned_incident_id: data.responder?.assigned_incident_id ?? responder.assigned_incident_id,
            }
          : responder
      ));
      setIncidents((prev) => prev.map((incident) =>
        incident.id === data.incident_id ? { ...incident, status: "on_scene" } : incident
      ));
      setAcceptedRoutes((prev) => {
        const next: Record<string, AcceptedRoute> = {};
        for (const [routeKey, acceptedRoute] of Object.entries(prev)) {
          const incidentId = getLegIncidentId(acceptedRoute.originalLeg);
          if (acceptedRoute.responderId === data.responder_id || incidentId === data.incident_id) continue;
          next[routeKey] = acceptedRoute;
        }
        return next;
      });
      refreshRouting();
    } else if (evt.type === "dispatch_completed") {
      const data = evt.data as DispatchCompletedData;
      if (data.responder) {
        setResponders((prev) => prev.map((responder) =>
          responder.id === data.responder!.id ? data.responder! : responder
        ));
      }
      if (data.incident) {
        setIncidents((prev) => prev.map((incident) =>
          incident.id === data.incident!.id ? data.incident! : incident
        ));
      }
      setAcceptedRoutes((prev) => {
        const next: Record<string, AcceptedRoute> = {};
        for (const [routeKey, acceptedRoute] of Object.entries(prev)) {
          const incidentId = getLegIncidentId(acceptedRoute.originalLeg);
          if (acceptedRoute.responderId === data.responder_id || incidentId === data.incident_id) continue;
          next[routeKey] = acceptedRoute;
        }
        return next;
      });
      refresh();
      refreshRouting();
    }
  }, [register, refresh, refreshRoadAccess, refreshRouting, routingResponse]);

  const selected = useMemo(
    () => (selectedId ? incidents.find((i) => i.id === selectedId) ?? null : null),
    [selectedId, incidents]
  );

  const chatSector = useMemo(() => {
    if (!selected) return null;
    if (selected.location.lat > 29.31) return "NORTH";
    if (selected.location.lat < 29.29) return "SOUTH";
    return "CENTRAL";
  }, [selected]);

  const acceptedRouteKeys = useMemo(() => {
    const routeKeys = new Set(Object.keys(acceptedRoutes));
    if (!routingResponse?.route_id) return routeKeys;
    for (const [responderId, legs] of Object.entries(routingResponse.routes)) {
      const responder = responders.find((unit) => unit.id === responderId);
      if (!responder?.assigned_incident_id) continue;
      if (responder.status === "on_scene" || responder.status === "idle" || responder.status === "out_of_service") continue;
      for (const leg of legs) {
        if (getLegIncidentId(leg) !== responder.assigned_incident_id) continue;
        const routeKey = routeAssignmentKey(routingResponse.route_id, leg.leg_id);
        if (routeKey) routeKeys.add(routeKey);
      }
    }
    return routeKeys;
  }, [acceptedRoutes, responders, routingResponse]);

  const recommendedDispatch = useMemo(
    () => getRecommendedDispatch(selected, responders, routingResponse),
    [selected, responders, routingResponse]
  );

  const startDispatch = useCallback(async (dispatch: RecommendedDispatch) => {
    if (!dispatch.routeId || !dispatch.leg.leg_id) {
      setDispatchError("Route identifiers unavailable.");
      return;
    }
    if (dispatch.responder?.status === "on_scene") {
      setDispatchError("Complete current aid before sending the next route.");
      return;
    }

    const dispatchKey = `${dispatch.routeId}:${dispatch.leg.leg_id}`;
    setDispatchingKey(dispatchKey);
    setDispatchError(null);
    try {
      const response = await api.startDispatch({
        route_id: dispatch.routeId,
        leg_id: dispatch.leg.leg_id,
        started_by: "dispatcher",
      });
      const responseLeg = response.assignment?.route_leg
        ?? response.assignment?.leg
        ?? response.route_leg
        ?? dispatch.leg;
      setAcceptedRoutes((prev) => ({
        ...prev,
        [dispatchKey]: {
          routeId: dispatch.routeId!,
          legId: dispatch.leg.leg_id!,
          responderId: dispatch.responderId,
          originalLeg: responseLeg,
          leg: responseLeg,
        },
      }));
      if (response.responders) setResponders(response.responders);
      const responderUpdate = response.responder;
      if (responderUpdate) {
        setResponders((prev) => prev.map((responder) =>
          responder.id === responderUpdate.id ? responderUpdate : responder
        ));
      }
      if (response.incidents) setIncidents(response.incidents);
      const incidentUpdate = response.incident;
      if (incidentUpdate) {
        setIncidents((prev) => prev.map((incident) =>
          incident.id === incidentUpdate.id ? incidentUpdate : incident
        ));
      }
      if (response.routing_response) setRoutingResponse(response.routing_response);
      await refresh();
    } catch (error) {
      setDispatchError(error instanceof Error ? error.message : "Dispatch failed.");
    } finally {
      setDispatchingKey(null);
    }
  }, [refresh]);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <div className="flex h-screen flex-col bg-bg-base">
      <TopBar
        connected={connected}
        incidentsCount={incidents.length}
        respondersCount={responders.length}
        onAction={refresh}
        onOptimize={refreshRouting}
      />

      <div className="flex flex-1 overflow-hidden">
        <div className="relative flex-1">
          <ErrorBoundary label="Map">
            <MapView
              incidents={incidents}
              responders={responders}
              routingResponse={routingResponse}
              roadAccess={roadAccess}
              acceptedRoutes={Object.values(acceptedRoutes)}
              acceptedRouteKeys={acceptedRouteKeys}
              flashing={flashing}
              onSelect={setSelectedId}
            />
          </ErrorBoundary>
          <ErrorBoundary label="Cortex alerts">
            <CortexToasts toasts={toasts} onDismiss={dismissToast} />
          </ErrorBoundary>
          <ErrorBoundary label="Cortex chat">
            <CortexChat
              incidentId={selectedId}
              sector={chatSector}
              collapsed={!chatOpen}
              onToggle={() => setChatOpen((o) => !o)}
            />
          </ErrorBoundary>
          {selected && (
            <ErrorBoundary label="Incident detail">
              <IncidentDetail
                incident={selected}
                recommendedDispatch={recommendedDispatch}
                dispatching={
                  recommendedDispatch?.routeId != null &&
                  recommendedDispatch.leg.leg_id != null &&
                  dispatchingKey === `${recommendedDispatch.routeId}:${recommendedDispatch.leg.leg_id}`
                }
                dispatchError={dispatchError}
                onStartDispatch={startDispatch}
                onIncidentUpdated={(updated) => {
                  setIncidents((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
                }}
                onClose={() => setSelectedId(null)}
              />
            </ErrorBoundary>
          )}
        </div>

        <aside className="w-[360px] border-l border-border-strong bg-bg-base">
          <ErrorBoundary label="Incident list">
            <IncidentList
              incidents={incidents}
              flashing={flashing}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </ErrorBoundary>
        </aside>
      </div>

      <div className="relative h-[160px] border-t border-border-strong bg-bg-base">
        <div className="mr-[360px] flex h-full">
          <div className="w-[280px]">
            <ErrorBoundary label="Infra panel">
              <InfraPanel callsHandled={callsHandled} incidentsCount={incidents.length} />
            </ErrorBoundary>
          </div>
          <div className="min-w-0 flex-1 overflow-hidden">
            <ErrorBoundary label="Snowflake tiles">
              <SnowflakeTiles refreshSignal={tileRefreshSignal} />
            </ErrorBoundary>
          </div>
        </div>
        <div className="absolute bottom-0 right-0 h-[280px] w-[360px] border-t border-border-strong">
          <ErrorBoundary label="Live ops">
            <OpsPanel refreshSignal={tileRefreshSignal} />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
