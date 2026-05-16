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

export interface Caller {
  phone_hash: string;
  callback_available: boolean;
}

export interface IncidentReport {
  id: string;
  timestamp: string;
  source: IncidentSource;
  status: IncidentStatus;
  location: Location;
  caller?: Caller | null;
  victims: Victim[];
  severity: Severity;
  priority_score: number;
  call_transcript: string;
  confidence: number;
  sim_run_id?: string | null;
}

export type IncidentCategory =
  | "medical"
  | "trapped"
  | "fire"
  | "water"
  | "shelter"
  | "power"
  | "evacuation"
  | "unknown";

export type DeviceFlag =
  | "epipen"
  | "inhaler"
  | "insulin"
  | "first_aid"
  | "mobility_aid"
  | "oxygen"
  | "aed";

export interface CallerProfile {
  name: string;
  age: number | null;
  conditions: string[];
  devices_owned: DeviceFlag[];
  emergency_contact?: { name: string; phone: string };
}

export interface CallerDraft {
  raw_text: string;
  needs: Partial<Record<IncidentCategory, boolean>>;
  inventory_have: DeviceFlag[];
  inventory_need: DeviceFlag[];
}

export interface CallerSubmitInput extends CallerDraft {
  device_id: string;
  timestamp: string;
  location: {
    lat: number;
    lng: number;
    description: string;
    source: "gps" | "manual";
  };
}

export interface CallerStatusView {
  incident_id: string;
  state: "received" | "triaging" | "assigned" | "low_confidence_location";
  title: string;
  message: string;
  severity_score?: number;
}

export const INCIDENT_CATEGORIES: IncidentCategory[] = [
  "medical",
  "trapped",
  "fire",
  "water",
  "shelter",
  "power",
  "evacuation",
  "unknown",
];

export const DEVICE_FLAGS: DeviceFlag[] = [
  "epipen",
  "inhaler",
  "insulin",
  "first_aid",
  "mobility_aid",
  "oxygen",
  "aed",
];
