import Link from "next/link";
import type { RunSummary } from "@/lib/aar";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

async function fetchRuns(): Promise<RunSummary[]> {
  try {
    const res = await fetch(`${BACKEND}/api/analysis/runs`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) return [];
    const body = (await res.json()) as { runs: RunSummary[] };
    return body.runs;
  } catch {
    // Backend hung or down — render the empty-state instead of a 500.
    return [];
  }
}

export default async function RunsIndex() {
  const runs = await fetchRuns();
  return (
    <main className="max-w-3xl mx-auto p-6 text-fg-primary">
      <h1 className="text-lg font-medium mb-1">After Action Reports</h1>
      <p className="text-fg-muted text-sm mb-6">Pick a simulation run to inspect.</p>
      {runs.length === 0 ? (
        <div className="border border-border-strong bg-bg-panel p-6 text-fg-muted text-sm">
          No runs recorded yet. Start a sim from the dashboard, then return here.
        </div>
      ) : (
        <ul className="border border-border-strong bg-bg-panel divide-y divide-border-strong">
          {runs.map((r) => (
            <li key={r.sim_run_id}>
              <Link
                href={`/analysis/${encodeURIComponent(r.sim_run_id)}`}
                className="flex items-baseline justify-between p-3 hover:bg-bg-elev"
              >
                <div>
                  <div className="text-fg-primary text-sm">{r.sim_run_id}</div>
                  <div className="mono text-[10px] text-fg-muted">
                    {new Date(r.started_at).toLocaleString()} · {r.incident_count} incidents
                  </div>
                </div>
                {r.is_active && (
                  <span className="mono text-[10px] uppercase text-status-warn">live</span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-6">
        <Link href="/" className="text-fg-secondary text-sm hover:text-fg-primary">← back to dispatch console</Link>
      </div>
    </main>
  );
}
