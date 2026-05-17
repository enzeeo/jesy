"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import type {
  DispatchStartedData,
  Location,
  ResponderArrivedData,
  ResponderAssignment,
  ResponderLocationPing,
  ResponderLocationUpdatedData,
  ResponderUnit,
  RouteLeg,
} from "@/lib/types";

const DEFAULT_LOCATION = { lat: 29.3013, lng: -94.7977, description: "Galveston demo" };

function formatEta(seconds?: number | null): string {
  if (seconds == null) return "--";
  return `${Math.max(1, Math.round(seconds / 60))} min`;
}

function formatDistance(km?: number | null): string {
  if (km == null) return "--";
  return `${km.toFixed(1)} km`;
}

function assignmentLeg(assignment: ResponderAssignment | null): RouteLeg | null {
  return assignment?.route_leg ?? assignment?.leg ?? null;
}

function assignmentDestination(assignment: ResponderAssignment | null): Location | null {
  const leg = assignmentLeg(assignment);
  return assignment?.incident?.location ?? leg?.to_location ?? null;
}

function getResponderFromLocationEvent(data: ResponderLocationUpdatedData): ResponderUnit | null {
  if (data && typeof data === "object" && "responder" in data) return data.responder;
  return data as ResponderUnit;
}

function makePing(lat: number, lng: number, accuracy_m: number): ResponderLocationPing {
  return {
    lat,
    lng,
    accuracy_m,
    timestamp: new Date().toISOString(),
  };
}

export default function ResponderPage() {
  const [responders, setResponders] = useState<ResponderUnit[]>([]);
  const [selectedResponderId, setSelectedResponderId] = useState("");
  const [assignment, setAssignment] = useState<ResponderAssignment | null>(null);
  const [manualLat, setManualLat] = useState(DEFAULT_LOCATION.lat.toFixed(5));
  const [manualLng, setManualLng] = useState(DEFAULT_LOCATION.lng.toFixed(5));
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const selectedResponder = useMemo(
    () => responders.find((responder) => responder.id === selectedResponderId) ?? null,
    [responders, selectedResponderId]
  );

  const loadResponders = useCallback(async () => {
    const units = await api.responders();
    setResponders(units);
    setSelectedResponderId((currentId) => currentId || units[0]?.id || "");
    setLoading(false);
  }, []);

  const loadAssignment = useCallback(async (responderId: string) => {
    if (!responderId) {
      setAssignment(null);
      return;
    }
    setAssignment(await api.responderAssignment(responderId));
  }, []);

  useEffect(() => {
    loadResponders();
  }, [loadResponders]);

  useEffect(() => {
    if (!selectedResponder) return;
    setManualLat(selectedResponder.location.lat.toFixed(5));
    setManualLng(selectedResponder.location.lng.toFixed(5));
    loadAssignment(selectedResponder.id);
  }, [selectedResponder, loadAssignment]);

  const refreshSelected = useCallback(async () => {
    await Promise.all([
      loadResponders(),
      selectedResponderId ? loadAssignment(selectedResponderId) : Promise.resolve(),
    ]);
  }, [loadAssignment, loadResponders, selectedResponderId]);

  useSSE((event) => {
    if (event.type === "responder_location_updated") {
      const responder = getResponderFromLocationEvent(event.data as ResponderLocationUpdatedData);
      if (!responder) return;
      setResponders((previous) => previous.map((unit) => unit.id === responder.id ? responder : unit));
      if (responder.id === selectedResponderId) {
        setManualLat(responder.location.lat.toFixed(5));
        setManualLng(responder.location.lng.toFixed(5));
        setMessage(`Location updated: ${responder.location.lat.toFixed(5)}, ${responder.location.lng.toFixed(5)}`);
      }
    } else if (event.type === "responder_arrived") {
      const data = event.data as ResponderArrivedData;
      if (data.responder_id !== selectedResponderId) return;
      setResponders((previous) => previous.map((unit) =>
        unit.id === data.responder_id ? { ...unit, status: "on_scene", location: data.location } : unit
      ));
      setAssignment((previous) => previous ? { ...previous, status: "on_scene" } : previous);
      setMessage("Arrival detected.");
    } else if (event.type === "dispatch_started") {
      const data = event.data as DispatchStartedData;
      const responderId = data.responder_id ?? data.responder?.id;
      if (responderId !== selectedResponderId) return;
      const responderUpdate = data.responder;
      if (responderUpdate) {
        setResponders((previous) => previous.map((unit) => unit.id === responderUpdate.id ? responderUpdate : unit));
      }
      setAssignment(data.assignment ?? null);
      loadAssignment(responderId);
      setMessage("Dispatch received.");
    } else if (event.type === "responders_seeded" || event.type === "state_reset") {
      refreshSelected();
    }
  }, [loadAssignment, refreshSelected, selectedResponderId]);

  async function sendPing(ping: ResponderLocationPing) {
    if (!selectedResponderId) return;
    setSending(true);
    setMessage(null);
    try {
      const response = await api.updateResponderLocation(selectedResponderId, ping);
      setMessage(response.arrival_detected ? "Ping sent. Arrival detected." : "Ping sent.");
      await refreshSelected();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ping failed.");
    } finally {
      setSending(false);
    }
  }

  function sendBrowserLocation() {
    if (!navigator.geolocation) {
      setMessage("Browser GPS unavailable. Use manual ping.");
      return;
    }
    setSending(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        sendPing(makePing(position.coords.latitude, position.coords.longitude, position.coords.accuracy || 25));
      },
      (error) => {
        setSending(false);
        setMessage(error.message || "Browser GPS denied. Use manual ping.");
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 5000 }
    );
  }

  function sendManualPing() {
    const lat = Number(manualLat);
    const lng = Number(manualLng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      setMessage("Enter valid latitude and longitude.");
      return;
    }
    sendPing(makePing(lat, lng, 12));
  }

  function sendSimulatedPing() {
    const current = selectedResponder?.location ?? DEFAULT_LOCATION;
    const destination = assignmentDestination(assignment);
    const next = destination
      ? {
          lat: current.lat + (destination.lat - current.lat) * 0.35,
          lng: current.lng + (destination.lng - current.lng) * 0.35,
        }
      : { lat: current.lat + 0.0004, lng: current.lng + 0.0004 };
    setManualLat(next.lat.toFixed(5));
    setManualLng(next.lng.toFixed(5));
    sendPing(makePing(next.lat, next.lng, 30));
  }

  const leg = assignmentLeg(assignment);
  const incidentId = assignment?.incident_id ?? assignment?.incident?.id ?? leg?.incident_id ?? leg?.target_id ?? null;
  const etaSeconds = assignment?.eta_seconds ?? leg?.eta_seconds ?? null;
  const distanceKm = assignment?.distance_km ?? leg?.distance_km ?? null;

  return (
    <main className="h-screen overflow-y-auto bg-bg-base text-fg-primary">
      <div className="mx-auto flex min-h-screen w-full max-w-md flex-col border-x border-border-strong bg-bg-panel">
        <header className="border-b border-border-strong px-4 py-3">
          <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Responder</div>
          <div className="mt-1 text-xl font-semibold">Mobile Unit Console</div>
        </header>

        <section className="space-y-4 p-4">
          <label className="block">
            <span className="mono text-xs uppercase tracking-wider text-fg-secondary">Unit</span>
            <select
              value={selectedResponderId}
              onChange={(event) => setSelectedResponderId(event.target.value)}
              className="mt-2 w-full border border-border-strong bg-bg-base px-3 py-2 text-sm text-fg-primary"
            >
              {responders.map((responder) => (
                <option key={responder.id} value={responder.id}>
                  {responder.callsign} - {responder.status}
                </option>
              ))}
            </select>
          </label>

          {loading ? (
            <div className="border border-border-strong bg-bg-base p-3 text-sm text-fg-secondary">Loading units.</div>
          ) : null}

          {selectedResponder ? (
            <div className="border border-border-strong bg-bg-base p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold">{selectedResponder.callsign}</div>
                  <div className="mono text-xs uppercase tracking-wider text-fg-secondary">{selectedResponder.type}</div>
                </div>
                <div className="mono border border-border-strong px-2 py-1 text-xs uppercase text-status-good">
                  {selectedResponder.status}
                </div>
              </div>
              <div className="mono mt-3 text-xs text-fg-muted">
                assigned: {selectedResponder.assigned_incident_id ?? "none"}
              </div>
              <div className="mono mt-1 text-xs text-fg-muted">
                {selectedResponder.location.lat.toFixed(5)}, {selectedResponder.location.lng.toFixed(5)}
              </div>
            </div>
          ) : (
            <div className="border border-border-strong bg-bg-base p-3 text-sm text-fg-secondary">
              No responders available. Seed responders from the dashboard.
            </div>
          )}

          <div className="border border-border-strong bg-bg-base p-3">
            <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Active Assignment</div>
            {assignment || leg ? (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <div className="mono text-xs text-fg-muted">incident</div>
                  <div className="truncate text-sm">{incidentId ?? "pending"}</div>
                </div>
                <div>
                  <div className="mono text-xs text-fg-muted">status</div>
                  <div className="text-sm">{assignment?.status ?? selectedResponder?.status ?? "--"}</div>
                </div>
                <div>
                  <div className="mono text-xs text-fg-muted">route</div>
                  <div className="truncate text-sm">{assignment?.route_id ?? "--"}</div>
                </div>
                <div>
                  <div className="mono text-xs text-fg-muted">leg</div>
                  <div className="truncate text-sm">{assignment?.leg_id ?? leg?.leg_id ?? "--"}</div>
                </div>
                <div>
                  <div className="mono text-xs text-fg-muted">ETA</div>
                  <div className="text-sm">{formatEta(etaSeconds)}</div>
                </div>
                <div>
                  <div className="mono text-xs text-fg-muted">distance</div>
                  <div className="text-sm">{formatDistance(distanceKm)}</div>
                </div>
              </div>
            ) : (
              <div className="mt-3 text-sm text-fg-secondary">No active assignment from backend.</div>
            )}
          </div>

          <div className="border border-border-strong bg-bg-base p-3">
            <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Location Ping</div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <label className="block">
                <span className="mono text-xs text-fg-muted">lat</span>
                <input
                  value={manualLat}
                  onChange={(event) => setManualLat(event.target.value)}
                  inputMode="decimal"
                  className="mt-1 w-full border border-border-strong bg-bg-panel px-2 py-2 text-sm"
                />
              </label>
              <label className="block">
                <span className="mono text-xs text-fg-muted">lng</span>
                <input
                  value={manualLng}
                  onChange={(event) => setManualLng(event.target.value)}
                  inputMode="decimal"
                  className="mt-1 w-full border border-border-strong bg-bg-panel px-2 py-2 text-sm"
                />
              </label>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <button
                disabled={sending || !selectedResponderId}
                onClick={sendBrowserLocation}
                className="mono border border-border-strong px-2 py-2 text-xs font-bold uppercase hover:bg-bg-elev disabled:opacity-40"
              >
                GPS
              </button>
              <button
                disabled={sending || !selectedResponderId}
                onClick={sendManualPing}
                className="mono border border-border-strong px-2 py-2 text-xs font-bold uppercase hover:bg-bg-elev disabled:opacity-40"
              >
                Manual
              </button>
              <button
                disabled={sending || !selectedResponderId}
                onClick={sendSimulatedPing}
                className="mono border border-status-good px-2 py-2 text-xs font-bold uppercase text-status-good hover:bg-bg-elev disabled:opacity-40"
              >
                Sim
              </button>
            </div>
            {message ? <div className="mono mt-3 text-xs text-status-warn">{message}</div> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
