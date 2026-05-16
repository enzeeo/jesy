// Mirrors IncidentReport from src/disaster/models/incident.py.
// Keep in sync — when the pydantic model changes, update here too.

export type Severity = "Immediate" | "Delayed" | "Minor" | "Deceased";
export type IncidentStatus = "new" | "dispatched" | "en_route" | "on_scene" | "resolved" | "partial";
export type IncidentSource = "voice" | "simulated" | "manual";

export interface Location {
  lat: number;
  lng: number;
  description: string;
}

export interface Victim {
  age_estimate?: number | null;
  injuries: string[];
  consciousness: string;
  breathing: string;
  respiratory_rate?: number | null;
  perfusion: string;
  mobility: string;
  vulnerabilities: string[];
}

export interface IncidentReport {
  id: string;
  timestamp: string;
  source: IncidentSource;
  status: IncidentStatus;
  location: Location;
  victims: Victim[];
  severity: Severity;
  priority_score: number;
  call_transcript: string;
  confidence: number;
  sim_run_id?: string | null;
}

export type ResponderType = "ALS" | "BLS" | "Fire" | "Rescue";
export type ResponderStatus = "idle" | "assigned" | "en_route" | "on_scene" | "out_of_service";

export interface ResponderUnit {
  id: string;
  callsign: string;
  type: ResponderType;
  location: Location;
  status: ResponderStatus;
  assigned_incident_id?: string | null;
}

export interface SSEEvent<T = unknown> {
  type: string;
  data: T;
  sequence_id?: number;
}

export interface SeverityUpgradedData {
  incident_id: string;
  from: Severity;
  to: Severity;
  reason: string;
}

export interface CortexAlertData {
  type: string;
  injury_bucket: string;
  sector: string;
  count: number;
  window_minutes: number;
  message: string;
}
