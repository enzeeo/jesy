"use client";
import type { AARScorecard } from "@/lib/aar";
import { formatPercent, formatSeconds } from "@/lib/aar";

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

export function Scorecard({ scorecard: s }: Props) {
  const vulnGapSeconds =
    s.vulnerable_eta_p50_seconds != null && s.p50_eta_seconds != null
      ? s.vulnerable_eta_p50_seconds - s.p50_eta_seconds
      : null;
  const vulnEmphasis: TileProps["emphasis"] =
    vulnGapSeconds == null ? "default" :
    vulnGapSeconds > 60 ? "warn" : "default";

  return (
    <div className="grid grid-cols-5 gap-2">
      <Tile
        label="Incidents"
        value={s.incident_count.toString()}
        sub={`${s.assigned_count} assigned (${formatPercent(s.assigned_pct)})`}
      />
      <Tile
        label="Response p50"
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
  );
}
