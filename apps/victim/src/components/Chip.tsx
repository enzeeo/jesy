import type { ReactNode } from 'react';

interface ChipProps {
  active: boolean;
  onToggle: () => void;
  children: ReactNode;
  /** Optional decoration on the left (icon, dot, etc). */
  icon?: ReactNode;
  /** When true, the chip is purely informational (no toggle). */
  readOnly?: boolean;
  ariaLabel?: string;
}

/**
 * Big, finger-friendly pill toggle. Used for incident categories,
 * inventory have/need flags, and condition multi-select.
 */
export default function Chip({
  active,
  onToggle,
  children,
  icon,
  readOnly,
  ariaLabel,
}: ChipProps) {
  const base =
    'inline-flex min-h-[44px] items-center gap-2 rounded-full px-4 py-2 text-base font-medium ring-1 transition-colors';
  const tone = active
    ? 'bg-rose-500/15 text-rose-100 ring-rose-400/60'
    : 'bg-zinc-800/60 text-zinc-200 ring-zinc-700 hover:bg-zinc-700/70';
  if (readOnly) {
    return (
      <span aria-label={ariaLabel} className={`${base} ${tone}`}>
        {icon}
        {children}
      </span>
    );
  }
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={ariaLabel}
      onClick={onToggle}
      className={`${base} ${tone}`}
    >
      {icon}
      {children}
    </button>
  );
}
