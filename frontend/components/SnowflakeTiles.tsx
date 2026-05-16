"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SEVERITY_VISUAL } from "@/lib/severity";

interface Tile { tile: string; source: string; rows: any[] }

const TILE_NAMES = [
  "severity_distribution",   // hero
  "incident_rate",
  "response_time_percentiles",
  "geographic_equity",
  "extraction_confidence",
];

export function SnowflakeTiles({ refreshSignal }: { refreshSignal: number }) {
  const [tiles, setTiles] = useState<Record<string, Tile>>({});

  const fetchAll = useCallback(async () => {
    const results = await Promise.allSettled(TILE_NAMES.map((name) => api.tile(name)));
    const next: Record<string, Tile> = {};
    results.forEach((r, i) => {
      if (r.status === "fulfilled") next[TILE_NAMES[i]] = r.value;
    });
    setTiles(next);
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 10000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // refresh on SSE events
  useEffect(() => {
    if (refreshSignal > 0) fetchAll();
  }, [refreshSignal, fetchAll]);

  return (
    <div className="flex h-full">
      <SeverityHero tile={tiles["severity_distribution"]} />
      <PeerTile title="Rate / min" tile={tiles["incident_rate"]} render={(rows) => (
        <div className="mono text-xs text-fg-primary">
          {rows.reduce((acc: number, r: any) => acc + (r.n || 0), 0)} <span className="text-fg-muted">in 10m</span>
        </div>
      )} />
      <PeerTile title="P50 / P99" tile={tiles["response_time_percentiles"]} render={(rows) => {
        const first = rows[0];
        if (!first) return <div className="mono text-xs text-fg-muted">—</div>;
        return (
          <div className="mono text-xs text-fg-primary">
            {Math.round(first.p50 || 0)}s / {Math.round(first.p99 || 0)}s
          </div>
        );
      }} />
      <PeerTile title="Geo Equity" tile={tiles["geographic_equity"]} render={(rows) => (
        <div className="mono text-xs space-y-0.5">
          {rows.map((r: any) => (
            <div key={r.sector} className="text-fg-secondary">
              <span className="text-fg-primary">{r.sector}</span>: {Math.round(r.avg_eta || 0)}s
            </div>
          ))}
        </div>
      )} />
      <PeerTile title="Extraction Conf" tile={tiles["extraction_confidence"]} render={(rows) => {
        const high = rows.find((r: any) => r.bucket === "high")?.n || 0;
        const low = rows.find((r: any) => r.bucket === "low")?.n || 0;
        return (
          <div className="mono text-xs">
            <span className="text-status-good">{high} high</span>{" · "}
            <span className={low > 0 ? "text-status-warn" : "text-fg-muted"}>{low} low</span>
          </div>
        );
      }} />
    </div>
  );
}

function SeverityHero({ tile }: { tile?: Tile }) {
  const rows = tile?.rows ?? [];
  const total = rows.reduce((acc: number, r: any) => acc + (r.n || 0), 0);
  return (
    <div className="flex flex-1 flex-col justify-between border-r border-border-strong bg-bg-panel px-4 py-3">
      <div className="flex items-baseline justify-between">
        <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Severity Distribution</div>
        <div className="mono text-xs text-fg-muted">{tile?.source ?? "—"}</div>
      </div>
      <div className="my-2 flex items-end gap-2">
        {rows.length === 0 ? (
          <div className="text-fg-muted text-sm italic">No data yet</div>
        ) : rows.map((r: any) => {
          const sev = r.severity as keyof typeof SEVERITY_VISUAL;
          const v = SEVERITY_VISUAL[sev];
          const pct = total > 0 ? (r.n / total) * 100 : 0;
          return (
            <div key={r.severity} className="flex-1">
              <div className="mono text-xs text-fg-muted">{v?.label.slice(0, 3) ?? r.severity}</div>
              <div className="h-12 mt-1" style={{ backgroundColor: v?.color ?? "#94A3B8", opacity: 0.85 }} />
              <div className="mono mt-1 text-xs text-fg-primary tabular-nums">{r.n}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PeerTile({ title, tile, render }: {
  title: string;
  tile?: Tile;
  render: (rows: any[]) => React.ReactNode;
}) {
  return (
    <div className="flex w-48 flex-col justify-between border-r border-border-strong bg-bg-panel px-3 py-3">
      <div className="flex items-baseline justify-between">
        <div className="mono text-xs uppercase tracking-wider text-fg-secondary">{title}</div>
        <div className="mono text-xs text-fg-muted">{tile?.source ?? "—"}</div>
      </div>
      <div className="my-2">{render(tile?.rows ?? [])}</div>
    </div>
  );
}
