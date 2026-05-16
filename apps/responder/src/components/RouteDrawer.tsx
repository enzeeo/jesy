import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, RotateCcw } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';

import { severityBand } from '@disaster/types';

import {
  RESOURCE_CLASS,
  RESOURCE_ICON,
  RESOURCE_LABEL,
  SEVERITY_BAND_CLASS,
  formatEta,
} from './severity';
import type { DataAdapter } from '../lib/data';
import { selectRoutes, useDashboardStore } from '../lib/store';

interface Props {
  adapter: DataAdapter;
}

export default function RouteDrawer({ adapter }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const routes = useDashboardStore(useShallow(selectRoutes));
  const filters = useDashboardStore((s) => s.filters);
  const respondersById = useDashboardStore((s) => s.respondersById);
  const incidentsById = useDashboardStore((s) => s.incidentsById);
  const selectedResponderId = useDashboardStore((s) => s.selectedResponderId);
  const setSelectedResponder = useDashboardStore((s) => s.selectResponder);

  const visibleRoutes = useMemo(() => {
    if (selectedResponderId) {
      return routes.filter((r) => r.responder_id === selectedResponderId);
    }
    if (filters.responderType !== 'all') {
      return routes.filter((r) => {
        const responder = respondersById[r.responder_id];
        return responder?.type === filters.responderType;
      });
    }
    return routes;
  }, [routes, selectedResponderId, filters.responderType, respondersById]);

  return (
    <section
      className={
        'border-t border-zinc-800 bg-zinc-950/85 transition-all ' +
        (collapsed ? 'h-8' : 'h-48')
      }
    >
      <div className="flex h-8 items-center gap-2 border-b border-zinc-800 px-3">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
          Route drawer
        </span>
        <span className="text-[10px] text-zinc-600">
          {visibleRoutes.length} active
        </span>
        {selectedResponderId ? (
          <button
            type="button"
            onClick={() => setSelectedResponder(null)}
            className="ml-1 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-zinc-300 hover:bg-zinc-700"
          >
            clear filter
          </button>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => adapter.recomputeRoutes()}
            className="flex items-center gap-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-200 hover:bg-zinc-800"
          >
            <RotateCcw className="h-3 w-3" />
            Recompute
          </button>
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            {collapsed ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
      {!collapsed && (
        <div className="flex h-40 gap-3 overflow-x-auto px-3 py-2 thin-scroll">
          {visibleRoutes.length === 0 ? (
            <div className="flex flex-1 items-center justify-center text-xs text-zinc-500">
              Select a responder or filter by type to see active routes.
            </div>
          ) : (
            visibleRoutes.map((route) => {
              const responder = respondersById[route.responder_id];
              const type = responder?.type;
              const Icon = type ? RESOURCE_ICON[type] : RESOURCE_ICON.volunteer;
              return (
                <div
                  key={route.responder_id}
                  className={
                    'flex w-72 shrink-0 flex-col rounded border border-zinc-800 bg-zinc-900/70 p-2'
                  }
                >
                  <div className="mb-1.5 flex items-center gap-2">
                    <div
                      className={
                        'flex h-6 w-6 items-center justify-center rounded ring-1 ' +
                        (type ? RESOURCE_CLASS[type] : '')
                      }
                    >
                      <Icon className="h-3 w-3" />
                    </div>
                    <div className="flex-1">
                      <div className="font-mono text-xs text-zinc-100">
                        {responder?.callsign ?? route.responder_id}
                      </div>
                      <div className="text-[10px] uppercase tracking-widest text-zinc-500">
                        {type ? RESOURCE_LABEL[type] : 'Unknown'}
                      </div>
                    </div>
                    {route.route_source === 'fallback' ? (
                      <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-amber-300 ring-1 ring-amber-500/30">
                        fallback (straight-line)
                      </span>
                    ) : route.route_source === 'cached' ? (
                      <span className="rounded bg-zinc-700/50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-zinc-300">
                        cached
                      </span>
                    ) : (
                      <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-emerald-300">
                        mapbox
                      </span>
                    )}
                  </div>
                  <ol className="flex-1 space-y-1 overflow-y-auto thin-scroll">
                    {route.stops.map((stop) => {
                      const inc = incidentsById[stop.incident_id];
                      const band = inc
                        ? severityBand(inc.severity.score)
                        : 'info';
                      return (
                        <li
                          key={stop.order}
                          className="flex items-center gap-2 text-[11px]"
                        >
                          <span className="tabular font-mono text-zinc-500">
                            {stop.order}.
                          </span>
                          <span
                            className={
                              'rounded px-1.5 py-0.5 text-[10px] font-semibold tabular ring-1 ' +
                              SEVERITY_BAND_CLASS[band]
                            }
                          >
                            {inc ? inc.severity.score : '?'}
                          </span>
                          <span className="flex-1 truncate text-zinc-200">
                            {stop.incident_id}
                          </span>
                          <span className="tabular font-mono text-zinc-400">
                            ETA {formatEta(stop.eta_sec)}
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                  <div className="mt-1.5 flex items-center justify-between border-t border-zinc-800 pt-1.5 text-[11px]">
                    <span className="text-zinc-500">Total ETA</span>
                    <span className="tabular font-mono text-zinc-200">
                      {formatEta(route.total_eta_sec)}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </section>
  );
}
