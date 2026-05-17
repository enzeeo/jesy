"use client";
import type { CounterfactualPanel as CP, PolicyResult } from "@/lib/aar";
import { formatKm, formatSeconds } from "@/lib/aar";

interface Props { panel: CP }

function PolicyColumn({ p, highlight }: { p: PolicyResult; highlight: boolean }) {
  const border = p.is_actual
    ? "border-fg-primary"
    : highlight
    ? "border-status-good"
    : "border-border-strong";
  const bg = p.is_actual ? "bg-bg-elev" : "bg-bg-panel";
  const tag = p.is_actual ? "ACTUAL" : highlight ? "BEST" : "REPLAY";
  const tagColor = p.is_actual ? "text-fg-primary" : highlight ? "text-status-good" : "text-fg-muted";

  if (p.error) {
    return (
      <div className={`border-2 ${border} ${bg} p-4 flex flex-col gap-2 min-h-[200px]`}>
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-wider text-fg-muted">{p.label}</span>
          <span className={`mono text-[10px] uppercase ${tagColor}`}>ERROR</span>
        </div>
        <div className="mono text-2xl text-status-warn flex-1 flex items-center" title={p.error}>—</div>
        <div className="mono text-xs text-status-warn">{p.error}</div>
      </div>
    );
  }

  return (
    <div className={`border-2 ${border} ${bg} p-4 flex flex-col gap-2 min-h-[200px]`}>
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-wider text-fg-muted">{p.label}</span>
        <span className={`mono text-[10px] uppercase ${tagColor}`}>{tag}</span>
      </div>
      <div>
        <div className="mono text-3xl font-bold text-fg-primary">{p.assigned_count}</div>
        <div className="text-[10px] text-fg-muted">assigned</div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-[10px] uppercase text-fg-muted">p50 ETA</div>
          <div className="mono text-fg-primary">{formatSeconds(p.p50_eta_seconds)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-fg-muted">p90 ETA</div>
          <div className="mono text-fg-primary">{formatSeconds(p.p90_eta_seconds)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-fg-muted">vuln p50</div>
          <div className="mono text-fg-primary">{formatSeconds(p.vulnerable_eta_p50_seconds)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-fg-muted">fleet km</div>
          <div className="mono text-fg-primary">{formatKm(p.total_fleet_distance_km)}</div>
        </div>
      </div>
    </div>
  );
}

export function CounterfactualPanel({ panel }: Props) {
  const winnerAssign = panel.winner_by_assignment;
  const winnerVuln = panel.winner_by_vulnerable_eta;

  return (
    <section>
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-xs uppercase tracking-wider text-fg-secondary">Counterfactual — what other policies would have done</h2>
        <div className="mono text-[10px] text-fg-muted">
          {winnerAssign && <>winner (assignment): <span className="text-status-good">{winnerAssign}</span></>}
          {winnerAssign && winnerVuln && <span className="px-2">·</span>}
          {winnerVuln && <>winner (vuln ETA): <span className="text-status-good">{winnerVuln}</span></>}
        </div>
      </header>
      <div className="grid grid-cols-4 gap-2">
        <PolicyColumn p={panel.actual} highlight={false} />
        {panel.policies.map((p) => (
          <PolicyColumn
            key={p.key}
            p={p}
            highlight={p.key === winnerAssign || p.key === winnerVuln}
          />
        ))}
      </div>
      <p className="mt-2 text-[10px] text-fg-muted">
        Replays use a single-trip assignment model (no responder service times yet).
        Compares assignment decisions, not full discrete-event outcomes.
      </p>
    </section>
  );
}
