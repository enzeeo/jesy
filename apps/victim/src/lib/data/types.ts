import type { Profile, VictimStatusView } from '@disaster/types';

import type { IncidentSubmitBody } from '../types';

export type VictimDataMode = 'fixture' | 'live';

export interface VictimDataAdapter {
  readonly mode: VictimDataMode;

  /** Persist the victim profile (idempotent by device_id). */
  saveProfile(profile: Profile): Promise<void>;

  /** Load the most recently saved profile for this device, if any. */
  loadProfile(deviceId: string): Promise<Profile | null>;

  /** Submit an incident; returns the incident id assigned by the system. */
  submitIncident(body: IncidentSubmitBody): Promise<{ incident_id: string }>;

  /**
   * Subscribe to status updates for an incident. The callback is invoked
   * synchronously with an initial snapshot if one is available, then again
   * on each subsequent state change.
   *
   * Returns an unsubscribe function.
   */
  subscribeStatus(
    incidentId: string,
    onUpdate: (status: VictimStatusView) => void,
  ): () => void;

  /**
   * Demo-only: walk through the canonical sequence of status states for the
   * given incident at a comfortable pace, so reviewers can see all five
   * VictimStatusView states without driving them by hand.
   *
   * `received → triaging → assigned`, plus `low_confidence_location` when the
   * submission used a place description, and `unmet_resource` to surface the
   * partial-assignment state for the demo bonus.
   */
  cycleDemoStatuses(incidentId: string): void;
}
