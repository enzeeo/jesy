"use client";
import { useState } from "react";
import type { IncidentReport, ResponderUnit, RouteLeg, Severity } from "@/lib/types";
import { ALL_SEVERITIES, SEVERITY_VISUAL } from "@/lib/severity";
import { api } from "@/lib/api";

export interface RecommendedDispatch {
  routeId: string | null;
  responderId: string;
  responder?: ResponderUnit;
  leg: RouteLeg;
}

interface Props {
  incident: IncidentReport;
  recommendedDispatch: RecommendedDispatch | null;
  dispatching: boolean;
  dispatchError: string | null;
  onStartDispatch: (dispatch: RecommendedDispatch) => Promise<void>;
  onClose: () => void;
}

function formatEta(seconds?: number | null): string {
  if (seconds == null) return "ETA --";
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `ETA ${minutes} min`;
}

export function IncidentDetail({
  incident,
  recommendedDispatch,
  dispatching,
  dispatchError,
  onStartDispatch,
  onClose,
}: Props) {
  const v = SEVERITY_VISUAL[incident.severity];
  const [escalating, setEscalating] = useState(false);
  const dispatchPreviewOnly = recommendedDispatch?.responder?.status === "on_scene";

  async function escalate(to: Severity) {
    if (to === incident.severity) return;
    setEscalating(true);
    try {
      await api.escalate(incident.id, to, "manual override");
    } finally {
      setEscalating(false);
    }
  }

  return (
    <div className="absolute right-[372px] top-16 z-20 w-96 border border-border-strong bg-bg-panel shadow-2xl">
      <div className="flex items-center justify-between border-b border-border-strong px-3 py-2">
        <span className="mono text-xs uppercase tracking-wider text-fg-secondary">Incident</span>
        <button onClick={onClose} className="text-fg-secondary hover:text-fg-primary" aria-label="Close">✕</button>
      </div>
      <div className="p-3 space-y-3">
        <div className="flex items-center gap-2">
          <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: v.color }} />
          <span className="mono text-xs font-bold uppercase tracking-wider" style={{ color: v.color }}>
            {v.label}
          </span>
          <span className="mono text-xs text-fg-muted">priority {(incident.priority_score * 100).toFixed(0)}%</span>
        </div>

        <div>
          <div className="text-sm text-fg-primary">{incident.location.description}</div>
          <div className="mono text-xs text-fg-muted">
            {incident.location.lat.toFixed(4)}, {incident.location.lng.toFixed(4)}
          </div>
        </div>

        {incident.victims.map((vic, i) => (
          <div key={i} className="border-t border-border-strong pt-2">
            <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Victim {i + 1}</div>
            <div className="mt-1 text-sm">
              {vic.age_estimate != null && <span>~{vic.age_estimate} yrs · </span>}
              {vic.injuries.join(", ") || <span className="italic text-fg-muted">no injuries reported</span>}
            </div>
            <div className="mono mt-1 text-xs text-fg-muted space-y-0.5">
              <div>breathing: {vic.breathing}</div>
              <div>perfusion: {vic.perfusion}</div>
              <div>mobility: {vic.mobility}</div>
              {vic.respiratory_rate != null && <div>resp rate: {vic.respiratory_rate}/min</div>}
              {vic.vulnerabilities.length > 0 && (
                <div>vulnerabilities: <span className="text-status-warn">{vic.vulnerabilities.join(", ")}</span></div>
              )}
            </div>
          </div>
        ))}

        {incident.call_transcript && (
          <div className="border-t border-border-strong pt-2">
            <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Transcript</div>
            <div className="mt-1 text-xs text-fg-secondary italic">"{incident.call_transcript}"</div>
          </div>
        )}

        <div className="border-t border-border-strong pt-2">
          <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Dispatch</div>
          {recommendedDispatch ? (
            <div className="mt-2 space-y-2">
              <div className="grid grid-cols-[1fr_auto] items-center gap-2">
                <div>
                  <div className="text-sm font-semibold text-fg-primary">
                    {recommendedDispatch.responder?.callsign ?? recommendedDispatch.responderId}
                  </div>
                  <div className="mono text-xs text-fg-muted">
                    {recommendedDispatch.responder?.type ?? "unit"} · {formatEta(recommendedDispatch.leg.eta_seconds)}
                    {recommendedDispatch.leg.distance_km != null
                      ? ` · ${recommendedDispatch.leg.distance_km.toFixed(1)} km`
                      : ""}
                  </div>
                </div>
                <button
                  disabled={dispatching || dispatchPreviewOnly || !recommendedDispatch.routeId || !recommendedDispatch.leg.leg_id}
                  onClick={() => onStartDispatch(recommendedDispatch)}
                  className="mono border border-status-good px-3 py-1 text-xs font-bold uppercase text-status-good
                             hover:bg-bg-elev disabled:cursor-not-allowed disabled:border-border-strong
                             disabled:text-fg-muted disabled:opacity-50"
                >
                  {dispatching ? "Sending" : "Send"}
                </button>
              </div>
              {!recommendedDispatch.routeId || !recommendedDispatch.leg.leg_id ? (
                <div className="mono text-xs text-status-warn">Route identifiers unavailable.</div>
              ) : null}
              {dispatchPreviewOnly ? (
                <div className="mono text-xs text-status-warn">Preview only until aid complete.</div>
              ) : null}
              {dispatchError ? <div className="mono text-xs text-status-warn">{dispatchError}</div> : null}
            </div>
          ) : (
            <div className="mono mt-2 text-xs text-fg-muted">No recommended responder for this incident.</div>
          )}
        </div>

        <div className="border-t border-border-strong pt-2">
          <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Escalate</div>
          <div className="mt-2 flex gap-1">
            {ALL_SEVERITIES.map((s) => (
              <button
                key={s}
                disabled={escalating || s === incident.severity}
                onClick={() => escalate(s)}
                className="mono flex-1 border border-border-strong px-2 py-1 text-xs font-bold uppercase
                           hover:bg-bg-elev disabled:opacity-30 disabled:cursor-not-allowed"
                style={{ color: SEVERITY_VISUAL[s].color }}
              >
                {SEVERITY_VISUAL[s].label.slice(0, 3)}
              </button>
            ))}
          </div>
        </div>

        <div className="mono pt-1 text-xs text-fg-muted">
          {incident.source} · {incident.status} · confidence {(incident.confidence * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  );
}
