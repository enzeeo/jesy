"use client";

import Link from "next/link";
import { CallerShell } from "@/components/CallerShell";

export default function Home() {
  return (
    <CallerShell>
      <section>
        <h1 className="text-4xl font-semibold tracking-tight text-fg-primary">Disaster Relief</h1>
        <p className="mt-4 text-lg leading-8 text-fg-secondary">
          If you need help, send a short message. Your request goes to the same dispatch system responders use.
        </p>
      </section>

      <div className="mt-8 grid gap-3">
        <button
          type="button"
          onClick={() => alert("Voice support is coming soon. Please use Text for now.")}
          className="min-h-20 border border-sev-immediate bg-sev-immediate px-6 py-5 text-left text-2xl font-semibold text-white shadow-lg shadow-black/30"
        >
          Call for help
        </button>
        <Link
          href="/incident"
          className="min-h-20 border border-border-strong bg-bg-panel px-6 py-5 text-2xl font-semibold text-fg-primary hover:bg-bg-elev"
        >
          Text for help
        </Link>
      </div>

      <section className="mt-8 border border-status-warn/40 bg-status-warn/10 p-5">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-amber-200">Mention what matters</p>
        <ul className="mt-3 grid gap-2 text-base leading-7 text-amber-50/90">
          <li>Where you are</li>
          <li>What happened</li>
          <li>Who is hurt</li>
          <li>What you have</li>
          <li>What you need</li>
        </ul>
      </section>

      <Link href="/onboard" className="mt-8 inline-block text-sm font-semibold text-fg-secondary underline-offset-4 hover:text-fg-primary hover:underline">
        Save your info optional
      </Link>
    </CallerShell>
  );
}
