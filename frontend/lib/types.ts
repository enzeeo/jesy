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

export interface RouteLineString {
  type: "LineString";
  coordinates: [number, number][];
}

export interface RoadAccessPolygon {
  type: "Polygon";
  coordinates: [number, number][][] | number[][][];
}

export interface RoadAccessMultiPolygon {
  type: "MultiPolygon";
  coordinates: [number, number][][][] | number[][][][];
}

export interface RoadAccessLineString {
  type: "LineString";
  coordinates: [number, number][] | number[][];
}

export interface RoadAccessMultiLineString {
  type: "MultiLineString";
  coordinates: [number, number][][] | number[][][];
}

export interface RoadAccessFeature {
  type: "Feature";
  geometry: RoadAccessPolygon | RoadAccessMultiPolygon | RoadAccessLineString | RoadAccessMultiLineString;
  properties?: Record<string, string | number | boolean | null>;
}

export interface RoadAccessFeatureCollection {
  type: "FeatureCollection";
  metadata?: {
    road_access_id?: string;
    source?: string;
    version?: string;
    loaded_at?: string;
    source_urls?: string[];
  };
  features: RoadAccessFeature[];
}

export interface RoadAccessSummary {
  feature_count?: number;
  hard_avoid_count?: number;
  soft_penalty_count?: number;
  status_counts?: Record<string, number>;
  road_access_id?: string;
  source?: string;
  version?: string;
  loaded_at?: string;
  source_urls?: string[];
  provider?: string;
  avoidance_strategy?: string;
  features?: RoadAccessFeature[];
  feature_collection?: RoadAccessFeatureCollection;
  type?: "FeatureCollection";
}

export interface BlockedRoad {
  label: string;
  road_status: string;
  confidence?: number | null;
  geometry: RoadAccessFeature["geometry"] | null;
}

export interface BlockedRoadsResponse {
  blocked_count: number;
  hard_avoid_count: number;
  blocked_roads: BlockedRoad[];
  feature_collection: RoadAccessFeatureCollection;
}

export interface RouteLeg {
  leg_id?: string | null;
  target_id?: string | null;
  target_type?: "incident" | "cluster" | string | null;
  incident_id?: string | null;
  from_location: Location;
  to_location: Location;
  distance_km: number;
  eta_seconds: number;
  arrival_seconds?: number | null;
  route_geometry?: RouteLineString | null;
  degraded?: boolean;
  provider_status?: string | null;
  warnings?: string[];
  assignment_reason?: string | null;
}

export interface RoutingResponse {
  route_id?: string | null;
  solver: string;
  elapsed_ms: number;
  unassigned: string[];
  road_access?: RoadAccessSummary | RoadAccessFeatureCollection | null;
  routes: Record<string, RouteLeg[]>;
}

export interface StartDispatchRequest {
  route_id: string;
  leg_id: string;
  started_by: string;
}

export interface StartDispatchResponse {
  dispatch_id?: string;
  route_id?: string;
  leg_id?: string;
  responder_id?: string;
  incident_id?: string;
  route_leg?: RouteLeg;
  assignment?: ResponderAssignment;
  responder?: ResponderUnit;
  responders?: ResponderUnit[];
  incident?: IncidentReport;
  incidents?: IncidentReport[];
  routing_response?: RoutingResponse;
  status?: string;
}

export interface CompleteAssignmentRequest {
  completed_by: string;
}

export interface CompleteAssignmentResponse {
  assignment_id?: string;
  route_id?: string;
  leg_id?: string;
  responder_id?: string;
  incident_id?: string;
  status?: string;
  completed_by?: string;
  responder?: ResponderUnit;
  incident?: IncidentReport;
}

export interface ResponderLocationPing {
  lat: number;
  lng: number;
  accuracy_m: number;
  timestamp: string;
  speed_mps?: number | null;
  heading?: number | null;
}

export interface ResponderLocationResponse {
  responder_id: string;
  arrival_detected: boolean;
  incident_id?: string | null;
  distance_m?: number;
  detection_method?: string;
  warning?: string;
}

export interface ResponderAssignment {
  responder_id?: string;
  route_id?: string | null;
  leg_id?: string | null;
  assignment_id?: string | null;
  incident_id?: string | null;
  status?: string | null;
  eta_seconds?: number | null;
  distance_km?: number | null;
  route_leg?: RouteLeg | null;
  leg?: RouteLeg | null;
  responder?: ResponderUnit | null;
  incident?: IncidentReport | null;
  route_progress?: number | null;
  remaining_route_geometry?: RouteLineString | null;
}

export interface ActiveResponderAssignment extends ResponderAssignment {
  responder_id: string;
  route_id: string;
  leg_id: string;
  assignment_id: string;
  incident_id: string;
  status: string;
  route_leg: RouteLeg;
  leg: RouteLeg;
  responder: ResponderUnit;
  incident: IncidentReport;
}

export type ResponderLocationUpdatedData =
  | ResponderUnit
  | {
      responder_id?: string;
      responder: ResponderUnit;
      callsign?: string;
      status?: ResponderStatus;
      location?: Location;
      accuracy_m?: number;
      timestamp?: string;
      speed_mps?: number | null;
      heading?: number | null;
      assignment?: ResponderAssignment | null;
      route_progress?: number | null;
      remaining_route_geometry?: RouteLineString | null;
    };

export interface DispatchStartedData {
  dispatch_id?: string;
  route_id?: string;
  leg_id?: string;
  responder_id?: string;
  incident_id?: string;
  responder?: ResponderUnit;
  assignment?: ResponderAssignment;
}

export interface DispatchCompletedData extends CompleteAssignmentResponse {}

export interface ResponderArrivedData {
  responder_id: string;
  incident_id: string;
  location: Location;
  responder?: ResponderUnit;
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
  from_priority?: number;
  to_priority?: number;
  reason: string;
}

export interface CortexReassessResponse {
  incident: IncidentReport;
  source: "snowflake" | "heuristic";
  reason: string;
  changed: boolean;
  previous: { severity: Severity; priority_score: number };
}

export interface SnowflakeTileResponse {
  tile: string;
  source: string;
  rows: unknown[];
}

export type AgentOpsSeverity = "info" | "warning" | "critical" | string;

export interface AgentOpsCard {
  run_id: string;
  agent_name: string;
  severity: AgentOpsSeverity;
  title: string;
  summary: string;
  recommendation: string;
  evidence: Record<string, unknown>[];
  timestamp: string;
  source: string;
}

export interface AgentOpsResponse {
  source: string;
  generated_at: string;
  cards: AgentOpsCard[];
}

export interface ChatSourceRef {
  query_id: string;
  tables: string[];
  row_count: number;
}

export interface ChatMessage {
  role: "user" | "assistant" | string;
  content: string;
  sources: ChatSourceRef[];
  warehouse_backed: boolean;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  scope: "global" | "incident" | "sector" | "cluster";
  scope_ref_id: string | null;
  title: string;
  created_at: string;
  messages: ChatMessage[];
}

export interface ChatPostMessageResponse {
  reply: {
    content: string;
    sources: ChatSourceRef[];
    warehouse_backed: boolean;
  };
  session: ChatSession;
}

export interface CortexAlertData {
  type: string;
  injury_bucket: string;
  sector: string;
  count: number;
  window_minutes: number;
  message: string;
}
