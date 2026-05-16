"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CallerShell } from "@/components/CallerShell";
import { StatusPanel } from "@/components/StatusPanel";
import { api, incidentToCallerStatus } from "@/lib/api";
import type { IncidentReport } from "@/lib/types";

export default function StatusPage() {
  const params = useParams<{ id: string }>();
  const incidentId = useMemo(() => decodeURIComponent(params.id), [params.id]);
  const [incident, setIncident] = useState<IncidentReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        const nextIncident = await api.getIncident(incidentId);
        if (cancelled) return;
        setIncident(nextIncident);
        setError(null);
        setLastUpdatedAt(new Date().toLocaleTimeString());
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "Unable to load your help request.");
      }
    }

    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [incidentId]);

  const status = incident ? incidentToCallerStatus(incident) : null;

  return (
    <CallerShell backHref="/" backLabel="Home">
      {status ? (
        <StatusPanel status={status} />
      ) : (
        <section className="border border-border-strong bg-bg-panel p-5">
          <p className="text-base text-fg-secondary">Connecting to your help request...</p>
        </section>
      )}

      {error && <p className="mt-4 border border-sev-immediate/40 bg-sev-immediate/10 p-3 text-sm text-rose-100">{error}</p>}

      <section className="mt-6 border border-border-strong bg-bg-panel p-5">
        <h2 className="text-base font-semibold text-fg-primary">Stay safe</h2>
        <p className="mt-2 text-sm leading-6 text-fg-secondary">
          You do not need to do anything else. Stay where it is safe, keep this screen open, and conserve battery.
        </p>
        {lastUpdatedAt && <p className="mono mt-4 text-xs uppercase tracking-[0.16em] text-fg-muted">Last updated {lastUpdatedAt}</p>}
      </section>

      <Link href="/incident" className="mt-6 inline-block text-sm font-semibold text-fg-secondary underline-offset-4 hover:text-fg-primary hover:underline">
        Send another update
      </Link>
    </CallerShell>
  );
}
