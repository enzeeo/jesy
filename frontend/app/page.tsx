"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import { useSeverityFlash } from "@/lib/useSeverityFlash";
import type { IncidentReport, ResponderUnit, SeverityUpgradedData, CortexAlertData, Severity } from "@/lib/types";
import { MapView } from "@/components/Map";
import { IncidentList } from "@/components/IncidentList";
import { IncidentDetail } from "@/components/IncidentDetail";
import { InfraPanel } from "@/components/InfraPanel";
import { SnowflakeTiles } from "@/components/SnowflakeTiles";
import { CortexToasts } from "@/components/CortexToast";
import { TopBar } from "@/components/TopBar";
import { ErrorBoundary } from "@/components/ErrorBoundary";

interface Toast { id: number; data: CortexAlertData }

export default function Dashboard() {
  const [incidents, setIncidents] = useState<IncidentReport[]>([]);
  const [responders, setResponders] = useState<ResponderUnit[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [callsHandled, setCallsHandled] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [tileRefreshSignal, setTileRefreshSignal] = useState(0);
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

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

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
    } else if (evt.type === "state_reset") {
      setIncidents([]); setResponders([]); setSelectedId(null);
      setCallsHandled(0); setToasts([]);
    } else if (evt.type === "route_recomputed") {
      setTileRefreshSignal((n) => n + 1);
    }
  }, [register, refresh]);

  const selected = useMemo(
    () => (selectedId ? incidents.find((i) => i.id === selectedId) ?? null : null),
    [selectedId, incidents]
  );

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
              flashing={flashing}
              onSelect={setSelectedId}
            />
          </ErrorBoundary>
          <ErrorBoundary label="Cortex alerts">
            <CortexToasts toasts={toasts} onDismiss={dismissToast} />
          </ErrorBoundary>
          {selected && (
            <ErrorBoundary label="Incident detail">
              <IncidentDetail incident={selected} onClose={() => setSelectedId(null)} />
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
