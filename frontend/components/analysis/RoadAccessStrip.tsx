"use client";
import type { RoadAccessContext } from "@/lib/aar";

interface Props {
  context: RoadAccessContext | null;
}

export function RoadAccessStrip({ context }: Props) {
  if (!context || context.feature_count === 0) return null;

  const loaded = context.loaded_at
    ? new Date(context.loaded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;
  const hardWarn = context.hard_avoid_count > 0;

  return (
    <div className="border border-border-strong bg-bg-panel px-3 py-2 mono text-xs text-fg-muted flex items-center gap-3">
      <span className="text-[10px] uppercase tracking-wider text-fg-secondary">Road access</span>
      <span>
        <span className="text-fg-primary">{context.feature_count}</span> features
      </span>
      <span>
        <span className={hardWarn ? "text-status-warn" : "text-fg-primary"}>{context.hard_avoid_count}</span> hard
      </span>
      <span>
        <span className="text-fg-primary">{context.soft_penalty_count}</span> soft
      </span>
      {context.provider && (
        <span>
          provider <span className="text-fg-primary">{context.provider}</span>
        </span>
      )}
      {loaded && (
        <span>
          loaded <span className="text-fg-primary">{loaded}</span>
        </span>
      )}
    </div>
  );
}
