// Thin fetch wrapper. All paths go through Next.js rewrite (/api/* -> backend:8000/*).

const BASE = "/api";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}

export const api = {
  // Incidents
  listIncidents: () => jsonFetch<import("./types").IncidentReport[]>("/incidents"),
  getIncident: (id: string) => jsonFetch<import("./types").IncidentReport>(`/incidents/${id}`),
  escalate: (id: string, severity: import("./types").Severity, reason: string) =>
    jsonFetch<import("./types").IncidentReport>(`/incidents/${id}/escalate`, {
      method: "POST",
      body: JSON.stringify({ severity, reason }),
    }),
  // Responders + routing
  optimize: () => jsonFetch<import("./types").RoutingResponse>("/routing/optimize", { method: "POST" }),
  roadAccess: () => jsonFetch<import("./types").RoadAccessSummary>("/routing/road-access"),
  blockedRoads: () => jsonFetch<import("./types").BlockedRoadsResponse>("/routing/blocked-roads"),
  startDispatch: (payload: import("./types").StartDispatchRequest) =>
    jsonFetch<import("./types").StartDispatchResponse>("/routing/dispatches/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  responderAssignment: (id: string) =>
    jsonFetch<import("./types").ResponderAssignment | null>(`/responders/${id}/assignment`).catch(() => null),
  completeResponderAssignment: (id: string, payload: import("./types").CompleteAssignmentRequest) =>
    jsonFetch<import("./types").CompleteAssignmentResponse>(`/responders/${id}/assignment/complete`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateResponderLocation: (id: string, ping: import("./types").ResponderLocationPing) =>
    jsonFetch<import("./types").ResponderLocationResponse>(`/responders/${id}/location`, {
      method: "POST",
      body: JSON.stringify(ping),
    }),
  // Snowflake tiles
  tile: (name: string) => jsonFetch<{ tile: string; source: string; rows: any[] }>(`/snowflake/tile/${name}`),
  // Cortex
  cortexScan: () => jsonFetch<{ alerts: any[]; emitted_count: number }>(`/cortex/scan`, { method: "POST" }),
  // Sim
  simStart: (count = 200, demo_window_s = 60) =>
    jsonFetch(`/sim/start`, {
      method: "POST",
      body: JSON.stringify({ count, demo_window_s, run_id: `run-${Date.now()}` }),
    }),
  simStop: () => jsonFetch(`/sim/stop`, { method: "POST" }),
  // Demo
  seedResponders: () => jsonFetch(`/demo/seed-responders`, { method: "POST" }),
  reset: () => jsonFetch(`/demo/reset`, { method: "POST" }),
  triggerCall: (scenario: string) =>
    jsonFetch(`/demo/trigger-call?scenario=${scenario}`, { method: "POST" }),
  scenarios: () => jsonFetch<{ scenarios: Array<{ key: string; location_hint: string; preview: string }> }>(`/demo/scenarios`),
  responders: () => jsonFetch<import("./types").ResponderUnit[]>("/responders").catch(() => []),
};
