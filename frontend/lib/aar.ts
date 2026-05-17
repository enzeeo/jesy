// AAR types. Mirror src/disaster/analysis/models.py.
// Keep in sync — when AARResponse changes server-side, update here too.

export interface AARScorecard {
  incident_count: number;
  assigned_count: number;
  assigned_pct: number;
  p50_eta_seconds: number | null;
  p90_eta_seconds: number | null;
  total_fleet_distance_km: number;
  vulnerable_incident_count: number;
  vulnerable_assigned_count: number;
  vulnerable_eta_p50_seconds: number | null;
  extraction_confidence_p50: number | null;
}

export interface PolicyResult {
  key: string;
  label: string;
  is_actual: boolean;
  assigned_count: number;
  total_fleet_distance_km: number;
  p50_eta_seconds: number | null;
  p90_eta_seconds: number | null;
  vulnerable_assigned_count: number;
  vulnerable_eta_p50_seconds: number | null;
  error: string | null;
}

export interface CounterfactualPanel {
  actual: PolicyResult;
  policies: PolicyResult[];
  winner_by_assignment: string | null;
  winner_by_vulnerable_eta: string | null;
}

export interface VulnerabilityBreakdown {
  class_name: string;
  incident_count: number;
  assigned_count: number;
  p50_eta_seconds: number | null;
  p90_eta_seconds: number | null;
  eta_gap_vs_baseline_seconds: number;
}

export interface TimelineSlice {
  t_seconds: number;
  incidents_total: number;
  incidents_assigned: number;
}

export interface IncidentGeoPoint {
  id: string;
  lat: number;
  lng: number;
  timestamp: string;
  severity: string;
  eta_seconds: number | null;
  has_vulnerable: boolean;
}

export interface LessonItem {
  headline: string;
  rationale: string;
  metric_citations: string[];
}

export interface NarrativeResponse {
  narrative: string;
  lessons: LessonItem[];
  source: "openai" | "fallback";
}

export interface AARResponse {
  sim_run_id: string;
  started_at: string | null;
  ended_at: string | null;
  is_live: boolean;
  badge: string | null;
  scorecard: AARScorecard;
  counterfactual: CounterfactualPanel | null;
  vulnerability: VulnerabilityBreakdown[];
  timeline: TimelineSlice[];
  incidents_geo: IncidentGeoPoint[];
  data_source: "snowflake" | "in_memory";
}

export interface RunSummary {
  sim_run_id: string;
  started_at: string;
  ended_at: string;
  incident_count: number;
  is_active: boolean;
}

// ── Formatters ──────────────────────────────────────────────────────────────

export function formatSeconds(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = s / 60;
  if (m < 10) return `${m.toFixed(1)}min`;
  return `${m.toFixed(0)}min`;
}

export function formatPercent(p: number | null | undefined): string {
  if (p == null) return "—";
  return `${Math.round(p * 100)}%`;
}

export function formatKm(km: number | null | undefined): string {
  if (km == null) return "—";
  return `${km.toFixed(1)}km`;
}

export function formatVulnGap(s: number): string {
  if (Math.abs(s) < 1) return "±0s";
  const sign = s > 0 ? "+" : "";
  return `${sign}${formatSeconds(Math.abs(s)).replace(/^/, s > 0 ? "" : "-")}`;
}

// Pretty class names for the UI (avoid showing "medical_dependency")
export const VULN_CLASS_LABELS: Record<string, string> = {
  elderly: "Elderly",
  child: "Children",
  disabled: "Disabled",
  medical_dependency: "Medical-dependent",
};
