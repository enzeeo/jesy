"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CallerShell } from "@/components/CallerShell";
import { Chip } from "@/components/Chip";
import { api } from "@/lib/api";
import { getOrCreateDeviceId } from "@/lib/device";
import { GeoError, getCurrentPosition } from "@/lib/geo";
import type { CallerDraft, DeviceFlag, IncidentCategory } from "@/lib/types";
import { DEVICE_FLAGS, INCIDENT_CATEGORIES } from "@/lib/types";

const CATEGORY_LABEL: Record<IncidentCategory, string> = {
  medical: "Medical",
  trapped: "Trapped",
  fire: "Fire",
  water: "Water / flooding",
  shelter: "Shelter",
  power: "Power out",
  evacuation: "Need evacuation",
  unknown: "Other",
};

const DEVICE_LABEL: Record<DeviceFlag, string> = {
  epipen: "EpiPen",
  inhaler: "Inhaler",
  insulin: "Insulin",
  first_aid: "First aid",
  mobility_aid: "Mobility aid",
  oxygen: "Oxygen",
  aed: "AED",
};

const DRAFT_KEY = "disaster.caller.pending_report";

function toggleSet<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export default function IncidentPage() {
  const router = useRouter();
  const [rawText, setRawText] = useState("");
  const [needs, setNeeds] = useState<Set<IncidentCategory>>(new Set());
  const [have, setHave] = useState<Set<DeviceFlag>>(new Set());
  const [need, setNeed] = useState<Set<DeviceFlag>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const draft = useMemo<CallerDraft>(
    () => ({
      raw_text: rawText,
      needs: Object.fromEntries(Array.from(needs).map((key) => [key, true])) as Partial<Record<IncidentCategory, boolean>>,
      inventory_have: Array.from(have),
      inventory_need: Array.from(need),
    }),
    [rawText, needs, have, need],
  );

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!rawText.trim()) {
      setError("Please describe your situation in a few words.");
      return;
    }

    setSubmitting(true);
    try {
      const coords = await getCurrentPosition();
      const deviceId = getOrCreateDeviceId();
      const response = await api.createIncident({
        ...draft,
        device_id: deviceId,
        timestamp: new Date().toISOString(),
        location: {
          source: "gps",
          lat: coords.lat,
          lng: coords.lng,
          description: `GPS location from caller device${coords.accuracy_m ? `, accuracy ${Math.round(coords.accuracy_m)}m` : ""}`,
        },
      });
      router.push(`/status/${response.incident_id}`);
    } catch (caught) {
      if (caught instanceof GeoError) {
        window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
        router.push("/manual-location");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Something went wrong sending your message.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <CallerShell backHref="/" backLabel="Home">
      <h1 className="text-3xl font-semibold tracking-tight text-fg-primary">Tell us what is happening</h1>
      <p className="mt-3 text-base leading-7 text-fg-secondary">A few words is enough. We will use your phone location if available.</p>

      <form onSubmit={onSubmit} className="mt-7 grid gap-6">
        <label className="grid gap-2">
          <span className="text-sm font-semibold text-fg-secondary">Describe your situation</span>
          <textarea
            required
            rows={5}
            value={rawText}
            onChange={(event) => setRawText(event.target.value)}
            className="border border-border-strong bg-bg-panel px-4 py-3 text-lg leading-7 text-fg-primary placeholder:text-fg-muted"
            placeholder="I'm trapped in my attic with my niece. Water is rising fast."
          />
        </label>

        <fieldset>
          <legend className="text-sm font-semibold text-fg-secondary">What is going on?</legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {INCIDENT_CATEGORIES.map((category) => (
              <Chip key={category} active={needs.has(category)} onToggle={() => setNeeds((current) => toggleSet(current, category))}>
                {CATEGORY_LABEL[category]}
              </Chip>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-sm font-semibold text-fg-secondary">I have</legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {DEVICE_FLAGS.map((device) => (
              <Chip key={device} active={have.has(device)} onToggle={() => setHave((current) => toggleSet(current, device))}>
                {DEVICE_LABEL[device]}
              </Chip>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-sm font-semibold text-fg-secondary">I need</legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {DEVICE_FLAGS.map((device) => (
              <Chip key={device} active={need.has(device)} onToggle={() => setNeed((current) => toggleSet(current, device))}>
                {DEVICE_LABEL[device]}
              </Chip>
            ))}
          </div>
        </fieldset>

        {error && <p className="border border-sev-immediate/40 bg-sev-immediate/10 p-3 text-sm text-rose-100">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="min-h-16 bg-sev-immediate px-6 py-4 text-xl font-semibold text-white disabled:opacity-60"
        >
          {submitting ? "Sending..." : "Get help now"}
        </button>
      </form>
    </CallerShell>
  );
}
