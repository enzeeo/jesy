"use client";
import type { AARScorecard } from "@/lib/aar";
import { formatPercent, formatSeconds, formatSignedSeconds } from "@/lib/aar";

interface Props { scorecard: AARScorecard }

interface TileProps {
  label: string;
  value: string;
  sub?: string;
  emphasis?: "default" | "warn" | "good";
}

function Tile({ label, value, sub, emphasis = "default" }: TileProps) {
  const color =
    emphasis === "warn" ? "text-status-warn" :
    emphasis === "good" ? "text-status-good" :
    "text-fg-primary";
  return (
    <div className="border border-border-strong bg-bg-panel p-4 flex flex-col justify-between min-h-[110px]">
      <div className="text-[10px] uppercase tracking-wider text-fg-muted">{label}</div>
      <div className={`mono text-3xl font-bold ${color}`}>{value}</div>
      {sub && <div className="mono text-xs text-fg-secondary">{sub}</div>}
    </div>
  );
}

// Below this coverage, the median actual-vs-estimated delta is too noisy to
// trust — the server suppresses the field but we hide the tile entirely too.
const MIN_DELTA_COVERAGE = 0.30;

export function Scorecard({ scorecard: s }: Props) {
  const vulnGapSeconds =
    s.vulnerable_eta_p50_seconds != null && s.p50_eta_seconds != null
      ? s.vulnerable_eta_p50_seconds - s.p50_eta_seconds
      : null;
  const vulnEmphasis: TileProps["emphasis"] =
    vulnGapSeconds == null ? "default" :
    vulnGapSeconds > 60 ? "warn" : "default";

  const hasActuals = s.actuals_coverage_pct > 0 && s.actual_eta_p50_seconds != null;
  const delta = s.eta_actual_vs_estimated_p50_delta_seconds;
  const showDelta = s.actuals_coverage_pct >= MIN_DELTA_COVERAGE && delta != null;
  const deltaEmphasis: TileProps["emphasis"] =
    !showDelta ? "default" :
    (delta ?? 0) > 30 ? "warn" :
    (delta ?? 0) < -10 ? "good" : "default";

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-5 gap-2">
        <Tile
          label="Incidents"
          value={s.incident_count.toString()}
          sub={`${s.assigned_count} assigned (${formatPercent(s.assigned_pct)})`}
        />
        <Tile
          label="Response p50 (est.)"
          value={formatSeconds(s.p50_eta_seconds)}
          sub={`p90 ${formatSeconds(s.p90_eta_seconds)}`}
        />
        <Tile
          label="Vulnerable victims"
          value={`${s.vulnerable_assigned_count}/${s.vulnerable_incident_count}`}
          sub={`p50 ETA ${formatSeconds(s.vulnerable_eta_p50_seconds)}`}
        />
        <Tile
          label="Vuln gap vs general"
          value={vulnGapSeconds == null ? "—" : `${vulnGapSeconds > 0 ? "+" : ""}${formatSeconds(Math.abs(vulnGapSeconds))}`}
          sub={vulnGapSeconds != null && vulnGapSeconds > 60 ? "Slower than general pop" : "Within parity"}
          emphasis={vulnEmphasis}
        />
        <Tile
          label="Intake quality"
          value={s.extraction_confidence_p50 != null ? `${(s.extraction_confidence_p50 * 100).toFixed(0)}%` : "—"}
          sub="median voice extraction confidence"
          emphasis={s.extraction_confidence_p50 != null && s.extraction_confidence_p50 < 0.7 ? "warn" : "default"}
        />
      </div>
      {hasActuals && (
        <div className="grid grid-cols-5 gap-2">
          <Tile
            label="Actual p50 arrival"
            value={formatSeconds(s.actual_eta_p50_seconds)}
            sub={`p90 ${formatSeconds(s.actual_eta_p90_seconds)} · ${formatPercent(s.actuals_coverage_pct)} coverage`}
            emphasis="good"
          />
          {showDelta ? (
            <Tile
              label="Actual − estimated"
              value={formatSignedSeconds(delta)}
              sub={(delta ?? 0) > 30 ? "Slower than dispatch estimated" : (delta ?? 0) < -10 ? "Faster than estimated" : "Tracking estimate"}
              emphasis={deltaEmphasis}
            />
          ) : (
            <Tile
              label="Actual − estimated"
              value="—"
              sub={`${formatPercent(s.actuals_coverage_pct)} coverage · need ${formatPercent(MIN_DELTA_COVERAGE)} for delta`}
            />
          )}
          <Tile
            label="Fleet distance"
            value={s.total_fleet_distance_km > 0 ? `${s.total_fleet_distance_km.toFixed(1)}km` : "—"}
            sub="summed across real solver runs"
          />
          <div className="col-span-2 border border-border-strong bg-bg-panel p-4 flex flex-col justify-center text-[11px] text-fg-secondary leading-relaxed">
            <span className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">Sourcing</span>
            <span>
              Top row uses estimated ETAs (same yardstick as counterfactual replays).
              This row reflects what actually happened — wheels-on-scene timestamps
              from responder ping data.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
