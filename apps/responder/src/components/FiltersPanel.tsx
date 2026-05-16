import { useState } from 'react';
import { ChevronLeft, ChevronRight, Filter } from 'lucide-react';

import type { IncidentCategory, ResourceType } from '@disaster/types';
import { INCIDENT_CATEGORIES, RESOURCE_TYPES } from '@disaster/types';

import { useDashboardStore } from '../lib/store';
import type { StatusFilter } from '../lib/store';

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'assigned', label: 'Assigned' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'resolved', label: 'Resolved' },
];

export default function FiltersPanel() {
  const filters = useDashboardStore((s) => s.filters);
  const setFilters = useDashboardStore((s) => s.setFilters);
  const selectResponder = useDashboardStore((s) => s.selectResponder);
  const responders = useDashboardStore((s) => s.respondersById);
  const [open, setOpen] = useState(true);

  const toggleCategory = (cat: IncidentCategory) => {
    const next = filters.categories.includes(cat)
      ? filters.categories.filter((c) => c !== cat)
      : [...filters.categories, cat];
    setFilters({ categories: next });
  };

  if (!open) {
    return (
      <aside className="flex w-10 flex-col items-center border-r border-zinc-800 bg-zinc-950/70 py-3">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded p-1.5 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
          title="Show filters"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <Filter className="mt-3 h-4 w-4 text-zinc-600" />
      </aside>
    );
  }

  const respondersOfType =
    filters.responderType === 'all'
      ? Object.values(responders)
      : Object.values(responders).filter((r) => r.type === filters.responderType);

  return (
    <aside className="flex w-60 flex-col gap-4 overflow-y-auto border-r border-zinc-800 bg-zinc-950/70 p-3 thin-scroll">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-zinc-400">
          <Filter className="h-3.5 w-3.5" />
          Filters
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded p-1 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200"
          title="Collapse filters"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Severity */}
      <section>
        <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-widest text-zinc-500">
          <span>Severity ≥</span>
          <span className="tabular font-mono text-zinc-200">
            {filters.minSeverity}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={filters.minSeverity}
          onChange={(e) =>
            setFilters({ minSeverity: Number(e.target.value) })
          }
          className="w-full accent-red-500"
        />
        <div className="flex justify-between text-[10px] text-zinc-600">
          <span>0</span>
          <span>50</span>
          <span>100</span>
        </div>
      </section>

      {/* Categories */}
      <section>
        <div className="mb-1.5 text-[11px] uppercase tracking-widest text-zinc-500">
          Category
        </div>
        <div className="grid grid-cols-2 gap-1">
          {INCIDENT_CATEGORIES.map((cat) => {
            const active = filters.categories.includes(cat);
            return (
              <button
                key={cat}
                type="button"
                onClick={() => toggleCategory(cat)}
                className={
                  'rounded border px-2 py-1 text-left text-xs capitalize transition ' +
                  (active
                    ? 'border-sky-500/40 bg-sky-500/15 text-sky-200'
                    : 'border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800/60')
                }
              >
                {cat}
              </button>
            );
          })}
        </div>
      </section>

      {/* Status */}
      <section>
        <div className="mb-1.5 text-[11px] uppercase tracking-widest text-zinc-500">
          Status
        </div>
        <div className="flex flex-wrap gap-1">
          {STATUS_OPTIONS.map((s) => {
            const active = filters.status === s.value;
            return (
              <button
                key={s.value}
                type="button"
                onClick={() => setFilters({ status: s.value })}
                className={
                  'rounded border px-2 py-1 text-[11px] transition ' +
                  (active
                    ? 'border-zinc-500/60 bg-zinc-700/40 text-zinc-50'
                    : 'border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:bg-zinc-800/60')
                }
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </section>

      {/* Responder type */}
      <section>
        <div className="mb-1.5 text-[11px] uppercase tracking-widest text-zinc-500">
          Responder type
        </div>
        <select
          value={filters.responderType}
          onChange={(e) => {
            const v = e.target.value as ResourceType | 'all';
            setFilters({ responderType: v });
          }}
          className="w-full rounded border border-zinc-800 bg-zinc-900/80 px-2 py-1.5 text-xs capitalize text-zinc-200"
        >
          <option value="all">All types</option>
          {RESOURCE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <div className="mt-2 max-h-40 overflow-y-auto rounded border border-zinc-800 bg-zinc-900/40 thin-scroll">
          {respondersOfType.length === 0 ? (
            <div className="px-2 py-1.5 text-[11px] text-zinc-600">
              No responders match.
            </div>
          ) : (
            respondersOfType.slice(0, 24).map((r) => (
              <button
                key={r.responder_id}
                type="button"
                onClick={() => selectResponder(r.responder_id)}
                className="flex w-full items-center justify-between px-2 py-1 text-left text-[11px] text-zinc-300 hover:bg-zinc-800/70"
              >
                <span className="font-mono">{r.callsign}</span>
                <span
                  className={
                    'rounded px-1 py-0.5 text-[9px] uppercase tracking-widest ' +
                    (r.status === 'available'
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : r.status === 'busy'
                        ? 'bg-red-500/15 text-red-300'
                        : 'bg-zinc-700/40 text-zinc-400')
                  }
                >
                  {r.status}
                </span>
              </button>
            ))
          )}
        </div>
      </section>
    </aside>
  );
}
