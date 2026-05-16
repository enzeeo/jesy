import type { DeviceFlag, VictimStatusView } from '@disaster/types';
import { DEVICE_FLAGS } from '@disaster/types';
import { ArrowLeft, MapPin, Pencil, Phone, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import Chip from '../components/Chip';
import ModePill from '../components/ModePill';
import StatusCard from '../components/StatusCard';
import { getVictimAdapter } from '../lib/data';
import { formatTimeSince } from '../lib/format';

const DEVICE_LABEL: Record<DeviceFlag, string> = {
  epipen: 'EpiPen',
  inhaler: 'Inhaler',
  insulin: 'Insulin',
  first_aid: 'First aid',
  mobility_aid: 'Mobility aid',
  oxygen: 'Oxygen',
  aed: 'AED',
};

export default function Status() {
  const { id = 'inc-001' } = useParams();
  const navigate = useNavigate();
  const adapter = getVictimAdapter();

  const [status, setStatus] = useState<VictimStatusView | null>(null);
  const [submittedAt] = useState(() => new Date().toISOString());
  const [now, setNow] = useState(() => Date.now());

  // Inventory recap — kept locally for the fixture preview. A real submit
  // would PATCH /v1/incidents/:id/inventory; here we just update local state.
  const [editing, setEditing] = useState(false);
  const [have, setHave] = useState<Set<DeviceFlag>>(new Set());
  const [need, setNeed] = useState<Set<DeviceFlag>>(new Set());

  useEffect(() => {
    const unsubscribe = adapter.subscribeStatus(id, setStatus);
    return unsubscribe;
  }, [adapter, id]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  function toggle<T>(set: Set<T>, value: T): Set<T> {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  }

  const carry = useMemo(
    () => ({
      raw_text: '',
      needs: {},
      inventory_have: Array.from(have),
      inventory_need: Array.from(need),
    }),
    [have, need],
  );

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

      <main className="mx-auto w-full max-w-md flex-1 px-5 pb-12 pt-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-zinc-500">
              Incident
            </p>
            <p className="text-sm font-semibold text-zinc-200">{id}</p>
          </div>
          <p className="text-xs text-zinc-400">
            Sent {formatTimeSince(submittedAt, now)}
          </p>
        </div>

        <div className="mt-5">
          {status ? (
            <StatusCard
              status={status}
              cta={
                status.state === 'low_confidence_location' ? (
                  <button
                    type="button"
                    onClick={() =>
                      navigate('/manual-location', {
                        state: { description: status.message ?? '' },
                      })
                    }
                    className="inline-flex min-h-[48px] items-center gap-2 rounded-2xl border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-base font-semibold text-amber-100 hover:bg-amber-500/20"
                  >
                    <MapPin className="h-4 w-4" aria-hidden />
                    Add more details
                  </button>
                ) : null
              }
            />
          ) : (
            <div
              role="status"
              aria-live="polite"
              className="rounded-3xl bg-zinc-900/60 p-5 ring-1 ring-zinc-800"
            >
              <p className="text-base text-zinc-300">
                We are connecting to your help request…
              </p>
            </div>
          )}
        </div>

        <section
          aria-label="What you have and need"
          className="mt-6 rounded-3xl bg-zinc-900/60 p-5 ring-1 ring-zinc-800"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-zinc-100">
              What you have and need
            </h3>
            <button
              type="button"
              onClick={() => setEditing((v) => !v)}
              className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-3 py-1 text-xs font-semibold text-zinc-200 hover:bg-zinc-700"
            >
              <Pencil className="h-3.5 w-3.5" aria-hidden />
              {editing ? 'Done' : 'Edit'}
            </button>
          </div>

          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              I have
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {DEVICE_FLAGS.map((d) => (
                <Chip
                  key={`have-${d}`}
                  active={have.has(d)}
                  readOnly={!editing}
                  onToggle={() => setHave((s) => toggle(s, d))}
                >
                  {DEVICE_LABEL[d]}
                </Chip>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              I need
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {DEVICE_FLAGS.map((d) => (
                <Chip
                  key={`need-${d}`}
                  active={need.has(d)}
                  readOnly={!editing}
                  onToggle={() => setNeed((s) => toggle(s, d))}
                >
                  {DEVICE_LABEL[d]}
                </Chip>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-6 flex items-center gap-3 rounded-2xl bg-zinc-900/60 p-4 ring-1 ring-zinc-800">
          <ShieldCheck className="h-5 w-5 text-emerald-400" aria-hidden />
          <p className="text-sm text-zinc-300">
            You don't need to do anything else. Stay where it is safe and keep
            this screen open.
          </p>
        </section>

        <p className="mt-6 text-center text-xs text-zinc-500">
          If your situation changes, tap{' '}
          <Phone className="inline h-3 w-3" aria-hidden /> Call again from the
          home screen.
        </p>

        {/* carry is only kept here so future inventory PATCH wiring is easy */}
        <span className="hidden" aria-hidden data-carry={JSON.stringify(carry)} />
      </main>
    </div>
  );
}
