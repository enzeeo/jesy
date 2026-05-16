import { FIXTURE_VICTIM_STATUSES } from '@disaster/fixtures';
import type { VictimStatusView } from '@disaster/types';
import {
  ArrowLeft,
  ChevronRight,
  Heart,
  Info,
  MapPin,
  MessageSquare,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import ModePill from '../components/ModePill';
import StatusCard from '../components/StatusCard';

const STATE_ORDER: VictimStatusView['state'][] = [
  'received',
  'triaging',
  'assigned',
  'low_confidence_location',
  'unmet_resource',
];

const STATE_LABEL: Record<VictimStatusView['state'], string> = {
  received: '1 — Received',
  triaging: '2 — Triaging',
  assigned: '3 — Help assigned',
  low_confidence_location: '4 — Low-confidence location',
  unmet_resource: '5 — Partial assignment',
};

interface FastPathCardProps {
  to: string;
  title: string;
  body: string;
  icon: ReactNode;
}

function FastPathCard({ to, title, body, icon }: FastPathCardProps) {
  return (
    <Link
      to={to}
      className="flex items-center gap-4 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4 ring-1 ring-transparent transition-colors hover:border-zinc-700 hover:ring-zinc-700"
    >
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30">
        {icon}
      </span>
      <span className="flex-1">
        <span className="block text-base font-semibold text-zinc-50">
          {title}
        </span>
        <span className="mt-0.5 block text-sm text-zinc-400">{body}</span>
      </span>
      <ChevronRight className="h-5 w-5 shrink-0 text-zinc-500" aria-hidden />
    </Link>
  );
}

export default function Demo() {
  return (
    <div className="flex min-h-full flex-col bg-zinc-950">
      <header className="mx-auto w-full max-w-md px-5 pt-[env(safe-area-inset-top)]">
        <div className="flex items-center justify-between pt-4">
          <Link
            to="/"
            className="inline-flex items-center gap-1 text-sm font-medium text-zinc-400 hover:text-zinc-200"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Home
          </Link>
          <ModePill />
        </div>
      </header>

      <main className="mx-auto w-full max-w-md flex-1 px-5 pb-14 pt-4">
        <h1 className="text-2xl font-semibold text-zinc-50">
          Reviewer preview
        </h1>
        <section
          aria-label="Fixture preview banner"
          className="mt-3 rounded-2xl bg-amber-500/10 p-4 ring-1 ring-amber-500/30"
        >
          <div className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 text-amber-300" aria-hidden />
            <p className="text-sm leading-relaxed text-amber-100">
              <span className="font-semibold">Fixture UI Preview.</span> The
              five victim status states the system will produce. The final
              demo uses live Snowflake processing.
            </p>
          </div>
        </section>

        <section className="mt-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">
            Fast paths
          </h2>
          <div className="mt-3 space-y-3">
            <FastPathCard
              to="/incident?demo=gps"
              title="Go through the GPS flow"
              body="Pre-fills a trapped-on-roof story and submits with browser GPS."
              icon={<MessageSquare className="h-5 w-5" aria-hidden />}
            />
            <FastPathCard
              to="/incident?demo=manual&gps=off"
              title="Go through the manual-location flow"
              body="Forces GPS off so the place-description fallback is shown."
              icon={<MapPin className="h-5 w-5" aria-hidden />}
            />
            <FastPathCard
              to="/status/inc-001"
              title="Show me what 'help assigned' looks like"
              body="Jumps straight to the assigned status for Sarah W."
              icon={<Heart className="h-5 w-5" aria-hidden />}
            />
          </div>
        </section>

        <section className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">
            All five status states
          </h2>
          <div className="mt-3 space-y-4">
            {STATE_ORDER.map((state) => {
              const fixture = FIXTURE_VICTIM_STATUSES[state];
              if (!fixture) return null;
              return (
                <div key={state}>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                    {STATE_LABEL[state]}
                  </p>
                  <StatusCard status={fixture} compact />
                </div>
              );
            })}
          </div>
        </section>

        <p className="mt-10 text-center text-xs text-zinc-500">
          Final judged demo flips this to live Snowflake processing.
        </p>
      </main>
    </div>
  );
}
