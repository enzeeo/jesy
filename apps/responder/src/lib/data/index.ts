import { createApiAdapter } from './apiAdapter';
import { createFixtureAdapter } from './fixtureAdapter';
import type { DataAdapter } from './types';

let cached: DataAdapter | null = null;

export function getDataAdapter(): DataAdapter {
  if (cached) return cached;
  const mode = (import.meta.env.VITE_DATA_MODE ?? 'fixture') as
    | 'fixture'
    | 'api';
  cached = mode === 'api' ? createApiAdapter() : createFixtureAdapter();
  return cached;
}

export type { AdapterEvent, AdapterHandler, DataAdapter } from './types';
