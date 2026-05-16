import {
  AlertTriangle,
  FastForward,
  Pause,
  Play,
  Plus,
  RotateCcw,
  StepForward,
} from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';

import { useDashboardStore, selectStats } from '../lib/store';
import type { DataAdapter } from '../lib/data';

interface Props {
  adapter: DataAdapter;
}

function fmtClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
}

export default function StatsBar({ adapter }: Props) {
  const scenario = useDashboardStore((s) => s.scenario);
  const connection = useDashboardStore((s) => s.connectionLabel);
  const stats = useDashboardStore(useShallow(selectStats));

  const isRunning = scenario.status === 'running';
  const isPaused = scenario.status === 'paused';

  const handleStart = () => {
    if (isPaused) adapter.resumeScenario();
    else adapter.startScenario();
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-stretch gap-3 border-b border-zinc-800 bg-zinc-950/95 px-4 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded bg-red-500/15 text-red-400 ring-1 ring-red-500/30">
          <AlertTriangle className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <div className="text-[11px] uppercase tracking-widest text-zinc-500">
            {scenario.name}
          </div>
          <div className="text-sm font-semibold text-zinc-200">
            {scenario.label}
          </div>
        </div>
        <div className="ml-2 flex items-center gap-2 rounded border border-zinc-800 bg-zinc-900/80 px-2 py-1 text-xs">
          <span className="text-zinc-500">elapsed</span>
          <span className="tabular font-mono text-zinc-100">
            {fmtClock(stats.elapsedSec)}
          </span>
        </div>
        <span
          className={
            'ml-2 inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest ring-1 ' +
            (connection === 'fixture'
              ? 'bg-amber-500/15 text-amber-300 ring-amber-500/30'
              : 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30')
          }
          title={
            connection === 'fixture'
              ? 'Fixture UI Preview — local mock data, not live Snowflake'
              : 'Live — backed by API/Snowflake'
          }
        >
          <span
            className={
              'h-1.5 w-1.5 rounded-full ' +
              (connection === 'fixture' ? 'bg-amber-300' : 'bg-emerald-300')
            }
          />
          {connection}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          onClick={handleStart}
          disabled={isRunning}
          className="flex items-center gap-1.5 rounded border border-emerald-700/50 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" />
          {isPaused ? 'Resume' : 'Start'}
        </button>
        <button
          type="button"
          onClick={() => adapter.pauseScenario()}
          disabled={!isRunning}
          className="flex items-center gap-1.5 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Pause className="h-3.5 w-3.5" />
          Pause
        </button>
        <button
          type="button"
          onClick={() => adapter.resetScenario()}
          className="flex items-center gap-1.5 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </button>
        <button
          type="button"
          onClick={() => adapter.setSpeed(4)}
          className="flex items-center gap-1.5 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800"
        >
          <FastForward className="h-3.5 w-3.5" />
          4×
        </button>
        <button
          type="button"
          onClick={() => adapter.stepScenario()}
          className="flex items-center gap-1.5 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800"
        >
          <StepForward className="h-3.5 w-3.5" />
          Step
        </button>
        <button
          type="button"
          onClick={() => adapter.injectCritical()}
          className="ml-1 flex items-center gap-1.5 rounded border border-red-700/50 bg-red-500/15 px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wide text-red-200 transition hover:bg-red-500/25"
          title="Inject a severity-98 mass-casualty incident"
        >
          <Plus className="h-3.5 w-3.5" />
          Inject Critical
        </button>

        <div className="ml-3 flex items-stretch gap-2 border-l border-zinc-800 pl-3 text-xs">
          <Stat label="OPEN" value={stats.open} accent="text-red-300" />
          <Stat
            label="RESOLVED"
            value={stats.resolved}
            accent="text-emerald-300"
          />
          <Stat label="AVG SEV" value={stats.avgSeverity} accent="text-amber-300" />
          <Stat
            label="UNITS"
            value={stats.dispatched}
            accent="text-sky-300"
            suffix="dispatched"
          />
        </div>
      </div>
    </header>
  );
}

function Stat({
  label,
  value,
  accent,
  suffix,
}: {
  label: string;
  value: number;
  accent: string;
  suffix?: string;
}) {
  return (
    <div className="flex items-center gap-1.5 rounded border border-zinc-800 bg-zinc-900/70 px-2 py-1">
      <span className="text-[9px] uppercase tracking-widest text-zinc-500">
        {label}
      </span>
      <span className={`tabular font-mono text-sm font-semibold ${accent}`}>
        {value}
      </span>
      {suffix ? (
        <span className="text-[10px] text-zinc-500">{suffix}</span>
      ) : null}
    </div>
  );
}
