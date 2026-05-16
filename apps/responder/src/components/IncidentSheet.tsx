import { AnimatePresence, motion } from 'framer-motion';
import { useMemo } from 'react';
import { MapPin, RotateCcw, X } from 'lucide-react';

import type { ResourceType } from '@disaster/types';
import { severityBand } from '@disaster/types';

import {
  CATEGORY_ICON,
  RESOURCE_CLASS,
  RESOURCE_ICON,
  RESOURCE_LABEL,
  SEVERITY_BAND_CLASS,
  formatEta,
} from './severity';
import type { DataAdapter } from '../lib/data';
import {
  selectAssignmentsForIncident,
  selectUnmetForIncident,
  useDashboardStore,
} from '../lib/store';

interface Props {
  adapter: DataAdapter;
}

function locationBadge(
  source: 'gps' | 'place_description_udf' | 'manual',
  confidence?: number,
): { label: string; cls: string } {
  switch (source) {
    case 'gps':
      return {
        label: 'GPS',
        cls: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
      };
    case 'place_description_udf': {
      const pct = Math.round((confidence ?? 0) * 100);
      return {
        label: `PLACE DESCRIPTION ~${pct}%`,
        cls: 'bg-sky-500/15 text-sky-300 ring-sky-500/30',
      };
    }
    case 'manual':
      return {
        label: 'MANUAL',
        cls: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
      };
  }
}

export default function IncidentSheet({ adapter }: Props) {
  const selectedId = useDashboardStore((s) => s.selectedIncidentId);
  const incident = useDashboardStore((s) =>
    selectedId ? s.incidentsById[selectedId] : undefined,
  );
  const select = useDashboardStore((s) => s.selectIncident);
  const respondersById = useDashboardStore((s) => s.respondersById);
  const clustersById = useDashboardStore((s) => s.clustersById);

  const assignments = useDashboardStore((s) =>
    selectedId ? selectAssignmentsForIncident(s, selectedId) : [],
  );
  const unmet = useDashboardStore((s) =>
    selectedId ? selectUnmetForIncident(s, selectedId) : [],
  );

  const clusterSize = useMemo(() => {
    if (!incident) return 0;
    for (const c of Object.values(clustersById)) {
      if (c.incident_ids.includes(incident.incident_id))
        return c.incident_ids.length;
    }
    return 0;
  }, [clustersById, incident]);

  return (
    <AnimatePresence>
      {incident ? (
        <motion.aside
          key={incident.incident_id}
          initial={{ x: 480, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 480, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 320, damping: 32 }}
          className="absolute right-0 top-0 z-40 flex h-full w-[420px] flex-col border-l border-zinc-800 bg-zinc-950/95 shadow-2xl backdrop-blur"
        >
          {/* Header */}
          <header className="flex items-start gap-3 border-b border-zinc-800 px-4 py-3">
            <div
              className={
                'flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-md ring-1 ' +
                SEVERITY_BAND_CLASS[severityBand(incident.severity.score)]
              }
            >
              <span className="tabular font-mono text-2xl font-semibold leading-none">
                {incident.severity.score}
              </span>
              <span className="mt-0.5 text-[9px] uppercase tracking-widest opacity-80">
                severity
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-zinc-400">
                {(() => {
                  const Icon = CATEGORY_ICON[incident.severity.category];
                  return <Icon className="h-3 w-3" />;
                })()}
                <span>{incident.severity.category}</span>
                <span className="text-zinc-600">·</span>
                <span
                  className={
                    'rounded px-1.5 py-0.5 text-[9px] font-semibold ' +
                    (incident.status === 'resolved'
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : incident.status === 'assigned'
                        ? 'bg-sky-500/15 text-sky-300'
                        : incident.status === 'in_progress'
                          ? 'bg-amber-500/15 text-amber-300'
                          : 'bg-zinc-700/40 text-zinc-300')
                  }
                >
                  {incident.status}
                </span>
              </div>
              <h2 className="mt-1 truncate text-sm font-semibold text-zinc-100">
                {incident.incident_id}
              </h2>
              <div className="mt-1 flex flex-wrap gap-1">
                {incident.triage_status === 'degraded' ? (
                  <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-amber-300 ring-1 ring-amber-500/30">
                    Degraded — manual review
                  </span>
                ) : null}
                {clusterSize > 1 ? (
                  <span className="rounded bg-purple-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-purple-300 ring-1 ring-purple-500/30">
                    Clustered ×{clusterSize}
                  </span>
                ) : null}
                {(() => {
                  const b = locationBadge(
                    incident.location.source,
                    incident.location.confidence,
                  );
                  return (
                    <span
                      className={
                        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest ring-1 ' +
                        b.cls
                      }
                    >
                      <MapPin className="h-2.5 w-2.5" />
                      {b.label}
                    </span>
                  );
                })()}
              </div>
            </div>
            <button
              type="button"
              onClick={() => select(null)}
              className="rounded p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3 thin-scroll">
            {/* Summary */}
            <Section title="Summary">
              <p className="text-sm leading-relaxed text-zinc-200">
                {incident.summary || incident.raw_text}
              </p>
            </Section>

            {/* Profile */}
            {incident.profile_snapshot ? (
              <Section title="Victim profile">
                <div className="rounded border border-zinc-800 bg-zinc-900/60 p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-zinc-100">
                      {incident.profile_snapshot.name}
                    </span>
                    <span className="text-[11px] text-zinc-500">
                      age {incident.profile_snapshot.age}
                    </span>
                  </div>
                  {incident.profile_snapshot.conditions.length > 0 ? (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {incident.profile_snapshot.conditions.map((c) => (
                        <span
                          key={c}
                          className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-300 ring-1 ring-red-500/20"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {incident.profile_snapshot.devices_owned.length > 0 ? (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {incident.profile_snapshot.devices_owned.map((d) => (
                        <span
                          key={d}
                          className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-[10px] text-zinc-300"
                        >
                          {d}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </Section>
            ) : null}

            {/* Transcript */}
            <Section title="Transcript">
              <pre className="whitespace-pre-wrap rounded border border-zinc-800 bg-zinc-900/60 p-2.5 font-mono text-[11px] leading-relaxed text-zinc-300">
                {incident.raw_text}
              </pre>
            </Section>

            {/* Reasons */}
            <Section title="Top reasons">
              <ol className="space-y-1.5 text-sm text-zinc-200">
                {incident.severity.top_reasons.map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="tabular font-mono text-xs text-zinc-500">
                      {i + 1}.
                    </span>
                    <span className="flex-1 leading-snug">{r}</span>
                  </li>
                ))}
              </ol>
            </Section>

            {/* Required resources */}
            <Section title="Required resources">
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(incident.severity.required_resources).map(
                  ([k, qty]) => {
                    const type = k as ResourceType;
                    const Icon = RESOURCE_ICON[type];
                    return (
                      <span
                        key={k}
                        className={
                          'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] ring-1 ' +
                          RESOURCE_CLASS[type]
                        }
                      >
                        <Icon className="h-3 w-3" />
                        {RESOURCE_LABEL[type]} ×{qty}
                      </span>
                    );
                  },
                )}
              </div>
            </Section>

            {/* Assigned units */}
            <Section title="Assigned units">
              {assignments.length === 0 ? (
                <p className="text-[11px] text-zinc-500">
                  No units dispatched yet.
                </p>
              ) : (
                <ul className="space-y-1">
                  {assignments.map((a) => {
                    const r = respondersById[a.responder_id];
                    const Icon = RESOURCE_ICON[a.resource_type];
                    return (
                      <li
                        key={a.assignment_id}
                        className={
                          'flex items-center gap-2 rounded border px-2 py-1.5 text-xs ring-1 ' +
                          RESOURCE_CLASS[a.resource_type] +
                          ' border-transparent'
                        }
                      >
                        <Icon className="h-3.5 w-3.5" />
                        <span className="flex-1 font-mono">
                          {r ? r.callsign : a.responder_id}
                        </span>
                        <span className="text-[10px] uppercase tracking-widest opacity-80">
                          {a.status}
                        </span>
                        <span className="tabular font-mono">
                          ETA {formatEta(a.eta_sec)}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}

              {unmet.length > 0 ? (
                <div className="mt-2 rounded border border-red-500/30 bg-red-500/10 p-2">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-red-300">
                    Unmet need
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {unmet.map((u, i) => {
                      const Icon = RESOURCE_ICON[u.resource_type];
                      return (
                        <span
                          key={`${u.resource_type}-${i}`}
                          className="inline-flex items-center gap-1 rounded bg-red-500/15 px-1.5 py-0.5 text-[11px] text-red-200 ring-1 ring-red-500/30"
                        >
                          <Icon className="h-3 w-3" />
                          {RESOURCE_LABEL[u.resource_type]} ×{u.quantity_needed}
                        </span>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </Section>

            {/* Inventory */}
            {(incident.inventory_have.length > 0 ||
              incident.inventory_need.length > 0) && (
              <Section title="Inventory">
                {incident.inventory_have.length > 0 ? (
                  <div className="mb-1.5">
                    <div className="text-[10px] uppercase tracking-widest text-emerald-400">
                      Have
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {incident.inventory_have.map((d) => (
                        <span
                          key={d}
                          className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-300 ring-1 ring-emerald-500/30"
                        >
                          {d}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {incident.inventory_need.length > 0 ? (
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-red-400">
                      Need
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {incident.inventory_need.map((d) => (
                        <span
                          key={d}
                          className="rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] text-red-300 ring-1 ring-red-500/30"
                        >
                          {d}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </Section>
            )}
          </div>

          {/* Footer actions */}
          <footer className="flex items-center justify-between gap-2 border-t border-zinc-800 bg-zinc-950/80 px-4 py-2.5">
            <button
              type="button"
              onClick={() => adapter.recomputeRoutes()}
              className="flex items-center gap-1.5 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-200 transition hover:bg-zinc-800"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Recompute routes
            </button>
            <button
              type="button"
              onClick={() => adapter.markResolved(incident.incident_id)}
              disabled={incident.status === 'resolved'}
              className="flex items-center gap-1.5 rounded border border-emerald-700/50 bg-emerald-500/15 px-2.5 py-1.5 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-50"
            >
              Mark resolved
            </button>
          </footer>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
        {title}
      </div>
      {children}
    </section>
  );
}
