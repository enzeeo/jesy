"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * P1 #8 frontend: dedupe severity_upgraded events by sequence_id.
 *
 * - A new sequence_id starts a 2s flash for the target incident_id
 * - Repeated sequence_ids are ignored (the dedupe contract)
 * - After 2s, the entry is auto-cleared
 *
 * Returns:
 *   flashing       : Set of incident_ids currently flashing
 *   register(seq, incident_id) : called by the SSE handler
 */
const FLASH_MS = 2000;

export function useSeverityFlash() {
  const [flashing, setFlashing] = useState<Set<string>>(new Set());
  const [seen, setSeen] = useState<Set<number>>(new Set());

  const register = useCallback((sequence_id: number | undefined, incident_id: string) => {
    if (sequence_id == null) return;
    setSeen((prev) => {
      if (prev.has(sequence_id)) return prev;
      const next = new Set(prev);
      next.add(sequence_id);
      // also start flash
      setFlashing((flashPrev) => {
        const f = new Set(flashPrev);
        f.add(incident_id);
        return f;
      });
      setTimeout(() => {
        setFlashing((flashPrev) => {
          const f = new Set(flashPrev);
          f.delete(incident_id);
          return f;
        });
      }, FLASH_MS);
      return next;
    });
  }, []);

  // Garbage-collect old sequence_ids so the Set doesn't grow unbounded
  useEffect(() => {
    const interval = setInterval(() => {
      setSeen((prev) => {
        if (prev.size < 1000) return prev;
        // Keep only the top half (most recent ids)
        const arr = Array.from(prev).sort((a, b) => b - a).slice(0, 500);
        return new Set(arr);
      });
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  return { flashing, register };
}
