"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CallerShell } from "@/components/CallerShell";
import { Chip } from "@/components/Chip";
import type { CallerProfile, DeviceFlag } from "@/lib/types";
import { DEVICE_FLAGS } from "@/lib/types";

const PROFILE_KEY = "disaster.caller.profile";

const CONDITIONS = [
  "diabetes",
  "asthma",
  "copd",
  "heart_condition",
  "mobility_limited",
  "nursing_mother",
  "pregnant",
  "elderly",
];

const CONDITION_LABEL: Record<string, string> = {
  diabetes: "Diabetes",
  asthma: "Asthma",
  copd: "COPD",
  heart_condition: "Heart condition",
  mobility_limited: "Mobility limited",
  nursing_mother: "Nursing mother",
  pregnant: "Pregnant",
  elderly: "Elderly",
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

function toggleSet<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function readProfile(): CallerProfile {
  if (typeof window === "undefined") {
    return { name: "", age: null, conditions: [], devices_owned: [] };
  }
  const savedProfile = window.localStorage.getItem(PROFILE_KEY);
  if (!savedProfile) {
    return { name: "", age: null, conditions: [], devices_owned: [] };
  }
  try {
    return JSON.parse(savedProfile) as CallerProfile;
  } catch {
    window.localStorage.removeItem(PROFILE_KEY);
    return { name: "", age: null, conditions: [], devices_owned: [] };
  }
}

export default function OnboardPage() {
  const router = useRouter();
  const [initialProfile] = useState<CallerProfile>(() => readProfile());
  const [name, setName] = useState(initialProfile.name);
  const [age, setAge] = useState(initialProfile.age == null ? "" : String(initialProfile.age));
  const [contactName, setContactName] = useState(initialProfile.emergency_contact?.name ?? "");
  const [contactPhone, setContactPhone] = useState(initialProfile.emergency_contact?.phone ?? "");
  const [conditions, setConditions] = useState<Set<string>>(new Set(initialProfile.conditions));
  const [devices, setDevices] = useState<Set<DeviceFlag>>(new Set(initialProfile.devices_owned));

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const profile: CallerProfile = {
      name: name.trim(),
      age: age ? Number.parseInt(age, 10) : null,
      conditions: Array.from(conditions),
      devices_owned: Array.from(devices),
      emergency_contact:
        contactName.trim() || contactPhone.trim()
          ? { name: contactName.trim(), phone: contactPhone.trim() }
          : undefined,
    };
    window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    router.push("/");
  }

  return (
    <CallerShell backHref="/" backLabel="Home">
      <h1 className="text-3xl font-semibold tracking-tight text-fg-primary">A little about you</h1>
      <p className="mt-3 text-base leading-7 text-fg-secondary">Optional. This stays on this device for now.</p>

      <form onSubmit={onSubmit} className="mt-7 grid gap-6">
        <label className="grid gap-2">
          <span className="text-sm font-semibold text-fg-secondary">Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} className="border border-border-strong bg-bg-panel px-4 py-3 text-lg text-fg-primary" placeholder="First name is fine" />
        </label>

        <label className="grid max-w-36 gap-2">
          <span className="text-sm font-semibold text-fg-secondary">Age</span>
          <input value={age} onChange={(event) => setAge(event.target.value)} type="number" min={0} max={120} className="border border-border-strong bg-bg-panel px-4 py-3 text-lg text-fg-primary" />
        </label>

        <fieldset>
          <legend className="text-sm font-semibold text-fg-secondary">Conditions</legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {CONDITIONS.map((condition) => (
              <Chip key={condition} active={conditions.has(condition)} onToggle={() => setConditions((current) => toggleSet(current, condition))}>
                {CONDITION_LABEL[condition]}
              </Chip>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-sm font-semibold text-fg-secondary">Devices and supplies you have</legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {DEVICE_FLAGS.map((device) => (
              <Chip key={device} active={devices.has(device)} onToggle={() => setDevices((current) => toggleSet(current, device))}>
                {DEVICE_LABEL[device]}
              </Chip>
            ))}
          </div>
        </fieldset>

        <fieldset className="grid gap-3">
          <legend className="text-sm font-semibold text-fg-secondary">Emergency contact</legend>
          <input value={contactName} onChange={(event) => setContactName(event.target.value)} className="border border-border-strong bg-bg-panel px-4 py-3 text-lg text-fg-primary" placeholder="Contact name" />
          <input value={contactPhone} onChange={(event) => setContactPhone(event.target.value)} type="tel" className="border border-border-strong bg-bg-panel px-4 py-3 text-lg text-fg-primary" placeholder="Contact phone" />
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <button type="submit" className="min-h-14 bg-sev-immediate px-5 py-3 text-lg font-semibold text-white">Save info</button>
          <button type="button" onClick={() => router.push("/")} className="min-h-14 border border-border-strong bg-bg-panel px-5 py-3 text-lg font-semibold text-fg-primary hover:bg-bg-elev">Skip for now</button>
        </div>
      </form>
    </CallerShell>
  );
}
