import Link from "next/link";
import type { ReactNode } from "react";

interface CallerShellProps {
  children: ReactNode;
  backHref?: string;
  backLabel?: string;
}

export function CallerShell({ children, backHref, backLabel = "Back" }: CallerShellProps) {
  return (
    <div className="min-h-screen bg-bg-base text-fg-primary">
      <header className="border-b border-border-strong bg-bg-panel/90">
        <div className="mx-auto flex w-full max-w-xl items-center justify-between px-5 py-4">
          {backHref ? (
            <Link href={backHref} className="text-sm font-semibold text-fg-secondary hover:text-fg-primary">
              {backLabel}
            </Link>
          ) : (
            <span className="text-sm font-semibold uppercase tracking-[0.18em] text-fg-secondary">
              Disaster Relief
            </span>
          )}
          <span className="border border-status-good/40 bg-status-good/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-emerald-300">
            Live
          </span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-xl px-5 py-8">{children}</main>
    </div>
  );
}
