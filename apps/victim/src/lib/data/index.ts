import { createApiAdapter } from './apiAdapter';
import { createFixtureAdapter } from './fixtureAdapter';
import type { VictimDataAdapter } from './types';

let cached: VictimDataAdapter | null = null;

/**
 * Singleton accessor for the active adapter. Selection is gated by
 * `VITE_DATA_MODE`, defaulting to `fixture` until the live API is ready.
 */
export function getVictimAdapter(): VictimDataAdapter {
  if (cached) return cached;
  const mode = import.meta.env.VITE_DATA_MODE ?? 'fixture';
  cached = mode === 'api' ? createApiAdapter() : createFixtureAdapter();
  return cached;
}

export function getVictimMode(): 'fixture' | 'api' {
  return import.meta.env.VITE_DATA_MODE === 'api' ? 'api' : 'fixture';
}

export type { VictimDataAdapter } from './types';
