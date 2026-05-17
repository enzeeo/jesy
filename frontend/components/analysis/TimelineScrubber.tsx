"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { TimelineSlice } from "@/lib/aar";

interface Props {
  timeline: TimelineSlice[];
  cursorTSeconds: number;
  onCursorChange: (t: number) => void;
}

// Scrubber decoupled from useSSE — operates on a frozen AAR snapshot. Drag
// the cursor, watch the IncidentMap filter incidents whose offset ≤ cursor.
export function TimelineScrubber({ timeline, cursorTSeconds, onCursorChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);

  const { maxT, maxIncidents } = useMemo(() => {
    if (timeline.length === 0) return { maxT: 0, maxIncidents: 1 };
    return {
      maxT: timeline[timeline.length - 1].t_seconds,
      maxIncidents: Math.max(1, ...timeline.map((s) => s.incidents_total)),
    };
  }, [timeline]);

  // Auto-advance the cursor when playing. Steps the cursor ~10x real-time so
  // a 60s run replays in ~6s. Stops at the end.
  useEffect(() => {
    if (!playing || timeline.length === 0) return;
    const interval = setInterval(() => {
      onCursorChange(Math.min(maxT + 1, cursorTSeconds + Math.max(1, maxT / 60)));
    }, 100);
    return () => clearInterval(interval);
  }, [playing, cursorTSeconds, maxT, timeline.length, onCursorChange]);

  useEffect(() => {
    if (playing && cursorTSeconds >= maxT) setPlaying(false);
  }, [cursorTSeconds, maxT, playing]);

  if (timeline.length === 0) {
    return (
      <div className="border border-border-strong bg-bg-panel p-4 text-fg-muted text-sm">
        No timeline data.
      </div>
    );
  }

  // Build the area chart path. Width 100%, height fixed.
  const W = 1000;
  const H = 80;
  const pad = 4;
  const points = timeline.map((s) => {
    const x = pad + (s.t_seconds / Math.max(1, maxT)) * (W - 2 * pad);
    const y = H - pad - (s.incidents_total / maxIncidents) * (H - 2 * pad);
    return { x, y };
  });
  const areaD =
    `M ${points[0].x} ${H - pad} ` +
    points.map((p) => `L ${p.x} ${p.y}`).join(" ") +
    ` L ${points[points.length - 1].x} ${H - pad} Z`;
  const assignedPoints = timeline.map((s) => {
    const x = pad + (s.t_seconds / Math.max(1, maxT)) * (W - 2 * pad);
    const y = H - pad - (s.incidents_assigned / maxIncidents) * (H - 2 * pad);
    return { x, y };
  });
  const assignedD = "M " + assignedPoints.map((p) => `${p.x} ${p.y}`).join(" L ");
  const cursorX = pad + (cursorTSeconds / Math.max(1, maxT)) * (W - 2 * pad);

  const handlePointer = (clientX: number) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    onCursorChange(Math.round(ratio * maxT));
  };

  const currentSlice = timeline.reduce<TimelineSlice | null>((acc, s) => {
    if (s.t_seconds <= cursorTSeconds) return s;
    return acc;
  }, null) ?? timeline[0];

  return (
    <section>
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-xs uppercase tracking-wider text-fg-secondary">Timeline</h2>
        <div className="mono text-[10px] text-fg-muted">
          <span className="text-fg-primary">t={cursorTSeconds.toString().padStart(3, "0")}s</span>
          <span className="px-2">·</span>
          incidents <span className="text-fg-primary">{currentSlice.incidents_total}</span>
          <span className="px-2">·</span>
          assigned <span className="text-fg-primary">{currentSlice.incidents_assigned}</span>
        </div>
      </header>
      <div className="border border-border-strong bg-bg-panel p-3">
        <div
          ref={containerRef}
          className="relative cursor-crosshair select-none"
          onPointerDown={(e) => { (e.target as Element).setPointerCapture(e.pointerId); handlePointer(e.clientX); }}
          onPointerMove={(e) => { if ((e.buttons & 1) === 1) handlePointer(e.clientX); }}
        >
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full h-20 block">
            <path d={areaD} fill="#1E293B" />
            <path d={assignedD} fill="none" stroke="#22C55E" strokeWidth={1.5} />
            <line x1={cursorX} y1={pad} x2={cursorX} y2={H - pad} stroke="#F1F5F9" strokeWidth={2} />
          </svg>
        </div>
        <div className="flex items-center justify-between mt-2">
          <button
            onClick={() => setPlaying((p) => !p)}
            className="border border-border-strong bg-bg-elev px-3 py-1 text-xs text-fg-primary hover:bg-border-strong"
          >
            {playing ? "❚❚ Pause" : "▶ Play"}
          </button>
          <button
            onClick={() => onCursorChange(0)}
            className="text-xs text-fg-muted hover:text-fg-primary"
          >
            reset
          </button>
          <button
            onClick={() => onCursorChange(maxT)}
            className="text-xs text-fg-muted hover:text-fg-primary"
          >
            jump to end
          </button>
        </div>
      </div>
    </section>
  );
}
