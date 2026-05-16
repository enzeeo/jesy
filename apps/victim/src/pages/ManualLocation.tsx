import type { DeviceFlag, IncidentCategory } from '@disaster/types';
import { ArrowLeft, Loader2, MapPin, Send } from 'lucide-react';
import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import ModePill from '../components/ModePill';
import { getVictimAdapter } from '../lib/data';
import { getOrCreateDeviceId } from '../lib/device';
import type { IncidentSubmitBody } from '../lib/types';

interface CarryState {
  raw_text?: string;
  needs?: Partial<Record<IncidentCategory, boolean>>;
  inventory_have?: DeviceFlag[];
  inventory_need?: DeviceFlag[];
  /** Optional pre-filled description (e.g. when reviewer comes back from Status). */
  description?: string;
}

export default function ManualLocation() {
  const navigate = useNavigate();
  const location = useLocation();
  const carry = (location.state ?? {}) as CarryState;
  const adapter = getVictimAdapter();
  const deviceId = getOrCreateDeviceId();

  const [description, setDescription] = useState(carry.description ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (description.trim().length === 0) {
      setError('Please describe where you are in a few words.');
      return;
    }
    setSubmitting(true);
    try {
      const body: IncidentSubmitBody = {
        device_id: deviceId,
        location: {
          source: 'place_description_udf',
          description: description.trim(),
        },
        raw_text:
          (carry.raw_text ?? '').trim() || description.trim(),
        needs: carry.needs ?? {},
        inventory_have: carry.inventory_have ?? [],
        inventory_need: carry.inventory_need ?? [],
        timestamp: new Date().toISOString(),
      };
      const { incident_id } = await adapter.submitIncident(body);
      adapter.cycleDemoStatuses(incident_id);
      navigate(`/status/${incident_id}`);
    } catch (err) {
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
            to="/incident"
            className="inline-flex items-center gap-1 text-sm font-medium text-zinc-400 hover:text-zinc-200"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back
          </Link>
          <ModePill />
        </div>
      </header>

      <main className="mx-auto w-full max-w-md flex-1 px-5 pb-10 pt-6">
        <div className="inline-flex items-center gap-2 rounded-full bg-amber-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-amber-200 ring-1 ring-amber-500/30">
          <MapPin className="h-3.5 w-3.5" aria-hidden />
          Locating you
        </div>

        <h1 className="mt-3 text-2xl font-semibold leading-tight text-zinc-50">
          Your phone GPS isn't working.
        </h1>
        <p className="mt-3 text-base leading-relaxed text-zinc-300">
          Describe where you are — nearby buildings, restaurants, gas stations,
          schools, or cross-streets. Anything you can see.
        </p>

        <form onSubmit={onSubmit} className="mt-6 space-y-5">
          <textarea
            aria-label="Place description"
            required
            rows={6}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="block w-full resize-y rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-lg leading-relaxed text-zinc-50 placeholder-zinc-500"
            placeholder="near the McDonald's and gas station off I-10 service road, big white church across the street…"
          />

          {error && (
            <p className="rounded-xl bg-rose-500/10 p-3 text-sm text-rose-200 ring-1 ring-rose-500/40">
              {error}
            </p>
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
            {submitting ? 'Sending…' : 'Send'}
          </button>

          <p className="text-center text-sm text-zinc-400">
            We'll do our best with what you describe.
          </p>
        </form>
      </main>
    </div>
  );
}
