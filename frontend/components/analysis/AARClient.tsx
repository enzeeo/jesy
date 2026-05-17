"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { AARResponse } from "@/lib/aar";
import { api } from "@/lib/api";
import { Scorecard } from "./Scorecard";
import { CounterfactualPanel } from "./CounterfactualPanel";
import { VulnerabilityPanel } from "./VulnerabilityPanel";
import { NarrativePanel, LessonsPanel } from "./NarrativePanel";
import { IncidentMap } from "./IncidentMap";
import { TimelineScrubber } from "./TimelineScrubber";

interface Props { aar: AARResponse }

export function AARClient({ aar: initialAar }: Props) {
  const router = useRouter();
  const [aar, setAar] = useState<AARResponse>(initialAar);

  // Cursor starts at the end (show full run by default). Scrubber lets user
  // drag back in time. Bounded by last timeline slice's t_seconds.
  const maxT = aar.timeline.length > 0 ? aar.timeline[aar.timeline.length - 1].t_seconds : 0;
  const [cursorTSeconds, setCursor] = useState<number>(maxT);

  // Live runs: poll every 3s. When the run flips out of is_live, refresh the
  // page so SSR re-fetches the full payload (counterfactual + narrative panels
  // weren't part of the live response and need a fresh server render).
  useEffect(() => {
    if (!aar.is_live) return;
    const id = setInterval(async () => {
      try {
        const next = await api.aar(aar.sim_run_id);
        if (!next.is_live) {
          router.refresh();
        } else {
          setAar(next);
          // While still live, advance the cursor so newly-arrived incidents render.
          const nextMaxT = next.timeline.length > 0 ? next.timeline[next.timeline.length - 1].t_seconds : 0;
          setCursor(nextMaxT);
        }
      } catch {
        // transient — keep polling
      }
    }, 3000);
    return () => clearInterval(id);
  }, [aar.is_live, aar.sim_run_id, router]);

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Header strip */}
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-fg-primary text-lg font-medium">After Action Report</h1>
          <div className="mono text-xs text-fg-muted">
            run <span className="text-fg-secondary">{aar.sim_run_id}</span>
            <span className="px-2">·</span>
            data <span className="text-fg-secondary">{aar.data_source}</span>
            {aar.started_at && aar.ended_at && (
              <>
                <span className="px-2">·</span>
                duration <span className="text-fg-secondary">
                  {Math.round((new Date(aar.ended_at).getTime() - new Date(aar.started_at).getTime()) / 1000)}s
                </span>
              </>
            )}
          </div>
        </div>
        {aar.is_live && aar.badge && (
          <div className="border border-status-warn bg-status-warn/10 text-status-warn px-3 py-1 mono text-xs">
            ⚡ {aar.badge}
          </div>
        )}
      </header>

      <Scorecard scorecard={aar.scorecard} />

      {aar.counterfactual && <CounterfactualPanel panel={aar.counterfactual} />}

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 flex flex-col gap-4">
          <NarrativePanel simRunId={aar.sim_run_id} isLive={aar.is_live} />
          <LessonsPanel simRunId={aar.sim_run_id} isLive={aar.is_live} />
        </div>
        <VulnerabilityPanel rows={aar.vulnerability} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 border border-border-strong bg-bg-panel h-[420px]">
          <IncidentMap
            points={aar.incidents_geo}
            cursorTSeconds={cursorTSeconds}
            startedAt={aar.started_at}
          />
        </div>
        <div className="col-span-1">
          <TimelineScrubber
            timeline={aar.timeline}
            cursorTSeconds={cursorTSeconds}
            onCursorChange={setCursor}
          />
        </div>
      </div>

      <footer className="mono text-[10px] text-fg-muted text-center mt-4 pb-4">
        AAR generated from {aar.scorecard.incident_count} incidents · source: {aar.data_source}
      </footer>
    </div>
  );
}
