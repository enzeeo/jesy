import type { CallerStatusView } from "@/lib/types";

function severityLabel(score?: number): string {
  if (score == null) return "Reviewing";
  if (score >= 75) return "High priority";
  if (score >= 50) return "Priority";
  if (score >= 25) return "Queued";
  return "Received";
}

export function StatusPanel({ status }: { status: CallerStatusView }) {
  const tone =
    status.state === "assigned"
      ? "border-status-good bg-status-good/10"
      : status.state === "low_confidence_location"
        ? "border-status-warn bg-status-warn/10"
        : "border-sky-500/40 bg-sky-500/10";

  return (
    <section aria-live="polite" className={`border p-5 ${tone}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="mono text-xs uppercase tracking-[0.16em] text-fg-muted">Incident</p>
          <p className="mono mt-1 break-all text-sm font-semibold text-fg-secondary">{status.incident_id}</p>
        </div>
        <span className="border border-border-strong bg-bg-panel px-2 py-1 text-xs font-semibold text-fg-secondary">
          {severityLabel(status.severity_score)}
        </span>
      </div>

      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-fg-primary">{status.title}</h1>
      <p className="mt-3 text-base leading-7 text-fg-secondary">{status.message}</p>
    </section>
  );
}
