"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { CallerShell } from "@/components/CallerShell";
import { CallPanel } from "@/components/CallPanel";

function CallScreen() {
  const params = useSearchParams();
  const agentId = params.get("agent") ?? "";
  const conversationId = params.get("conv") ?? "";
  const lat = Number.parseFloat(params.get("lat") ?? "");
  const lng = Number.parseFloat(params.get("lng") ?? "");
  const deviceId = params.get("device") ?? "";
  const geoSource = (params.get("geo") === "fallback" ? "fallback" : "gps") as
    | "gps"
    | "fallback";

  const ready =
    agentId.length > 0 &&
    conversationId.length > 0 &&
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    deviceId.length > 0;

  if (!ready) {
    return (
      <CallerShell backHref="/" backLabel="Home">
        <h1 className="text-2xl font-semibold text-fg-primary">Call not ready</h1>
        <p className="mt-3 text-base leading-7 text-fg-secondary">
          Something went wrong setting up your call. Please go back and try again.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block border border-border-strong bg-bg-panel px-5 py-3 text-base font-semibold text-fg-primary hover:bg-bg-elev"
        >
          Back home
        </Link>
      </CallerShell>
    );
  }

  return (
    <CallerShell backHref="/" backLabel="End call">
      <h1 className="text-2xl font-semibold text-fg-primary">You&apos;re connected</h1>
      <p className="mt-2 text-base leading-7 text-fg-secondary">
        Speak naturally. The assistant will listen and ask follow-up questions.
      </p>

      <div className="mt-6">
        <CallPanel
          agentId={agentId}
          conversationId={conversationId}
          lat={lat}
          lng={lng}
          deviceId={deviceId}
          geoSource={geoSource}
        />
      </div>
    </CallerShell>
  );
}

export default function CallPage() {
  return (
    <Suspense
      fallback={
        <CallerShell backHref="/" backLabel="Home">
          <p className="text-base text-fg-secondary">Preparing call...</p>
        </CallerShell>
      }
    >
      <CallScreen />
    </Suspense>
  );
}
