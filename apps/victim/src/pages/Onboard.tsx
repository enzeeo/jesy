import type { DeviceFlag, Profile } from '@disaster/types';
import { DEVICE_FLAGS } from '@disaster/types';
import { ArrowLeft, Save, SkipForward } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';

import Chip from '../components/Chip';
import ModePill from '../components/ModePill';
import { getVictimAdapter } from '../lib/data';
import { getOrCreateDeviceId } from '../lib/device';

const CONDITIONS = [
  'diabetes',
  'asthma',
  'copd',
  'heart_condition',
  'mobility_limited',
  'nursing_mother',
  'pregnant',
  'elderly',
] as const;

type ConditionKey = (typeof CONDITIONS)[number];

const CONDITION_LABEL: Record<ConditionKey, string> = {
  diabetes: 'Diabetes',
  asthma: 'Asthma',
  copd: 'COPD',
  heart_condition: 'Heart condition',
  mobility_limited: 'Mobility limited',
  nursing_mother: 'Nursing mother',
  pregnant: 'Pregnant',
  elderly: 'Elderly',
};

const DEVICE_LABEL: Record<DeviceFlag, string> = {
  epipen: 'EpiPen',
  inhaler: 'Inhaler',
  insulin: 'Insulin',
  first_aid: 'First aid kit',
  mobility_aid: 'Mobility aid',
  oxygen: 'Oxygen',
  aed: 'AED',
};

interface FormValues {
  name: string;
  age: string;
  contact_name: string;
  contact_phone: string;
}

export default function Onboard() {
  const navigate = useNavigate();
  const adapter = getVictimAdapter();
  const deviceId = getOrCreateDeviceId();

  const [conditions, setConditions] = useState<Set<ConditionKey>>(new Set());
  const [devices, setDevices] = useState<Set<DeviceFlag>>(new Set());
  const [saving, setSaving] = useState(false);

  const { register, handleSubmit, reset } = useForm<FormValues>({
    defaultValues: {
      name: '',
      age: '',
      contact_name: '',
      contact_phone: '',
    },
  });

  useEffect(() => {
    let cancelled = false;
    void adapter.loadProfile(deviceId).then((p) => {
      if (cancelled || !p) return;
      reset({
        name: p.name,
        age: p.age > 0 ? String(p.age) : '',
        contact_name: p.emergency_contact?.name ?? '',
        contact_phone: p.emergency_contact?.phone ?? '',
      });
      setConditions(new Set(p.conditions as ConditionKey[]));
      setDevices(new Set(p.devices_owned));
    });
    return () => {
      cancelled = true;
    };
  }, [adapter, deviceId, reset]);

  function toggle<T>(set: Set<T>, value: T): Set<T> {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  }

  async function onSubmit(values: FormValues) {
    setSaving(true);
    try {
      const profile: Profile = {
        profile_id: `pf-${deviceId}`,
        device_id: deviceId,
        name: values.name.trim(),
        age: Number.parseInt(values.age, 10) || 0,
        conditions: Array.from(conditions),
        devices_owned: Array.from(devices),
        emergency_contact:
          values.contact_name.trim() || values.contact_phone.trim()
            ? {
                name: values.contact_name.trim(),
                phone: values.contact_phone.trim(),
              }
            : undefined,
        created_at: new Date().toISOString(),
      };
      await adapter.saveProfile(profile);
      navigate('/');
    } finally {
      setSaving(false);
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

      <main className="mx-auto w-full max-w-md flex-1 px-5 pb-12 pt-6">
        <h1 className="text-2xl font-semibold text-zinc-50">
          A little about you (optional)
        </h1>
        <p className="mt-2 text-base leading-relaxed text-zinc-300">
          This helps us send the right team faster. You can skip any field, and
          you can skip the whole page.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-6">
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-zinc-300"
            >
              Name
            </label>
            <input
              id="name"
              autoComplete="name"
              {...register('name')}
              className="mt-1 block w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-lg text-zinc-50 placeholder-zinc-500"
              placeholder="First name is fine"
            />
          </div>

          <div>
            <label
              htmlFor="age"
              className="block text-sm font-medium text-zinc-300"
            >
              Age
            </label>
            <input
              id="age"
              type="number"
              inputMode="numeric"
              min={0}
              max={120}
              {...register('age')}
              className="mt-1 block w-32 rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-lg text-zinc-50"
              placeholder="e.g. 67"
            />
          </div>

          <fieldset>
            <legend className="text-sm font-medium text-zinc-300">
              Conditions
            </legend>
            <p className="mt-1 text-xs text-zinc-500">
              Pick any that apply. They help responders prepare.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {CONDITIONS.map((c) => (
                <Chip
                  key={c}
                  active={conditions.has(c)}
                  onToggle={() => setConditions((s) => toggle(s, c))}
                >
                  {CONDITION_LABEL[c]}
                </Chip>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-medium text-zinc-300">
              Devices &amp; supplies you have
            </legend>
            <div className="mt-3 flex flex-wrap gap-2">
              {DEVICE_FLAGS.map((d) => (
                <Chip
                  key={d}
                  active={devices.has(d)}
                  onToggle={() => setDevices((s) => toggle(s, d))}
                >
                  {DEVICE_LABEL[d]}
                </Chip>
              ))}
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-zinc-300">
              Emergency contact
            </legend>
            <input
              {...register('contact_name')}
              autoComplete="name"
              className="block w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-lg text-zinc-50 placeholder-zinc-500"
              placeholder="Contact name"
              aria-label="Emergency contact name"
            />
            <input
              {...register('contact_phone')}
              autoComplete="tel"
              type="tel"
              className="block w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-lg text-zinc-50 placeholder-zinc-500"
              placeholder="Contact phone"
              aria-label="Emergency contact phone"
            />
          </fieldset>

          <div className="flex flex-col gap-3 pt-2 sm:flex-row">
            <button
              type="submit"
              disabled={saving}
              className="inline-flex min-h-[56px] flex-1 items-center justify-center gap-2 rounded-2xl bg-rose-600 px-5 py-3 text-lg font-semibold text-white hover:bg-rose-500 disabled:opacity-60"
            >
              <Save className="h-5 w-5" aria-hidden />
              {saving ? 'Saving…' : 'Save info'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="inline-flex min-h-[56px] flex-1 items-center justify-center gap-2 rounded-2xl border border-zinc-700 bg-zinc-900 px-5 py-3 text-lg font-semibold text-zinc-100 hover:bg-zinc-800"
            >
              <SkipForward className="h-5 w-5" aria-hidden />
              Skip for now
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
