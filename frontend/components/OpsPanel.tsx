"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AgentOpsCard, AgentOpsResponse } from "@/lib/types";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-sev-immediate/20 text-sev-immediate border-sev-immediate/40",
  warning: "bg-status-warn/20 text-status-warn border-status-warn/40",
  info: "bg-status-good/15 text-status-good border-status-good/30",
};

const LIVE_OPS_REFRESH_INTERVAL_MS = 10000;

export function OpsPanel({ refreshSignal }: { refreshSignal: number }) {
  const [ops, setOps] = useState<AgentOpsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchOps = useCallback(async () => {
    try {
      const response = await api.ops();
      setOps(response);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ops unavailable");
    }
  }, []);

  useEffect(() => {
    fetchOps();
    const interval = setInterval(fetchOps, LIVE_OPS_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchOps]);

  useEffect(() => {
    if (refreshSignal > 0) fetchOps();
  }, [refreshSignal, fetchOps]);

  const cards = useMemo(() => ops?.cards.slice(0, 3) ?? [], [ops]);
  const lastUpdated = useMemo(() => {
    if (!ops?.generated_at) return "";
    const date = new Date(ops.generated_at);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }, [ops]);

  return (
    <div className="flex h-full min-w-0 flex-col border-l border-border-strong bg-bg-panel">
      <div className="flex h-10 shrink-0 items-center justify-between gap-3 border-b border-border-strong px-3">
        <div className="mono shrink-0 text-xs uppercase tracking-wider text-fg-secondary">Live Ops</div>
        <div className="mono min-w-0 truncate text-right text-[11px] text-fg-muted">
          {lastUpdated ? `Checked ${lastUpdated}` : error ? "Check failed" : "Checking..."}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {error ? (
          <div className="px-3 py-2 text-xs text-status-warn">{error}</div>
        ) : cards.length === 0 ? (
          <div className="px-3 py-2 text-xs text-fg-muted">No ops cards yet</div>
        ) : (
          cards.map((card) => <OpsCard key={card.run_id} card={card} />)
        )}
      </div>
    </div>
  );
}

function OpsCard({ card }: { card: AgentOpsCard }) {
  const severityClass = SEVERITY_STYLES[card.severity] ?? SEVERITY_STYLES.info;
  return (
    <div className="border-b border-border-strong px-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        <span className={`mono shrink-0 rounded-tile border px-1.5 py-0.5 text-[10px] uppercase ${severityClass}`}>
          {card.severity}
        </span>
        <div className="truncate text-xs font-medium text-fg-primary">{card.title}</div>
      </div>
      <div className="mt-1 text-[11px] leading-4 text-fg-secondary">{card.summary}</div>
      <div className="text-[11px] leading-4 text-fg-muted">{card.recommendation}</div>
    </div>
  );
}
