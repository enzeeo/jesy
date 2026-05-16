"use client";
import { useEffect, useRef, useState } from "react";
import type { IncidentReport } from "@/lib/types";
import { SEVERITY_VISUAL } from "@/lib/severity";

interface Props {
  incidents: IncidentReport[];
  flashing: Set<string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function timeShort(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return iso;
  }
}

export function IncidentList({ incidents, flashing, selectedId, onSelect }: Props) {
  const sorted = [...incidents].sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  // aria-live: announce only when the newest incident's ID actually changes,
  // and at most one announcement per second. Without this, the sim flood
  // would spam screen readers 50+ times per minute.
  const seenIdRef = useRef<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    const newest = sorted[0];
    if (!newest || newest.id === seenIdRef.current) return;
    seenIdRef.current = newest.id;
    const text = `New ${newest.severity} incident at ${newest.location.description}`;
    setAnnouncement(text);
    const t = setTimeout(() => setAnnouncement(""), 4000);
    return () => clearTimeout(t);
  }, [sorted]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border-strong bg-bg-panel px-3 py-2">
        <div className="mono text-xs uppercase tracking-wider text-fg-secondary">
          Active Incidents <span className="text-fg-primary">({incidents.length})</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <div className="text-fg-secondary">Awaiting incidents.</div>
              <div className="mono mt-2 text-xs text-fg-muted">{new Date().toISOString().slice(11, 19)} UTC</div>
            </div>
          </div>
        ) : null}

        <div aria-live="polite" aria-atomic="true" className="sr-only">
          {announcement}
        </div>

        {sorted.map((inc) => {
          const v = SEVERITY_VISUAL[inc.severity];
          const isFlashing = flashing.has(inc.id);
          const isSelected = inc.id === selectedId;
          const partial = inc.status === "partial";
          return (
            <button
              key={inc.id}
              onClick={() => onSelect(inc.id)}
              className={[
                "block w-full border-b border-border-strong px-3 py-2 text-left transition-colors",
                isSelected ? "bg-bg-elev" : "hover:bg-bg-elev",
                isFlashing ? "severity-pulse animate-severity-pulse" : "",
              ].join(" ")}
              style={isFlashing ? { boxShadow: `inset 4px 0 0 0 ${v.color}` } : undefined}
            >
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: v.color }}
                  aria-label={v.a11y}
                />
                <span className="mono text-xs text-fg-secondary">{timeShort(inc.timestamp)}</span>
                <span className="mono text-xs font-bold uppercase tracking-wider" style={{ color: v.color }}>
                  {v.label}
                </span>
                {partial && (
                  <span className="mono text-xs text-status-warn" title="Partial extraction, flagged for review">
                    ⚠
                  </span>
                )}
              </div>
              <div className="mt-1 text-sm text-fg-primary truncate">{inc.location.description}</div>
              {inc.victims[0]?.injuries.length ? (
                <div className="mono mt-0.5 text-xs text-fg-muted truncate">
                  {inc.victims[0].injuries.join(", ")}
                </div>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
