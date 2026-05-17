"use client";
import { useEffect, useState } from "react";
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
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    api.scenarios().then((s) => setScenarios(s.scenarios)).catch(() => {});
    const updateClock = () => setNowUtc(new Date().toISOString().slice(11, 19));
    updateClock();
    const t = setInterval(updateClock, 1000);
    return () => clearInterval(t);
  }, []);

  async function run(label: string, fn: () => Promise<unknown> | unknown) {
    setPending(label);
    try {
      await fn();
      await onAction();
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex h-14 items-center justify-between border-b border-border-strong bg-bg-panel px-4">
      <div className="flex items-center gap-6">
        <div className="flex items-baseline gap-2">
          <span className="mono text-base font-bold tracking-wide text-fg-primary">▲ TEXAS DISPATCH</span>
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
        <TopBarButton label="Seed Responders" pending={pending} onClick={() => run("seed", api.seedResponders)} />
        <TopBarButton label="Start Sim" pending={pending} onClick={() => run("sim", () => api.simStart(200, 60))} />
        <TopBarButton label="Optimize" pending={pending} onClick={() => run("optimize", onOptimize)} />
        <TopBarButton label="Cortex Scan" pending={pending} onClick={() => run("cortex", api.cortexScan)} />
        <div className="mx-2 h-6 w-px bg-border-strong" />
        {scenarios.map((s) => (
          <TopBarButton
            key={s.key}
            label={`Call: ${s.key}`}
            pending={pending}
            onClick={() => run(s.key, () => api.triggerCall(s.key))}
          />
        ))}
        <div className="mx-2 h-6 w-px bg-border-strong" />
        <TopBarButton label="Reset" pending={pending} onClick={() => run("reset", api.reset)} />
      </div>
    </div>
  );
}

function TopBarButton({ label, pending, onClick }: { label: string; pending: string | null; onClick: () => void }) {
  const isMe = pending === label.toLowerCase().split(":")[0].trim();
  return (
    <button
      onClick={onClick}
      disabled={pending !== null}
      className="mono border border-border-strong bg-bg-elev px-2.5 py-1 text-xs text-fg-primary
                 hover:bg-bg-base disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {isMe ? "…" : label}
    </button>
  );
}
