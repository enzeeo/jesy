// Thin fetch wrapper. All paths go through Next.js rewrite (/api/* -> backend:8000/*).

const BASE = "/api";

// Backend base URL for endpoints that bypass the Next.js rewrite. The dev
// rewrite proxies via Node fetch with a ~30s timeout, which breaks long-
// running endpoints (/routing/optimize takes 60-90s under Mapbox load).
// SSE already bypasses for the same reason (see lib/useSSE.ts).
const DIRECT_BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";

async function jsonFetch<T>(
  path: string,
  init?: RequestInit & { direct?: boolean },
): Promise<T> {
  const { direct, ...fetchInit } = init ?? {};
  const url = direct && DIRECT_BACKEND ? `${DIRECT_BACKEND}${path}` : `${BASE}${path}`;
  const res = await fetch(url, {
    ...fetchInit,
    headers: { "Content-Type": "application/json", ...(fetchInit?.headers || {}) },
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
  optimize: () => jsonFetch<import("./types").RoutingResponse>("/routing/optimize", { method: "POST", direct: true }),
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
  cortexReassess: (id: string) =>
    jsonFetch<import("./types").CortexReassessResponse>(`/cortex/reassess/${id}`, { method: "POST" }),
  // Dispatch chat
  createChatSession: (body: {
    scope?: "global" | "incident" | "sector" | "cluster";
    scope_ref_id?: string;
    title?: string;
  }) =>
    jsonFetch<import("./types").ChatSession>("/chat/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  postChatMessage: (
    sessionId: string,
    body: {
      message: string;
      context?: { incident_id?: string; sector?: string; cluster_id?: string };
    },
  ) =>
    jsonFetch<import("./types").ChatPostMessageResponse>(
      `/chat/sessions/${sessionId}/messages`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  // Sim
  simStart: (count = 200, demo_window_s = 60, road_access_source = "helene_cached") =>
    jsonFetch(`/sim/start`, {
      method: "POST",
      body: JSON.stringify({ count, demo_window_s, road_access_source, run_id: `run-${Date.now()}` }),
    }),
  simStop: () => jsonFetch(`/sim/stop`, { method: "POST" }),
  // Demo
  seedResponders: () => jsonFetch(`/demo/seed-responders`, { method: "POST" }),
  reset: () => jsonFetch(`/demo/reset`, { method: "POST" }),
  triggerCall: (scenario: string) =>
    jsonFetch(`/demo/trigger-call?scenario=${scenario}`, { method: "POST" }),
  scenarios: () => jsonFetch<{ scenarios: Array<{ key: string; location_hint: string; preview: string }> }>(`/demo/scenarios`),
  responders: () => jsonFetch<import("./types").ResponderUnit[]>("/responders").catch(() => []),
  // AAR
  aar: (simRunId: string) => jsonFetch<import("./aar").AARResponse>(`/api/analysis/${encodeURIComponent(simRunId)}`),
  aarNarrative: (simRunId: string) => jsonFetch<import("./aar").NarrativeResponse>(`/api/analysis/${encodeURIComponent(simRunId)}/narrative`),
  aarRuns: () => jsonFetch<{ runs: import("./aar").RunSummary[] }>("/api/analysis/runs"),
};
