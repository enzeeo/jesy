"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { NarrativeResponse } from "@/lib/aar";

interface Props { simRunId: string; isLive: boolean }

export function NarrativePanel({ simRunId, isLive }: Props) {
  const [data, setData] = useState<NarrativeResponse | null>(null);
  const [loading, setLoading] = useState(!isLive);

  useEffect(() => {
    if (isLive) {
      // Server already returns a static "run in progress" narrative; just fetch it
      // so the source/badge stays consistent with the rest of the page.
      setLoading(true);
    }
    let cancelled = false;
    api.aarNarrative(simRunId)
      .then((r) => { if (!cancelled) { setData(r); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [simRunId, isLive]);

  if (loading) {
    return (
      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wider text-fg-secondary">Summary</h2>
        <div className="border border-border-strong bg-bg-panel p-4">
          <div className="h-4 w-3/4 bg-bg-elev mb-2" />
          <div className="h-4 w-full bg-bg-elev mb-2" />
          <div className="h-4 w-5/6 bg-bg-elev" />
        </div>
      </section>
    );
  }
  if (!data) {
    return (
      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wider text-fg-secondary">Summary</h2>
        <div className="border border-border-strong bg-bg-panel p-4 text-fg-muted text-sm">
          Narrative unavailable.
        </div>
      </section>
    );
  }
  return (
    <section>
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-xs uppercase tracking-wider text-fg-secondary">Summary</h2>
        <span className="mono text-[10px] uppercase text-fg-muted">{data.source}</span>
      </header>
      <div className="border border-border-strong bg-bg-panel p-4 text-sm text-fg-primary leading-relaxed whitespace-pre-line">
        {data.narrative}
      </div>
    </section>
  );
}

export function LessonsPanel({ simRunId, isLive }: Props) {
  const [data, setData] = useState<NarrativeResponse | null>(null);
  const [loading, setLoading] = useState(!isLive);

  useEffect(() => {
    let cancelled = false;
    api.aarNarrative(simRunId)
      .then((r) => { if (!cancelled) { setData(r); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [simRunId, isLive]);

  if (loading) {
    return (
      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wider text-fg-secondary">Lessons learned</h2>
        <div className="border border-border-strong bg-bg-panel p-4">
          <div className="h-4 w-2/3 bg-bg-elev mb-2" />
          <div className="h-3 w-full bg-bg-elev mb-3" />
          <div className="h-4 w-3/4 bg-bg-elev mb-2" />
          <div className="h-3 w-full bg-bg-elev" />
        </div>
      </section>
    );
  }
  if (!data || data.lessons.length === 0) {
    return (
      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wider text-fg-secondary">Lessons learned</h2>
        <div className="border border-border-strong bg-bg-panel p-4 text-fg-muted text-sm">
          {isLive
            ? "Lessons will appear once the run ends."
            : data?.source === "fallback"
            ? "No recommendations generated (OpenAI fallback mode)."
            : "No recommendations."}
        </div>
      </section>
    );
  }
  return (
    <section>
      <h2 className="mb-2 text-xs uppercase tracking-wider text-fg-secondary">Lessons learned</h2>
      <div className="border border-border-strong bg-bg-panel divide-y divide-border-strong">
        {data.lessons.map((l, i) => (
          <div key={i} className="p-3">
            <div className="text-fg-primary text-sm font-medium">{l.headline}</div>
            <div className="text-fg-secondary text-xs mt-1">{l.rationale}</div>
            {l.metric_citations.length > 0 && (
              <div className="mono text-[10px] text-fg-muted mt-2">
                {l.metric_citations.join(" · ")}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
