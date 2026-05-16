"use client";
import { useEffect } from "react";
import type { CortexAlertData } from "@/lib/types";

interface Toast { id: number; data: CortexAlertData }

const AUTO_DISMISS_MS = 8000;
const MAX_TOASTS = 2;

interface Props {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}

export function CortexToasts({ toasts, onDismiss }: Props) {
  // Per-toast auto-dismiss timers
  useEffect(() => {
    const timers = toasts.map((t) =>
      setTimeout(() => onDismiss(t.id), AUTO_DISMISS_MS)
    );
    return () => timers.forEach(clearTimeout);
  }, [toasts, onDismiss]);

  const visible = toasts.slice(0, MAX_TOASTS);
  const overflow = Math.max(0, toasts.length - MAX_TOASTS);

  return (
    <div className="absolute right-4 top-20 z-30 flex flex-col gap-2 pointer-events-none">
      {visible.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto w-[480px] bg-bg-panel border border-status-warn shadow-2xl animate-toast-slide-in"
        >
          <div className="flex gap-3 p-3">
            <span className="text-status-warn text-xl">⚠</span>
            <div className="flex-1">
              <div className="text-sm text-fg-primary">{t.data.message}</div>
              <div className="mono mt-1 text-xs text-fg-muted">
                {t.data.injury_bucket} · {t.data.sector} · cluster of {t.data.count} · Cortex anomaly
              </div>
            </div>
            <button
              onClick={() => onDismiss(t.id)}
              className="text-fg-muted hover:text-fg-primary"
              aria-label="Dismiss alert"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
      {overflow > 0 && (
        <div className="pointer-events-auto w-[480px] bg-bg-panel border border-border-strong px-3 py-1.5 mono text-xs text-fg-secondary">
          +{overflow} more
        </div>
      )}
    </div>
  );
}
