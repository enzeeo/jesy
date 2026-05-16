import {
  RESOURCE_BAR,
  RESOURCE_ICON,
  RESOURCE_LABEL,
} from './severity';
import { selectRoster, useDashboardStore } from '../lib/store';

export default function ResourceRoster() {
  const roster = useDashboardStore(selectRoster);

  return (
    <div className="absolute right-4 top-4 z-20 w-60 rounded-md border border-zinc-800 bg-zinc-950/85 p-2 shadow-xl backdrop-blur">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
          Resource roster
        </span>
        <span className="text-[10px] text-zinc-600">avail / total</span>
      </div>
      <ul className="space-y-1.5">
        {roster.map((r) => {
          const Icon = RESOURCE_ICON[r.type];
          const utilization = r.total === 0 ? 0 : r.busy / r.total;
          const isFull = r.total > 0 && r.available === 0;
          const isWarn = !isFull && utilization >= 0.8;
          return (
            <li key={r.type} className="flex items-center gap-2">
              <div
                className={
                  'flex h-6 w-6 items-center justify-center rounded ' +
                  (isFull
                    ? 'bg-red-500/20 text-red-300'
                    : isWarn
                      ? 'bg-amber-500/20 text-amber-300'
                      : 'bg-zinc-800 text-zinc-300')
                }
              >
                <Icon className="h-3 w-3" />
              </div>
              <div className="flex-1">
                <div className="flex items-baseline justify-between gap-1 text-[11px]">
                  <span className="text-zinc-300">{RESOURCE_LABEL[r.type]}</span>
                  <span
                    className={
                      'tabular font-mono ' +
                      (isFull
                        ? 'text-red-300'
                        : isWarn
                          ? 'text-amber-300'
                          : 'text-zinc-200')
                    }
                  >
                    {r.available}/{r.total}
                  </span>
                </div>
                <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-zinc-900">
                  <div
                    className={'h-full transition-all ' + RESOURCE_BAR[r.type]}
                    style={{
                      width: `${Math.round(utilization * 100)}%`,
                    }}
                  />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
