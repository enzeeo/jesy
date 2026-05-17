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
  actual_eta_p50_seconds: number | null;
  actual_eta_p90_seconds: number | null;
  eta_actual_vs_estimated_p50_delta_seconds: number | null;
  actuals_coverage_pct: number;
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
  solver_mix: Record<string, number> | null;
  elapsed_ms_p50: number | null;
  elapsed_ms_p90: number | null;
  degraded_leg_pct: number | null;
  provider_status: string | null;
  optimization_count: number | null;
}

export interface RoadAccessContext {
  feature_count: number;
  hard_avoid_count: number;
  soft_penalty_count: number;
  provider: string | null;
  loaded_at: string | null;
}

export interface CortexAlertEvent {
  alert_id: string;
  alert_type: string;
  severity: string;
  message: string | null;
  detected_at: string;
  sector_id: string | null;
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
  road_access_context: RoadAccessContext | null;
  cortex_alerts: CortexAlertEvent[];
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

// Signed delta with leading sign — "+12s slower" or "−4s faster" feels too
// chatty for a tile, so this just emits "+12s" / "-4s". Caller adds context.
export function formatSignedSeconds(s: number | null | undefined): string {
  if (s == null) return "—";
  if (Math.abs(s) < 1) return "±0s";
  const sign = s > 0 ? "+" : "−";
  return `${sign}${formatSeconds(Math.abs(s))}`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatSolverMix(mix: Record<string, number> | null | undefined): string {
  if (!mix) return "—";
  const entries = Object.entries(mix).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return "—";
  return entries.map(([k, v]) => `${k}×${v}`).join(" · ");
}

// Pretty class names for the UI (avoid showing "medical_dependency")
export const VULN_CLASS_LABELS: Record<string, string> = {
  elderly: "Elderly",
  child: "Children",
  disabled: "Disabled",
  medical_dependency: "Medical-dependent",
};
