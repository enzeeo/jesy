import Link from "next/link";
import { notFound } from "next/navigation";
import type { AARResponse } from "@/lib/aar";
import { AARClient } from "@/components/analysis/AARClient";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface Props { params: Promise<{ sim_run_id: string }> }

type FetchOutcome =
  | { kind: "ok"; aar: AARResponse }
  | { kind: "not_found" }
  | { kind: "timeout" }
  | { kind: "error"; message: string };

async function fetchAAR(simRunId: string): Promise<FetchOutcome> {
  // SSR fetch — bail after 15s instead of hanging if the backend is sick
  // (Snowflake connection wedged, query in flight, etc.). Returning a tagged
  // outcome lets the page render an inline retry surface instead of throwing
  // into Next.js's error overlay.
  try {
    const res = await fetch(`${BACKEND}/api/analysis/${encodeURIComponent(simRunId)}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (res.status === 404) return { kind: "not_found" };
    if (!res.ok) return { kind: "error", message: `${res.status} ${await res.text()}` };
    return { kind: "ok", aar: (await res.json()) as AARResponse };
  } catch (e) {
    const err = e as { name?: string; message?: string };
    if (err.name === "TimeoutError" || err.name === "AbortError") {
      return { kind: "timeout" };
    }
    return { kind: "error", message: err.message ?? String(e) };
  }
}

function ErrorState({ simRunId, headline, detail }: { simRunId: string; headline: string; detail: string }) {
  return (
    <main className="max-w-2xl mx-auto p-6 text-fg-primary">
      <h1 className="text-lg font-medium mb-1">{headline}</h1>
      <p className="text-fg-muted text-sm mb-4">{detail}</p>
      <div className="border border-border-strong bg-bg-panel p-4 mono text-xs text-fg-secondary">
        run <span className="text-fg-primary">{simRunId}</span>
      </div>
      <div className="mt-4 flex items-center gap-4 text-sm">
        <Link href={`/analysis/${encodeURIComponent(simRunId)}`} className="text-fg-primary hover:underline">
          Retry
        </Link>
        <Link href="/analysis" className="text-fg-secondary hover:text-fg-primary">
          ← back to runs
        </Link>
      </div>
    </main>
  );
}

export default async function AARPage({ params }: Props) {
  const { sim_run_id } = await params;
  const decoded = decodeURIComponent(sim_run_id);
  const outcome = await fetchAAR(decoded);
  if (outcome.kind === "not_found") notFound();
  if (outcome.kind === "timeout") {
    return (
      <ErrorState
        simRunId={decoded}
        headline="Backend timed out"
        detail="The AAR fetch took longer than 15s. The backend may be slow or its Snowflake connection may be wedged. Restart the backend and retry."
      />
    );
  }
  if (outcome.kind === "error") {
    return (
      <ErrorState
        simRunId={decoded}
        headline="Backend error"
        detail={`AAR fetch failed: ${outcome.message}`}
      />
    );
  }
  return <AARClient aar={outcome.aar} />;
}
