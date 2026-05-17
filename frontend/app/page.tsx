"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import { useSeverityFlash } from "@/lib/useSeverityFlash";
import type {
  IncidentReport,
  ResponderArrivedData,
  ResponderLocationUpdatedData,
  ResponderUnit,
  RoutingResponse,
  DispatchStartedData,
  SeverityUpgradedData,
  CortexAlertData,
} from "@/lib/types";
import { MapView } from "@/components/Map";
import { IncidentList } from "@/components/IncidentList";
import { IncidentDetail, type RecommendedDispatch } from "@/components/IncidentDetail";
import { InfraPanel } from "@/components/InfraPanel";
import { SnowflakeTiles } from "@/components/SnowflakeTiles";
import { CortexToasts } from "@/components/CortexToast";
import { TopBar } from "@/components/TopBar";
import { ErrorBoundary } from "@/components/ErrorBoundary";

interface Toast { id: number; data: CortexAlertData }

function getRecommendedDispatch(
  incident: IncidentReport | null,
  responders: ResponderUnit[],
  routingResponse: RoutingResponse | null
): RecommendedDispatch | null {
  if (!incident || !routingResponse) return null;
  const routeId = routingResponse.route_id ?? null;
  const candidates: RecommendedDispatch[] = [];

  for (const [responderId, legs] of Object.entries(routingResponse.routes)) {
    for (const leg of legs) {
      const targetIncidentId =
        leg.incident_id ?? (leg.target_type === "incident" ? leg.target_id ?? null : null);
      if (targetIncidentId !== incident.id) continue;
      candidates.push({
        routeId,
        responderId,
        responder: responders.find((responder) => responder.id === responderId),
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

export default function Dashboard() {
  const [incidents, setIncidents] = useState<IncidentReport[]>([]);
  const [responders, setResponders] = useState<ResponderUnit[]>([]);
  const [routingResponse, setRoutingResponse] = useState<RoutingResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [callsHandled, setCallsHandled] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [tileRefreshSignal, setTileRefreshSignal] = useState(0);
  const [dispatchingKey, setDispatchingKey] = useState<string | null>(null);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const lastLocalOptimizeAtRef = useRef(0);
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

  // Initial load
  useEffect(() => {
    refresh();
    refreshRouting();
  }, [refresh, refreshRouting]);

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
        i.id === data.incident_id ? { ...i, severity: data.to } : i
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
      const responderUpdate = data.responder;
      if (responderUpdate) {
        setResponders((prev) => prev.map((responder) =>
          responder.id === responderUpdate.id ? responderUpdate : responder
        ));
      }
      refresh();
      refreshRouting();
    } else if (evt.type === "state_reset") {
      setIncidents([]); setResponders([]); setSelectedId(null);
      setRoutingResponse(null);
      setCallsHandled(0); setToasts([]);
    } else if (evt.type === "route_recomputed") {
      setTileRefreshSignal((n) => n + 1);
      refresh();
      if (Date.now() - lastLocalOptimizeAtRef.current > 1500) {
        refreshRouting();
      }
    } else if (evt.type === "responder_location_updated") {
      const data = evt.data as ResponderLocationUpdatedData;
      const responder = "responder" in data ? data.responder : data;
      if (responder) {
        setResponders((prev) => {
          const exists = prev.some((existingResponder) => existingResponder.id === responder.id);
          if (!exists) return [...prev, responder];
          return prev.map((existingResponder) =>
            existingResponder.id === responder.id ? responder : existingResponder
          );
        });
      }
      refresh();
      refreshRouting();
    } else if (evt.type === "responder_arrived") {
      const data = evt.data as ResponderArrivedData;
      setResponders((prev) => prev.map((responder) =>
        responder.id === data.responder_id
          ? { ...responder, status: "on_scene", location: data.location }
          : responder
      ));
      setIncidents((prev) => prev.map((incident) =>
        incident.id === data.incident_id ? { ...incident, status: "on_scene" } : incident
      ));
      refresh();
      refreshRouting();
    }
  }, [register, refresh, refreshRouting]);

  const selected = useMemo(
    () => (selectedId ? incidents.find((i) => i.id === selectedId) ?? null : null),
    [selectedId, incidents]
  );

  const recommendedDispatch = useMemo(
    () => getRecommendedDispatch(selected, responders, routingResponse),
    [selected, responders, routingResponse]
  );

  const startDispatch = useCallback(async (dispatch: RecommendedDispatch) => {
    if (!dispatch.routeId || !dispatch.leg.leg_id) {
      setDispatchError("Route identifiers unavailable.");
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
      await Promise.all([refresh(), refreshRouting()]);
    } catch (error) {
      setDispatchError(error instanceof Error ? error.message : "Dispatch failed.");
    } finally {
      setDispatchingKey(null);
    }
  }, [refresh, refreshRouting]);

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
      />

      <div className="flex flex-1 overflow-hidden">
        <div className="relative flex-1">
          <ErrorBoundary label="Map">
            <MapView
              incidents={incidents}
              responders={responders}
              routingResponse={routingResponse}
              flashing={flashing}
              onSelect={setSelectedId}
            />
          </ErrorBoundary>
          <ErrorBoundary label="Cortex alerts">
            <CortexToasts toasts={toasts} onDismiss={dismissToast} />
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

      <div className="h-[180px] border-t border-border-strong bg-bg-base flex">
        <div className="w-[280px]">
          <ErrorBoundary label="Infra panel">
            <InfraPanel callsHandled={callsHandled} incidentsCount={incidents.length} />
          </ErrorBoundary>
        </div>
        <div className="flex-1">
          <ErrorBoundary label="Snowflake tiles">
            <SnowflakeTiles refreshSignal={tileRefreshSignal} />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
