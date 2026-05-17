"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { getOrCreateDeviceId } from "@/lib/device";
import { GeoError, getCurrentPosition, getFallbackLocation } from "@/lib/geo";
import { newConversationId } from "@/lib/elevenlabs";

interface CallButtonProps {
  agentId?: string;
}

/**
 * Big red "Call for help" button. Requests mic + geolocation up-front (mic
 * permission must be granted before the agent can stream audio), then
 * navigates to /call with the call context in URL params so CallPanel can
 * start the ElevenLabs session with the right overrides.
 *
 * Fallback paths:
 *   - mic denied   → shows error, suggests text form
 *   - geo denied   → uses fallback lat/lng (configured Asheville default)
 *   - no agent id  → shows config-missing notice
 */
export function CallButton({ agentId }: CallButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onClick() {
    setError(null);

    if (!agentId) {
      setError(
        "Voice intake is not configured (missing NEXT_PUBLIC_ELEVENLABS_AGENT_ID). Use the text form below.",
      );
      return;
    }

    setPending(true);
    try {
      if (typeof navigator === "undefined" || !navigator.mediaDevices) {
        setError("This browser does not support voice intake. Use the text form below.");
        return;
      }

      try {
        const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        micStream.getTracks().forEach((track) => track.stop());
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : String(caught);
        setError(`Microphone permission required: ${message}`);
        return;
      }

      let lat: number;
      let lng: number;
      let geoSource: "gps" | "fallback" = "gps";
      try {
        const coords = await getCurrentPosition();
        lat = coords.lat;
        lng = coords.lng;
      } catch (caught) {
        if (caught instanceof GeoError) {
          const fallback = getFallbackLocation();
          lat = fallback.lat;
          lng = fallback.lng;
          geoSource = "fallback";
        } else {
          throw caught;
        }
      }

      const deviceId = getOrCreateDeviceId();
      const conversationId = newConversationId();
      const params = new URLSearchParams({
        agent: agentId,
        conv: conversationId,
        lat: String(lat),
        lng: String(lng),
        device: deviceId,
        geo: geoSource,
      });
      router.push(`/call?${params.toString()}`);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid gap-2">
      <button
        type="button"
        onClick={onClick}
        disabled={pending}
        className="min-h-20 touch-manipulation select-none border border-sev-immediate bg-sev-immediate px-6 py-5 text-left text-2xl font-semibold text-white shadow-lg shadow-black/30 disabled:opacity-60"
      >
        {pending ? "Connecting..." : "Call for help"}
      </button>
      {error && (
        <p className="border border-sev-immediate/40 bg-sev-immediate/10 p-3 text-sm text-rose-100">
          {error}
        </p>
      )}
    </div>
  );
}
