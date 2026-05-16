import type { Profile, VictimStatusView } from '@disaster/types';

import type { IncidentSubmitBody } from '../types';
import type { VictimDataAdapter, VictimDataMode } from './types';

const NOT_IMPLEMENTED = 'api adapter not implemented yet';

/**
 * Placeholder live adapter. We deliberately throw for every method so that
 * accidentally enabling `VITE_DATA_MODE=api` before the API is ready surfaces
 * loudly instead of failing silently.
 */
export class VictimApiAdapter implements VictimDataAdapter {
  readonly mode: VictimDataMode = 'live';

  async saveProfile(_profile: Profile): Promise<void> {
    throw new Error(NOT_IMPLEMENTED);
  }

  async loadProfile(_deviceId: string): Promise<Profile | null> {
    throw new Error(NOT_IMPLEMENTED);
  }

  async submitIncident(
    _body: IncidentSubmitBody,
  ): Promise<{ incident_id: string }> {
    throw new Error(NOT_IMPLEMENTED);
  }

  subscribeStatus(
    _incidentId: string,
    _onUpdate: (s: VictimStatusView) => void,
  ): () => void {
    throw new Error(NOT_IMPLEMENTED);
  }

  cycleDemoStatuses(_incidentId: string): void {
    throw new Error(NOT_IMPLEMENTED);
  }
}

export function createApiAdapter(): VictimDataAdapter {
  return new VictimApiAdapter();
}
