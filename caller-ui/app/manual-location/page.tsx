"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CallerShell } from "@/components/CallerShell";
import { api } from "@/lib/api";
import { getOrCreateDeviceId } from "@/lib/device";
import { getFallbackLocation } from "@/lib/geo";
import type { CallerDraft } from "@/lib/types";

const DRAFT_KEY = "disaster.caller.pending_report";

const emptyDraft: CallerDraft = {
  raw_text: "",
  needs: {},
  inventory_have: [],
  inventory_need: [],
};

function readDraft(): CallerDraft {
  if (typeof window === "undefined") return emptyDraft;
  const savedDraft = window.sessionStorage.getItem(DRAFT_KEY);
  if (!savedDraft) return emptyDraft;
  try {
    return JSON.parse(savedDraft) as CallerDraft;
  } catch {
    window.sessionStorage.removeItem(DRAFT_KEY);
    return emptyDraft;
  }
}

export default function ManualLocationPage() {
  const router = useRouter();
  const [draft] = useState<CallerDraft>(() => readDraft());
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!description.trim()) {
      setError("Please describe where you are in a few words.");
      return;
    }

    setSubmitting(true);
    try {
      const fallbackLocation = getFallbackLocation();
      const response = await api.createIncident({
        ...draft,
        raw_text: draft.raw_text.trim() || description.trim(),
        device_id: getOrCreateDeviceId(),
        timestamp: new Date().toISOString(),
        location: {
          source: "manual",
          lat: fallbackLocation.lat,
          lng: fallbackLocation.lng,
          description: description.trim(),
        },
      });
      window.sessionStorage.removeItem(DRAFT_KEY);
      router.push(`/status/${response.incident_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong sending your message.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <CallerShell backHref="/incident" backLabel="Back">
      <p className="inline-block border border-status-warn/40 bg-status-warn/10 px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] text-amber-200">
        Location needed
      </p>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight text-fg-primary">Your phone GPS is not working.</h1>
      <p className="mt-3 text-base leading-7 text-fg-secondary">
        Describe nearby buildings, roads, signs, schools, or anything you can see.
      </p>

      <form onSubmit={onSubmit} className="mt-7 grid gap-5">
        <textarea
          aria-label="Place description"
          required
          rows={6}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="border border-border-strong bg-bg-panel px-4 py-3 text-lg leading-7 text-fg-primary placeholder:text-fg-muted"
          placeholder="Near the gas station off the service road, big white church across the street."
        />

        {error && <p className="border border-sev-immediate/40 bg-sev-immediate/10 p-3 text-sm text-rose-100">{error}</p>}

        <button type="submit" disabled={submitting} className="min-h-16 bg-sev-immediate px-6 py-4 text-xl font-semibold text-white disabled:opacity-60">
          {submitting ? "Sending..." : "Send"}
        </button>
      </form>
    </CallerShell>
  );
}
