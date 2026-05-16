"use client";
import { useEffect, useRef, useState } from "react";
import type { SSEEvent } from "./types";

type Handler = (event: SSEEvent) => void;

// SSE goes DIRECT to the backend, bypassing Next.js rewrite.
// Next.js dev (14.x) buffers proxied SSE responses — EventSource never receives
// events even though curl works. CORS allow_origins=["*"] on the backend covers
// this. Override via NEXT_PUBLIC_BACKEND_URL if backend is not on localhost:8000.
const SSE_URL = `${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"}/events`;

/**
 * Subscribes to /events (server-sent events). Maintains an internal
 * sequence_id Set so the severity flash hook can dedupe concurrent upgrades.
 */
export function useSSE(handler: Handler, deps: React.DependencyList = []) {
  const handlerRef = useRef(handler);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    handlerRef.current = handler;
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const es = new EventSource(SSE_URL);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    const types = [
      "incident_created", "severity_upgraded", "route_recomputed",
      "cortex_alert", "sim_started", "responders_seeded", "state_reset", "ready",
    ];
    const listeners: Array<[string, (e: MessageEvent) => void]> = [];
    for (const t of types) {
      const cb = (e: MessageEvent) => {
        try {
          const data = e.data ? JSON.parse(e.data) : {};
          const seq = e.lastEventId ? Number(e.lastEventId) : undefined;
          handlerRef.current({ type: t, data, sequence_id: seq });
        } catch {
          // ignore malformed events
        }
      };
      es.addEventListener(t, cb);
      listeners.push([t, cb]);
    }

    return () => {
      for (const [t, cb] of listeners) es.removeEventListener(t, cb);
      es.close();
    };
  }, []);

  return { connected };
}
