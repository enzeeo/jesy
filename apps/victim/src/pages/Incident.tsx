import type { DeviceFlag, IncidentCategory } from '@disaster/types';
import { DEVICE_FLAGS, INCIDENT_CATEGORIES } from '@disaster/types';
import {
  AlertTriangle,
  ArrowLeft,
  Bolt,
  Droplets,
  Flame,
  Heart,
  HelpCircle,
  Loader2,
  MapPin,
  Send,
  Truck,
  Users,
} from 'lucide-react';
import type { ComponentType, SVGProps } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import Chip from '../components/Chip';
import ModePill from '../components/ModePill';
import { getVictimAdapter } from '../lib/data';
import { getOrCreateDeviceId } from '../lib/device';
import { GeoError, getCurrentPosition } from '../lib/geo';
import type { IncidentSubmitBody } from '../lib/types';

const CATEGORY_LABEL: Record<IncidentCategory, string> = {
  medical: 'Medical',
  trapped: 'Trapped',
  fire: 'Fire',
  water: 'Water / flooding',
  shelter: 'Shelter',
  power: 'Power out',
  evacuation: 'Need evacuation',
  unknown: 'Other',
};

const CATEGORY_ICON: Record<
  IncidentCategory,
  ComponentType<SVGProps<SVGSVGElement>>
> = {
  medical: Heart,
  trapped: Users,
  fire: Flame,
  water: Droplets,
  shelter: MapPin,
  power: Bolt,
  evacuation: Truck,
  unknown: HelpCircle,
};

const DEVICE_LABEL: Record<DeviceFlag, string> = {
  epipen: 'EpiPen',
  inhaler: 'Inhaler',
  insulin: 'Insulin',
  first_aid: 'First aid',
  mobility_aid: 'Mobility aid',
  oxygen: 'Oxygen',
  aed: 'AED',
};

interface CarryState {
  raw_text: string;
  needs: Partial<Record<IncidentCategory, boolean>>;
  inventory_have: DeviceFlag[];
  inventory_need: DeviceFlag[];
}

export default function Incident() {
  const navigate = useNavigate();
  const adapter = getVictimAdapter();
  const deviceId = getOrCreateDeviceId();
  const [params] = useSearchParams();

  const demo = params.get('demo'); // 'gps' | 'manual' | null
  const [rawText, setRawText] = useState('');
  const [needs, setNeeds] = useState<Set<IncidentCategory>>(new Set());
  const [have, setHave] = useState<Set<DeviceFlag>>(new Set());
  const [need, setNeed] = useState<Set<DeviceFlag>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // For demo=manual: prefill an example so reviewers can just press the button.
  // For demo=gps:    prefill an example trapped-on-roof message.
  useEffect(() => {
    if (demo === 'gps' && rawText === '') {
      setRawText(
        "I'm trapped on my roof, water is up to my chest. I'm 67 and diabetic, I have my insulin but I'm cold and shaking.",
      );
      setNeeds(new Set(['medical', 'trapped', 'water']));
      setHave(new Set(['insulin']));
    } else if (demo === 'manual' && rawText === '') {
      setRawText(
        "My phone GPS isn't working but I can describe where I am.",
      );
      setNeeds(new Set(['shelter']));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demo]);

  function toggle<T>(set: Set<T>, value: T): Set<T> {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  }

  const carryState = useMemo<CarryState>(
    () => ({
      raw_text: rawText,
      needs: Object.fromEntries(
        Array.from(needs).map((k) => [k, true]),
      ) as Partial<Record<IncidentCategory, boolean>>,
      inventory_have: Array.from(have),
      inventory_need: Array.from(need),
    }),
    [rawText, needs, have, need],
  );

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (rawText.trim().length === 0) {
      setError('Please describe your situation in a few words.');
      return;
    }

    setSubmitting(true);
    try {
      const coords = await getCurrentPosition({ timeoutMs: 6000 });
      const body: IncidentSubmitBody = {
        device_id: deviceId,
        location: {
          source: 'gps',
          lat: coords.lat,
          lng: coords.lng,
          accuracy_m: coords.accuracy_m,
        },
        raw_text: rawText.trim(),
        needs: carryState.needs,
        inventory_have: carryState.inventory_have,
        inventory_need: carryState.inventory_need,
        timestamp: new Date().toISOString(),
      };
      const { incident_id } = await adapter.submitIncident(body);
      // Kick off the demo cycle so reviewers see the status states evolve.
      adapter.cycleDemoStatuses(incident_id);
      navigate(`/status/${incident_id}`);
    } catch (err) {
      if (err instanceof GeoError) {
        // GPS unavailable → manual location flow with our form state in tow.
        navigate('/manual-location', { state: carryState });
        return;
      }
      setError(
        err instanceof Error
          ? err.message
          : 'Something went wrong sending your message. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col bg-zinc-950">
      <header className="mx-auto w-full max-w-md px-5 pt-[env(safe-area-inset-top)]">
        <div className="flex items-center justify-between pt-4">
          <Link
            to="/"
            className="inline-flex items-center gap-1 text-sm font-medium text-zinc-400 hover:text-zinc-200"
            aria-label="Back to home"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Home
          </Link>
          <ModePill />
        </div>
      </header>

      <main className="mx-auto w-full max-w-md flex-1 px-5 pb-10 pt-6">
        <h1 className="text-2xl font-semibold text-zinc-50">
          Tell us what is happening
        </h1>
        <p className="mt-2 text-base leading-relaxed text-zinc-300">
          A few words is enough. We will read it carefully.
        </p>

        <form onSubmit={onSubmit} className="mt-6 space-y-6">
          <div>
            <label
              htmlFor="raw_text"
              className="block text-sm font-medium text-zinc-300"
            >
              Describe your situation
            </label>
            <textarea
              id="raw_text"
              required
              rows={5}
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              className="mt-2 block w-full resize-y rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-lg leading-relaxed text-zinc-50 placeholder-zinc-500"
              placeholder="e.g. I'm trapped in my attic with my niece. Water is rising fast."
            />
          </div>

          <fieldset>
            <legend className="text-sm font-medium text-zinc-300">
              What is going on?
            </legend>
            <p className="mt-1 text-xs text-zinc-500">Tap any that apply.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {INCIDENT_CATEGORIES.map((c) => {
                const Icon = CATEGORY_ICON[c];
                return (
                  <Chip
                    key={c}
                    active={needs.has(c)}
                    onToggle={() => setNeeds((s) => toggle(s, c))}
                    icon={<Icon className="h-4 w-4" aria-hidden />}
                  >
                    {CATEGORY_LABEL[c]}
                  </Chip>
                );
              })}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-medium text-zinc-300">
              I have
            </legend>
            <div className="mt-3 flex flex-wrap gap-2">
              {DEVICE_FLAGS.map((d) => (
                <Chip
                  key={d}
                  active={have.has(d)}
                  onToggle={() => setHave((s) => toggle(s, d))}
                  ariaLabel={`I have ${DEVICE_LABEL[d]}`}
                >
                  {DEVICE_LABEL[d]}
                </Chip>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-medium text-zinc-300">
              I need
            </legend>
            <div className="mt-3 flex flex-wrap gap-2">
              {DEVICE_FLAGS.map((d) => (
                <Chip
                  key={d}
                  active={need.has(d)}
                  onToggle={() => setNeed((s) => toggle(s, d))}
                  ariaLabel={`I need ${DEVICE_LABEL[d]}`}
                >
                  {DEVICE_LABEL[d]}
                </Chip>
              ))}
            </div>
          </fieldset>

          {error && (
            <div className="flex items-start gap-2 rounded-xl bg-rose-500/10 p-4 text-sm text-rose-200 ring-1 ring-rose-500/40">
              <AlertTriangle className="mt-0.5 h-4 w-4" aria-hidden />
              <p>{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="inline-flex min-h-[64px] w-full items-center justify-center gap-3 rounded-2xl bg-rose-600 px-6 py-4 text-xl font-semibold text-white shadow-lg shadow-rose-900/40 transition-colors hover:bg-rose-500 active:bg-rose-700 disabled:opacity-60"
          >
            {submitting ? (
              <Loader2 className="h-6 w-6 animate-spin" aria-hidden />
            ) : (
              <Send className="h-6 w-6" aria-hidden />
            )}
            {submitting ? 'Sending…' : 'Get help now'}
          </button>

          <p className="text-center text-xs text-zinc-500">
            We will use your phone location if it is available. If not, we will
            ask you to describe where you are.
          </p>
        </form>
      </main>
    </div>
  );
}
