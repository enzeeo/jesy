import { notFound } from "next/navigation";
import type { AARResponse } from "@/lib/aar";
import { AARClient } from "@/components/analysis/AARClient";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface Props { params: Promise<{ sim_run_id: string }> }

async function fetchAAR(simRunId: string): Promise<AARResponse | null> {
  const res = await fetch(`${BACKEND}/api/analysis/${encodeURIComponent(simRunId)}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`AAR fetch failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AARResponse;
}

export default async function AARPage({ params }: Props) {
  const { sim_run_id } = await params;
  const decoded = decodeURIComponent(sim_run_id);
  const aar = await fetchAAR(decoded);
  if (!aar) notFound();
  return <AARClient aar={aar} />;
}
