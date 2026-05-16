import { useMemo } from 'react';

import { severityBand } from '@disaster/types';

import {
  CATEGORY_ICON,
  SEVERITY_BAND_CLASS,
  timeAgo,
} from './severity';
import { selectQueue, useDashboardStore } from '../lib/store';

export default function IncidentQueue() {
  const queue = useDashboardStore(selectQueue);
  const selectIncident = useDashboardStore((s) => s.selectIncident);
  const selectedIncidentId = useDashboardStore((s) => s.selectedIncidentId);
  const clustersById = useDashboardStore((s) => s.clustersById);

  const now = useMemo(() => Date.now(), [queue.length]);

  const clusterByIncidentId = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of Object.values(clustersById)) {
      for (const id of c.incident_ids) {
        map.set(id, c.incident_ids.length);
      }
    }
    return map;
  }, [clustersById]);

  return (
    <aside className="flex w-80 flex-col border-l border-zinc-800 bg-zinc-950/70">
      <div className="flex h-9 items-center justify-between border-b border-zinc-800 px-3 text-[11px] uppercase tracking-widest text-zinc-400">
        <span>Incident queue</span>
        <span className="tabular font-mono text-zinc-300">{queue.length}</span>
      </div>

      <div className="flex-1 overflow-y-auto thin-scroll">
        {queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center text-xs text-zinc-500">
            <span className="text-2xl">⌁</span>
            <p>
              No incidents yet. Press <span className="text-zinc-300">Start</span>{' '}
              or <span className="text-zinc-300">Inject Critical</span> to begin
              the scenario.
            </p>
          </div>
        ) : (
          queue.map((inc) => {
            const band = severityBand(inc.severity.score);
            const Icon = CATEGORY_ICON[inc.severity.category];
            const clusterSize = clusterByIncidentId.get(inc.incident_id) ?? 0;
            const isClustered = clusterSize > 1;
            const isDegraded = inc.triage_status === 'degraded';
            const isSelected = inc.incident_id === selectedIncidentId;
            const title = (inc.summary || inc.raw_text).slice(0, 60);

            return (
              <button
                key={inc.incident_id}
                type="button"
                onClick={() => selectIncident(inc.incident_id)}
                className={
                  'flex w-full items-start gap-2 border-b border-zinc-900 px-3 py-2.5 text-left transition ' +
                  (isSelected
                    ? 'bg-zinc-800/70'
                    : 'hover:bg-zinc-900/80')
                }
              >
                <div
                  className={
                    'flex h-9 w-9 shrink-0 items-center justify-center rounded ring-1 ' +
                    SEVERITY_BAND_CLASS[band]
                  }
                >
                  <span className="tabular font-mono text-sm font-semibold">
                    {inc.severity.score}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="mb-0.5 flex items-center gap-1.5">
                    <Icon className="h-3 w-3 text-zinc-400" />
                    <span className="text-[10px] uppercase tracking-widest text-zinc-500">
                      {inc.severity.category}
                    </span>
                    <span className="text-[10px] text-zinc-600">·</span>
                    <span className="text-[10px] text-zinc-500">
                      {timeAgo(inc.ts, now)}
                    </span>
                    {inc.status === 'resolved' ? (
                      <span className="ml-auto rounded bg-emerald-500/15 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-emerald-300">
                        resolved
                      </span>
                    ) : null}
                  </div>
                  <p className="line-clamp-2 text-xs leading-snug text-zinc-200">
                    {title}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {isDegraded ? (
                      <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-amber-300 ring-1 ring-amber-500/30">
                        Degraded
                      </span>
                    ) : null}
                    {isClustered ? (
                      <span className="rounded bg-purple-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-purple-300 ring-1 ring-purple-500/30">
                        Clustered ×{clusterSize}
                      </span>
                    ) : null}
                    {inc.location.source === 'place_description_udf' ? (
                      <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-sky-300 ring-1 ring-sky-500/30">
                        place ~
                        {Math.round((inc.location.confidence ?? 0) * 100)}%
                      </span>
                    ) : null}
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}
