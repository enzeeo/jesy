import { getVictimMode } from '../lib/data';

interface ModePillProps {
  className?: string;
}

/**
 * Tiny "MODE: FIXTURE" badge so reviewers always know whether the screen
 * they're looking at is mock data or live API output. Required by Phase -1.
 */
export default function ModePill({ className = '' }: ModePillProps) {
  const mode = getVictimMode();
  const tone =
    mode === 'fixture'
      ? 'text-amber-300 ring-amber-400/40 bg-amber-500/10'
      : 'text-emerald-300 ring-emerald-400/40 bg-emerald-500/10';
  return (
    <span
      aria-label={`Data mode: ${mode}`}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ${tone} ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      Mode: {mode}
    </span>
  );
}
