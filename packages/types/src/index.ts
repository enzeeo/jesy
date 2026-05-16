// =============================================================
// @disaster/types — shared domain contract
// All apps + API + fixtures import from here. Do not define
// domain types inline anywhere else in this repo.
// =============================================================

export type ResourceType =
  | 'police'
  | 'fire'
  | 'ems'
  | 'paramedic'
  | 'nurse'
  | 'doctor'
  | 'volunteer';

export type IncidentCategory =
  | 'medical'
  | 'trapped'
  | 'fire'
  | 'water'
  | 'shelter'
  | 'power'
  | 'evacuation'
  | 'unknown';

export type DeviceFlag =
  | 'epipen'
  | 'inhaler'
  | 'insulin'
  | 'first_aid'
  | 'mobility_aid'
  | 'oxygen'
  | 'aed';

export interface Profile {
  profile_id: string;
  device_id: string;
  name: string;
  age: number;
  conditions: string[];
  devices_owned: DeviceFlag[];
  emergency_contact?: { name: string; phone: string };
  created_at: string;
}

export interface IncidentLocation {
  lat: number;
  lng: number;
  accuracy_m?: number;
  source: 'gps' | 'place_description_udf' | 'manual';
  confidence?: number;
  description?: string;
}

export interface IncidentRaw {
  incident_id: string;
  profile_id?: string;
  device_id: string;
  location: IncidentLocation;
  raw_text: string;
  needs: Partial<Record<IncidentCategory, boolean>>;
  inventory_have: DeviceFlag[];
  inventory_need: DeviceFlag[];
  ts: string;
}

export interface SeverityResult {
  score: number; // 0..100
  category: IncidentCategory;
  top_reasons: [string, string, string];
  required_resources: Partial<Record<ResourceType, number>>;
  confidence: number; // 0..1
}

export interface IncidentEnriched extends IncidentRaw {
  severity: SeverityResult;
  triage_status: 'ok' | 'degraded';
  summary: string;
  cluster_id?: string;
  primary_of_duplicate_group?: string;
  status: 'open' | 'assigned' | 'in_progress' | 'resolved';
  /** Snapshot of victim profile at submit time. Optional. */
  profile_snapshot?: Profile;
}

export interface Responder {
  responder_id: string;
  type: ResourceType;
  callsign: string;
  current_location?: { lat: number; lng: number };
  status: 'available' | 'busy' | 'offline';
}

export interface Assignment {
  assignment_id: string;
  incident_id: string;
  responder_id: string;
  resource_type: ResourceType;
  eta_sec: number;
  polyline?: string;
  status: 'enroute' | 'on_scene' | 'completed';
  assigned_at: string;
}

export interface UnmetResourceNeed {
  incident_id: string;
  resource_type: ResourceType;
  quantity_needed: number;
  reason: 'no_available_responder' | 'responder_offline';
}

export interface ClusterView {
  cluster_id: string;
  centroid: { lat: number; lng: number };
  incident_ids: string[];
  total_severity: number;
  category_breakdown: Partial<Record<IncidentCategory, number>>;
}

export interface ResourceRoster {
  type: ResourceType;
  total: number;
  available: number;
  busy: number;
}

export interface RoutePreview {
  responder_id: string;
  assignment_ids: string[];
  stops: Array<{
    incident_id: string;
    eta_sec: number;
    order: number;
  }>;
  polyline?: string;
  total_eta_sec: number;
  route_source: 'mapbox' | 'cached' | 'fallback';
}

export interface ScenarioState {
  name: string;
  label: string;
  elapsed_sec: number;
  status: 'idle' | 'running' | 'paused' | 'complete';
}

export interface DashboardState {
  mode: 'fixture' | 'live';
  scenario?: ScenarioState;
  incidents: IncidentEnriched[];
  clusters: ClusterView[];
  assignments: Assignment[];
  unmet_resource_needs: UnmetResourceNeed[];
  routes: RoutePreview[];
  roster: ResourceRoster[];
  responders: Responder[];
}

export interface VictimStatusView {
  incident_id: string;
  state:
    | 'received'
    | 'triaging'
    | 'assigned'
    | 'low_confidence_location'
    | 'unmet_resource';
  message: string;
  eta_sec?: number;
  assigned_resource_types?: ResourceType[];
  location_confidence?: number;
  severity_score?: number;
  category?: IncidentCategory;
}

// =============================================================
// Fixture / scenario timeline
// =============================================================

export interface FixtureTimelineEvent {
  at_sec: number;
  type:
    | 'incident_new'
    | 'incident_update'
    | 'cluster_update'
    | 'assignment_new'
    | 'route_update'
    | 'resource_update'
    | 'victim_status_update';
  payload: unknown;
}

// =============================================================
// SSE envelope
// =============================================================

export type SSEEvent =
  | { type: 'incident_new'; data: IncidentEnriched }
  | { type: 'incident_update'; data: IncidentEnriched }
  | { type: 'cluster_update'; data: ClusterView }
  | { type: 'assignment_new'; data: Assignment }
  | { type: 'route_update'; data: RoutePreview }
  | { type: 'resource_update'; data: ResourceRoster[] };

// =============================================================
// Helpers for UI (kept tiny — pure data only)
// =============================================================

/** Color bucket for a severity score. UI maps these to tokens. */
export type SeverityBand = 'critical' | 'high' | 'medium' | 'low' | 'info';

export function severityBand(score: number): SeverityBand {
  if (score >= 90) return 'critical';
  if (score >= 75) return 'high';
  if (score >= 50) return 'medium';
  if (score >= 25) return 'low';
  return 'info';
}

export const RESOURCE_TYPES: ResourceType[] = [
  'police',
  'fire',
  'ems',
  'paramedic',
  'nurse',
  'doctor',
  'volunteer',
];

export const INCIDENT_CATEGORIES: IncidentCategory[] = [
  'medical',
  'trapped',
  'fire',
  'water',
  'shelter',
  'power',
  'evacuation',
  'unknown',
];

export const DEVICE_FLAGS: DeviceFlag[] = [
  'epipen',
  'inhaler',
  'insulin',
  'first_aid',
  'mobility_aid',
  'oxygen',
  'aed',
];
