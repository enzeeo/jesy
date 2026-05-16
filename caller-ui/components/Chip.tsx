import type { ReactNode } from "react";

interface ChipProps {
  active: boolean;
  onToggle: () => void;
  children: ReactNode;
  ariaLabel?: string;
}

export function Chip({ active, onToggle, children, ariaLabel }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={ariaLabel}
      onClick={onToggle}
      className={`min-h-11 border px-4 py-2 text-sm font-semibold transition ${
        active
          ? "border-sev-immediate bg-sev-immediate/15 text-rose-100"
          : "border-border-strong bg-bg-panel text-fg-secondary hover:bg-bg-elev hover:text-fg-primary"
      }`}
    >
      {children}
    </button>
  );
}
