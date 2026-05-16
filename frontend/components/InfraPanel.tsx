"use client";
import { useEffect, useState } from "react";

interface InfraMetrics {
  llm_model: string;
  llm_calls: number;
  llm_tokens: number;
  llm_latency_ms: number;
  sf_enqueued: number;
  sf_dropped: number;
  sse_subscribers: number;
}

interface Props {
  callsHandled: number;
  incidentsCount: number;
}

// Animated counter via rAF (Performance issue 4.8)
function useAnimatedCounter(target: number, durationMs = 800) {
  const [value, setValue] = useState(target);
  useEffect(() => {
    const start = performance.now();
    const startVal = value;
    const delta = target - startVal;
    if (delta === 0) return;
    let raf: number;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(startVal + delta * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]); // eslint-disable-line react-hooks/exhaustive-deps
  return value;
}

export function InfraPanel({ callsHandled, incidentsCount }: Props) {
  const calls = useAnimatedCounter(callsHandled);
  const inc = useAnimatedCounter(incidentsCount);

  return (
    <div className="flex h-full flex-col border-r border-border-strong bg-bg-panel px-4 py-3">
      <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Infrastructure</div>
      <div className="mt-2 grid grid-cols-2 gap-y-2">
        <div>
          <div className="mono text-2xl tabular-nums text-fg-primary">{calls}</div>
          <div className="mono text-xs text-fg-muted">voice calls</div>
        </div>
        <div>
          <div className="mono text-2xl tabular-nums text-fg-primary">{inc}</div>
          <div className="mono text-xs text-fg-muted">incidents</div>
        </div>
        <div>
          <div className="mono text-sm text-fg-primary flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-status-good" />
            gpt-4o-mini
          </div>
          <div className="mono text-xs text-fg-muted">openai live</div>
        </div>
        <div>
          <div className="mono text-sm text-fg-primary">snowflake</div>
          <div className="mono text-xs text-status-good">async writes</div>
        </div>
      </div>
    </div>
  );
}
