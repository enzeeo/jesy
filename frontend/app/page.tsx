"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import { useSeverityFlash } from "@/lib/useSeverityFlash";
import type {
  ActiveResponderAssignment,
  IncidentReport,
  BlockedRoadsResponse,
  RoadAccessSummary,
  ResponderArrivedData,
  ResponderAssignment,
  ResponderLocationUpdatedData,
  ResponderUnit,
  RouteLineString,
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

function findRouteLeg(
  routingResponse: RoutingResponse | null,
  responderId: string | null | undefined,
  legId: string | null | undefined
): RouteLeg | null {
  if (!routingResponse || !responderId || !legId) return null;
  return routingResponse.routes[responderId]?.find((leg) => leg.leg_id === legId) ?? null;
}

function routeLegWithRemainingGeometry(
  leg: RouteLeg,
  remainingRouteGeometry: RouteLineString | null | undefined
): RouteLeg {
  if (!remainingRouteGeometry) return leg;
  return { ...leg, route_geometry: remainingRouteGeometry };
}

function getAssignmentLeg(assignment: ResponderAssignment): RouteLeg | null {
  return assignment.route_leg ?? assignment.leg ?? null;
}

function acceptedRouteFromAssignment(
  assignment: ResponderAssignment,
  previousAcceptedRoute?: AcceptedRoute,
  remainingRouteGeometry?: RouteLineString | null,
  fallbackResponderId?: string
): AcceptedRoute | null {
  const routeId = assignment.route_id ?? previousAcceptedRoute?.routeId;
  const legId = assignment.leg_id ?? previousAcceptedRoute?.legId;
  const responderId = assignment.responder_id ?? previousAcceptedRoute?.responderId ?? fallbackResponderId;
  const assignmentLeg = getAssignmentLeg(assignment);
  const baseLeg = assignmentLeg ?? previousAcceptedRoute?.leg ?? previousAcceptedRoute?.originalLeg ?? null;
  if (!routeId || !legId || !responderId || !baseLeg) return null;

  const leg = routeLegWithRemainingGeometry(
    baseLeg,
    remainingRouteGeometry ?? assignment.remaining_route_geometry
  );

  return {
    routeId,
    legId,
    responderId,
    originalLeg: previousAcceptedRoute?.originalLeg ?? assignmentLeg ?? leg,
    leg,
  };
}

function acceptedRoutesFromAssignments(
  assignments: ActiveResponderAssignment[],
  previousAcceptedRoutes: Record<string, AcceptedRoute> = {}
): Record<string, AcceptedRoute> {
  const next: Record<string, AcceptedRoute> = {};
  for (const assignment of assignments) {
    const routeKey = routeAssignmentKey(assignment.route_id, assignment.leg_id);
    const acceptedRoute = acceptedRouteFromAssignment(
      assignment,
      routeKey ? previousAcceptedRoutes[routeKey] : undefined
    );
    if (!acceptedRoute) continue;
    const acceptedRouteKey = routeAssignmentKey(acceptedRoute.routeId, acceptedRoute.legId);
    if (acceptedRouteKey) next[acceptedRouteKey] = acceptedRoute;
  }
  return next;
}

function getResponderFromLocationEvent(data: ResponderLocationUpdatedData): ResponderUnit | null {
  if (data && typeof data === "object" && "responder" in data) return data.responder ?? null;
  if (data && typeof data === "object" && "id" in data) return data as ResponderUnit;
  return null;
}

function getAssignmentFromLocationEvent(data: ResponderLocationUpdatedData): ResponderAssignment | null {
  if (data && typeof data === "object" && "assignment" in data) return data.assignment ?? null;
  return null;
}

function getRemainingGeometryFromLocationEvent(data: ResponderLocationUpdatedData): RouteLineString | null {
  if (data && typeof data === "object" && "remaining_route_geometry" in data) {
    return data.remaining_route_geometry ?? null;
  }
  return null;
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
  const { flashing, register } = useSeverityFlash();

  const refresh = useCallback(async () => {
    const [inc, resp, activeAssignmentsResult] = await Promise.all([
      api.listIncidents().catch(() => []),
      api.responders().catch(() => []),
      api.activeResponderAssignments()
        .then((assignments) => ({ ok: true as const, assignments }))
        .catch(() => ({ ok: false as const, assignments: [] as ActiveResponderAssignment[] })),
    ]);
    setIncidents(inc);
    setResponders(resp);
    if (activeAssignmentsResult.ok) {
      setAcceptedRoutes((prev) => acceptedRoutesFromAssignments(activeAssignmentsResult.assignments, prev));
    }
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
        ?? data.route_leg
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
      const responder = getResponderFromLocationEvent(data);
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
      const assignment = getAssignmentFromLocationEvent(data);
      const remainingRouteGeometry = getRemainingGeometryFromLocationEvent(data);
      if (assignment) {
        setAcceptedRoutes((prev) => {
          const routeKey = routeAssignmentKey(assignment.route_id, assignment.leg_id);
          if (!routeKey) return prev;
          const acceptedRoute = acceptedRouteFromAssignment(
            assignment,
            prev[routeKey],
            remainingRouteGeometry,
            responder?.id
          );
          if (!acceptedRoute) return prev;
          return { ...prev, [routeKey]: acceptedRoute };
        });
      } else if (responder && remainingRouteGeometry) {
        setAcceptedRoutes((prev) => {
          let changed = false;
          const next: Record<string, AcceptedRoute> = {};
          for (const [routeKey, acceptedRoute] of Object.entries(prev)) {
            if (acceptedRoute.responderId !== responder.id) {
              next[routeKey] = acceptedRoute;
              continue;
            }
            changed = true;
            next[routeKey] = {
              ...acceptedRoute,
              leg: routeLegWithRemainingGeometry(acceptedRoute.leg, remainingRouteGeometry),
            };
          }
          return changed ? next : prev;
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
