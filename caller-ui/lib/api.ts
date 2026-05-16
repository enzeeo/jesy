import type {
  CallerStatusView,
  CallerSubmitInput,
  IncidentCategory,
  IncidentReport,
  Severity,
  Victim,
} from "@/lib/types";

const BASE = "/api";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return (await response.json()) as T;
}

function selectedLabels<T extends string>(values: Partial<Record<T, boolean>>, labels: Record<T, string>): string[] {
  return Object.entries(values)
    .filter(([, selected]) => Boolean(selected))
    .map(([key]) => labels[key as T]);
}

const categoryLabels: Record<IncidentCategory, string> = {
  medical: "medical help",
  trapped: "trapped",
  fire: "fire",
  water: "water or flooding",
  shelter: "shelter",
  power: "power outage",
  evacuation: "evacuation",
  unknown: "other help",
};

function buildTranscript(input: CallerSubmitInput): string {
  const lines = [input.raw_text.trim()];
  const needs = selectedLabels(input.needs, categoryLabels);
  if (needs.length > 0) lines.push(`Selected needs: ${needs.join(", ")}.`);
  if (input.inventory_have.length > 0) lines.push(`Caller has: ${input.inventory_have.join(", ")}.`);
  if (input.inventory_need.length > 0) lines.push(`Caller needs supplies: ${input.inventory_need.join(", ")}.`);
  if (input.location.source === "manual") lines.push(`Manual location description: ${input.location.description}.`);
  return lines.join("\n");
}

function buildVictim(input: CallerSubmitInput): Victim {
  const needs = new Set(Object.entries(input.needs).filter(([, selected]) => selected).map(([key]) => key));
  const vulnerabilities: string[] = [...input.inventory_have, ...input.inventory_need];
  if (needs.has("water") || needs.has("trapped") || needs.has("evacuation")) vulnerabilities.push("mobility_dependent");
  if (needs.has("medical")) vulnerabilities.push("medical_dependency");

  return {
    injuries: needs.has("medical") ? ["caller requested medical help"] : [],
    consciousness: "unknown",
    breathing: needs.has("medical") ? "spontaneous" : "unknown",
    respiratory_rate: null,
    perfusion: "unknown",
    mobility: needs.has("trapped") ? "cannot_follow_commands" : "unknown",
    vulnerabilities,
  };
}

function buildIncidentPayload(input: CallerSubmitInput) {
  return {
    timestamp: input.timestamp,
    source: "manual",
    location: {
      lat: input.location.lat,
      lng: input.location.lng,
      description: input.location.description,
    },
    caller: {
      phone_hash: input.device_id,
      callback_available: false,
    },
    victims: [buildVictim(input)],
    call_transcript: buildTranscript(input),
    confidence: input.location.source === "gps" ? 0.9 : 0.45,
  };
}

function severityToScore(severity: Severity): number {
  switch (severity) {
    case "Immediate":
      return 90;
    case "Delayed":
      return 55;
    case "Minor":
      return 25;
    case "Deceased":
      return 10;
    default: {
      const exhaustive: never = severity;
      return exhaustive;
    }
  }
}

export function incidentToCallerStatus(incident: IncidentReport): CallerStatusView {
  if (incident.status === "partial" || incident.confidence < 0.5) {
    return {
      incident_id: incident.id,
      state: "low_confidence_location",
      title: "We received your request",
      message: "Your location details were saved. Keep this screen open while responders review it.",
      severity_score: severityToScore(incident.severity),
    };
  }

  if (incident.status === "dispatched" || incident.status === "en_route" || incident.status === "on_scene") {
    return {
      incident_id: incident.id,
      state: "assigned",
      title: "Help is being coordinated",
      message: "Responders can see your request. Stay where it is safe and keep your phone nearby.",
      severity_score: severityToScore(incident.severity),
    };
  }

  return {
    incident_id: incident.id,
    state: "received",
    title: "Help request received",
    message: "We are reading your message and matching the right help.",
    severity_score: severityToScore(incident.severity),
  };
}

export const api = {
  createIncident: async (input: CallerSubmitInput) => {
    const incident = await jsonFetch<IncidentReport>("/incidents", {
      method: "POST",
      body: JSON.stringify(buildIncidentPayload(input)),
    });
    return { incident_id: incident.id, incident };
  },
  getIncident: (id: string) => jsonFetch<IncidentReport>(`/incidents/${id}`),
};
