import type { ResourceType, VictimStatusView } from '@disaster/types';
import { severityBand } from '@disaster/types';
import {
  AlertTriangle,
  Bandage,
  CheckCircle2,
  Heart,
  Info,
  Loader2,
  MapPin,
  Phone,
  Pill,
  Shield,
  Stethoscope,
  Truck,
  Users,
} from 'lucide-react';
import type { ComponentType, ReactNode, SVGProps } from 'react';

import { formatEta, severityBandToLabel, RESOURCE_LABEL } from '../lib/format';

const RESOURCE_ICON: Record<ResourceType, ComponentType<SVGProps<SVGSVGElement>>> = {
  police: Shield,
  fire: Bandage,
  ems: Truck,
  paramedic: Heart,
  nurse: Pill,
  doctor: Stethoscope,
  volunteer: Users,
};

const RESOURCE_TONE: Record<ResourceType, string> = {
  police: 'text-sky-200 bg-sky-500/15 ring-sky-500/30',
  fire: 'text-rose-200 bg-rose-500/15 ring-rose-500/30',
  ems: 'text-amber-200 bg-amber-500/15 ring-amber-500/30',
  paramedic: 'text-orange-200 bg-orange-500/15 ring-orange-500/30',
  nurse: 'text-pink-200 bg-pink-500/15 ring-pink-500/30',
  doctor: 'text-purple-200 bg-purple-500/15 ring-purple-500/30',
  volunteer: 'text-emerald-200 bg-emerald-500/15 ring-emerald-500/30',
};

interface StateMeta {
  title: string;
  body: string;
  /** Tone tag for the panel ring/background. */
  tone: 'received' | 'triaging' | 'assigned' | 'amber' | 'amber-strong';
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const STATE_META: Record<VictimStatusView['state'], StateMeta> = {
  received: {
    title: 'Help received',
    body: "We're reading your message. You don't need to do anything else right now.",
    tone: 'received',
    Icon: CheckCircle2,
  },
  triaging: {
    title: 'Matching the right help to you',
    body: 'This takes a few seconds. Please stay where you are if it is safe.',
    tone: 'triaging',
    Icon: Loader2,
  },
  assigned: {
    title: 'Help is on the way',
    body: "We've sent the closest team that can help. You will see them soon.",
    tone: 'assigned',
    Icon: Heart,
  },
  low_confidence_location: {
    title: "We're using the description you gave us",
    body:
      "If you can, share more about what's around you — buildings, signs, or cross-streets. Every detail helps.",
    tone: 'amber',
    Icon: MapPin,
  },
  unmet_resource: {
    title: 'An EMT is on the way',
    body:
      'A doctor is being requested for follow-up. You are not being forgotten — we are still working on it.',
    tone: 'amber-strong',
    Icon: AlertTriangle,
  },
};

const TONE_CLASS: Record<StateMeta['tone'], string> = {
  received: 'ring-sky-500/30 bg-sky-500/5',
  triaging: 'ring-amber-500/30 bg-amber-500/5',
  assigned: 'ring-emerald-500/30 bg-emerald-500/5',
  amber: 'ring-amber-500/40 bg-amber-500/10',
  'amber-strong': 'ring-orange-500/40 bg-orange-500/10',
};

interface StatusCardProps {
  status: VictimStatusView;
  /**
   * Optional CTA at the bottom of the card. The Status page uses this for
   * "Add more details" → manual-location; the Demo page does not pass one.
   */
  cta?: ReactNode;
  /** Hide the redundant incident header on stacked Demo cards. */
  compact?: boolean;
}

export default function StatusCard({ status, cta, compact = false }: StatusCardProps) {
  const meta = STATE_META[status.state] ?? STATE_META.received;
  const tone = TONE_CLASS[meta.tone];
  const band =
    status.severity_score != null ? severityBand(status.severity_score) : null;
  const sevTone =
    band === 'critical'
      ? 'text-rose-200 ring-rose-500/40 bg-rose-500/15'
      : band === 'high'
        ? 'text-orange-200 ring-orange-500/40 bg-orange-500/15'
        : band === 'medium'
          ? 'text-amber-200 ring-amber-500/40 bg-amber-500/15'
          : band === 'low'
            ? 'text-emerald-200 ring-emerald-500/40 bg-emerald-500/15'
            : 'text-sky-200 ring-sky-500/40 bg-sky-500/15';

  return (
    <section
      aria-live="polite"
      className={`rounded-3xl p-5 ring-1 ${tone}`}
    >
      <header className="mb-3 flex items-start gap-3">
        <span className="mt-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/5 ring-1 ring-white/10">
          <meta.Icon
            className={`h-5 w-5 ${
              status.state === 'triaging' ? 'animate-spin text-amber-300' : 'text-zinc-100'
            }`}
            aria-hidden
          />
        </span>
        <div className="flex-1">
          <h2 className="text-xl font-semibold leading-tight text-zinc-50">
            {meta.title}
          </h2>
          <p className="mt-1 text-base leading-relaxed text-zinc-300">
            {status.message || meta.body}
          </p>
        </div>
      </header>

      {!compact && band && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-semibold ring-1 ${sevTone}`}
            aria-label={`Severity: ${severityBandToLabel(band)}`}
          >
            <Info className="h-3.5 w-3.5" aria-hidden />
            {severityBandToLabel(band)}
          </span>
          {status.eta_sec != null && (
            <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800/80 px-3 py-1 text-sm font-semibold text-zinc-100 ring-1 ring-zinc-700">
              <Phone className="h-3.5 w-3.5" aria-hidden />
              ETA {formatEta(status.eta_sec)}
            </span>
          )}
        </div>
      )}

      {status.assigned_resource_types && status.assigned_resource_types.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2" aria-label="Help on the way">
          {status.assigned_resource_types.map((rt) => {
            const Icon = RESOURCE_ICON[rt];
            return (
              <li
                key={rt}
                className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium ring-1 ${RESOURCE_TONE[rt]}`}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {RESOURCE_LABEL[rt]}
              </li>
            );
          })}
        </ul>
      )}

      {status.state === 'low_confidence_location' && status.location_confidence != null && (
        <p className="mt-4 text-sm text-amber-200/80">
          Location confidence: {Math.round(status.location_confidence * 100)}%
        </p>
      )}

      {cta && <div className="mt-5">{cta}</div>}
    </section>
  );
}
