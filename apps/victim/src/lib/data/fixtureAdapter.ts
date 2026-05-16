import type { Profile, VictimStatusView } from '@disaster/types';
import { FIXTURE_VICTIM_STATUSES } from '@disaster/fixtures';
import * as idb from 'idb-keyval';

import type { IncidentSubmitBody } from '../types';
import type { VictimDataAdapter, VictimDataMode } from './types';

const PROFILE_STORE_PREFIX = 'victim.profile.';

interface IncidentRecord {
  id: string;
  body: IncidentSubmitBody;
  /** Snapshot we keep so the demo cycle can include `low_confidence_location`. */
  usedPlaceDescription: boolean;
}

/**
 * Pick the fixture status template that best fits this incident, then patch in
 * the live incident_id so the UI reads "this is YOUR status", not "inc-001".
 */
function pickInitialStatus(incident: IncidentRecord): VictimStatusView {
  const tpl = FIXTURE_VICTIM_STATUSES['received'];
  if (!tpl) {
    return {
      incident_id: incident.id,
      state: 'received',
      message: 'Help received. We are reading your message.',
    };
  }
  return { ...tpl, incident_id: incident.id };
}

function patchedStatus(
  incident: IncidentRecord,
  state: VictimStatusView['state'],
): VictimStatusView | null {
  const tpl = FIXTURE_VICTIM_STATUSES[state];
  if (!tpl) return null;
  return { ...tpl, incident_id: incident.id };
}

/**
 * Build the canonical demo cycle for this incident:
 *   received → triaging → assigned [→ low_confidence_location?] [→ unmet_resource]
 *
 * `low_confidence_location` is only inserted when the submission came from a
 * place description (so we don't fake it for GPS-clean submissions).
 *
 * `unmet_resource` is always shown last so reviewers can see the calm copy
 * we use for partial-assignment cases.
 */
function buildCycle(incident: IncidentRecord): VictimStatusView['state'][] {
  const cycle: VictimStatusView['state'][] = ['received', 'triaging', 'assigned'];
  if (incident.usedPlaceDescription) cycle.push('low_confidence_location');
  cycle.push('unmet_resource');
  return cycle;
}

export class VictimFixtureAdapter implements VictimDataAdapter {
  readonly mode: VictimDataMode = 'fixture';

  /** In-memory registry so subscribeStatus / cycleDemoStatuses can find the incident. */
  private readonly incidents = new Map<string, IncidentRecord>();

  /** Active per-incident subscribers so a demo cycle pushes through to the UI. */
  private readonly subscribers = new Map<
    string,
    Set<(s: VictimStatusView) => void>
  >();

  /** Latest snapshot per incident — replayed to new subscribers immediately. */
  private readonly latest = new Map<string, VictimStatusView>();

  /** Pending demo timeouts so we can clear them if cycle is restarted. */
  private readonly demoTimers = new Map<string, ReturnType<typeof setTimeout>[]>();

  async saveProfile(profile: Profile): Promise<void> {
    await idb.set(PROFILE_STORE_PREFIX + profile.device_id, profile);
  }

  async loadProfile(deviceId: string): Promise<Profile | null> {
    const value = await idb.get<Profile | undefined>(PROFILE_STORE_PREFIX + deviceId);
    return value ?? null;
  }

  async submitIncident(
    body: IncidentSubmitBody,
  ): Promise<{ incident_id: string }> {
    const id = `inc-demo-${Math.random().toString(36).slice(2, 8)}`;
    const record: IncidentRecord = {
      id,
      body,
      usedPlaceDescription: body.location.source === 'place_description_udf',
    };
    this.incidents.set(id, record);
    // Seed the initial received snapshot so any subscriber gets it immediately.
    this.latest.set(id, pickInitialStatus(record));
    return { incident_id: id };
  }

  subscribeStatus(
    incidentId: string,
    onUpdate: (s: VictimStatusView) => void,
  ): () => void {
    let set = this.subscribers.get(incidentId);
    if (!set) {
      set = new Set();
      this.subscribers.set(incidentId, set);
    }
    set.add(onUpdate);

    // Replay the latest snapshot, or synthesize a "received" one for fixture
    // incidents the user lands on directly (e.g. /status/inc-001).
    const snap = this.latest.get(incidentId) ?? this.synthesizeStandalone(incidentId);
    if (snap) {
      this.latest.set(incidentId, snap);
      // Defer to next tick so unrelated subscribe-during-render warnings don't fire.
      queueMicrotask(() => onUpdate(snap));
    }

    return () => {
      set?.delete(onUpdate);
    };
  }

  cycleDemoStatuses(incidentId: string): void {
    let record = this.incidents.get(incidentId);
    // Allow the demo page to drive a hard-coded fixture incident id (e.g. inc-001)
    // even though we never called submitIncident for it.
    if (!record) {
      record = {
        id: incidentId,
        body: {
          // Minimal stub — only fields used elsewhere.
          device_id: 'dev-fixture',
          location: { source: 'gps', lat: 0, lng: 0 },
          raw_text: '',
          needs: {},
          inventory_have: [],
          inventory_need: [],
          timestamp: new Date().toISOString(),
        },
        usedPlaceDescription:
          incidentId === FIXTURE_VICTIM_STATUSES['low_confidence_location']?.incident_id,
      };
      this.incidents.set(incidentId, record);
    }

    // Cancel any prior cycle for this incident so multiple presses don't pile up.
    for (const t of this.demoTimers.get(incidentId) ?? []) clearTimeout(t);
    const timers: ReturnType<typeof setTimeout>[] = [];
    this.demoTimers.set(incidentId, timers);

    const cycle = buildCycle(record);
    // Comfortable pace — 2.5s between beats so reviewers can read each line.
    const stepMs = 2500;
    cycle.forEach((state, i) => {
      timers.push(
        setTimeout(() => {
          const snap = patchedStatus(record!, state);
          if (snap) this.publish(incidentId, snap);
        }, i * stepMs),
      );
    });
  }

  /**
   * Build a standalone snapshot when the UI subscribes to an incident id we
   * never created via submitIncident — e.g. landing directly on
   * /status/inc-001 from the /demo page. We use the canonical "assigned"
   * fixture for inc-001, etc, so the page has something rich to render.
   */
  private synthesizeStandalone(incidentId: string): VictimStatusView | null {
    const tpls = Object.values(FIXTURE_VICTIM_STATUSES) as VictimStatusView[];
    for (const tpl of tpls) {
      if (tpl.incident_id === incidentId) {
        return { ...tpl };
      }
    }
    return null;
  }

  private publish(incidentId: string, snap: VictimStatusView): void {
    this.latest.set(incidentId, snap);
    const set = this.subscribers.get(incidentId);
    if (!set) return;
    for (const fn of set) fn(snap);
  }
}

export function createFixtureAdapter(): VictimDataAdapter {
  return new VictimFixtureAdapter();
}
