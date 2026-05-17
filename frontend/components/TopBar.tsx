"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

interface Props {
  connected: boolean;
  incidentsCount: number;
  respondersCount: number;
  onAction: () => Promise<void> | void;
  onOptimize: () => Promise<void> | void;
}

export function TopBar({ connected, incidentsCount, respondersCount, onAction, onOptimize }: Props) {
  const [scenarios, setScenarios] = useState<Array<{ key: string; preview: string }>>([]);
  const [nowUtc, setNowUtc] = useState("--:--:--");
  const [pendingActions, setPendingActions] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.scenarios().then((s) => setScenarios(s.scenarios)).catch(() => {});
    const updateClock = () => setNowUtc(new Date().toISOString().slice(11, 19));
    updateClock();
    const t = setInterval(updateClock, 1000);
    return () => clearInterval(t);
  }, []);

  async function run(actionKey: string, fn: () => Promise<unknown> | unknown) {
    setPendingActions((previous) => new Set(previous).add(actionKey));
    try {
      await fn();
      await onAction();
    } finally {
      setPendingActions((previous) => {
        const next = new Set(previous);
        next.delete(actionKey);
        return next;
      });
    }
  }

  return (
    <div className="flex h-14 items-center justify-between border-b border-border-strong bg-bg-panel px-4">
      <div className="flex items-center gap-6">
        <div className="flex items-baseline gap-2">
          <span className="mono text-base font-bold tracking-wide text-fg-primary">▲ ASHEVILLE DISPATCH</span>
        </div>
        <div className="mono flex items-baseline gap-4 text-xs text-fg-secondary">
          <span><span className="text-fg-primary">{respondersCount}</span> units</span>
          <span><span className="text-fg-primary">{incidentsCount}</span> incidents</span>
          <span className={connected ? "text-status-good" : "text-status-warn"}>
            {connected ? "● live" : "● reconnecting"}
          </span>
          <span>{nowUtc} UTC</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <TopBarButton label="Seed Responders" pending={pendingActions.has("seed")} onClick={() => run("seed", api.seedResponders)} />
        <TopBarButton label="Start Sim" pending={pendingActions.has("sim")} onClick={() => run("sim", () => api.simStart(200, 60, "helene_cached"))} />
        <TopBarButton label="Optimize" pending={pendingActions.has("optimize")} onClick={() => run("optimize", onOptimize)} />
        <TopBarButton label="Cortex Scan" pending={pendingActions.has("cortex")} onClick={() => run("cortex", api.cortexScan)} />
        <div className="mx-2 h-6 w-px bg-border-strong" />
        {scenarios.map((s) => (
          <TopBarButton
            key={s.key}
            label={`Call: ${s.key}`}
            pending={pendingActions.has(s.key)}
            onClick={() => run(s.key, () => api.triggerCall(s.key))}
          />
        ))}
        <div className="mx-2 h-6 w-px bg-border-strong" />
        <Link
          href="/analysis"
          className="mono border border-border-strong bg-bg-elev px-2.5 py-1 text-xs text-fg-primary hover:bg-bg-base"
        >
          AAR
        </Link>
        <TopBarButton label="Reset" pending={pendingActions.has("reset")} onClick={() => run("reset", api.reset)} />
      </div>
    </div>
  );
}

function TopBarButton({ label, pending, onClick }: { label: string; pending: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={pending}
      className="mono border border-border-strong bg-bg-elev px-2.5 py-1 text-xs text-fg-primary
                 hover:bg-bg-base disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {pending ? "..." : label}
    </button>
  );
}
