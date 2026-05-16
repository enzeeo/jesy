import type { DashboardState, ScenarioState } from '@disaster/types';

import type { AdapterEvent, AdapterHandler, DataAdapter } from './types';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ??
  'http://localhost:8787';

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`api ${response.status}: ${path}`);
  }
  return (await response.json()) as T;
}

function getAdminHeaders(): HeadersInit {
  let token = '';
  try {
    token = localStorage.getItem('admin-token') ?? '';
  } catch {
    token = '';
  }
  return token ? { authorization: `Bearer ${token}` } : {};
}

function parseStreamMessage(message: MessageEvent<string>): AdapterEvent | null {
  try {
    return JSON.parse(message.data) as AdapterEvent;
  } catch {
    return null;
  }
}

function postAdmin(path: string, body?: unknown): void {
  void fetchJson(path, {
    method: 'POST',
    headers: getAdminHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => {
    // The dashboard should stay usable if admin endpoints are unavailable.
  });
}

export function createApiAdapter(): DataAdapter {
  let stream: EventSource | null = null;

  return {
    mode: 'live',

    async loadInitialState(): Promise<DashboardState> {
      return fetchJson<DashboardState>('/v1/dashboard/state');
    },

    subscribe(_handler: AdapterHandler) {
      const handler = _handler;
      stream = new EventSource(`${API_BASE_URL}/v1/stream`);
      stream.onmessage = (message) => {
        const event = parseStreamMessage(message);
        if (event) handler(event);
      };
      stream.addEventListener('scenario_status', (message) => {
        const data = JSON.parse((message as MessageEvent<string>).data) as {
          status: ScenarioState['status'];
        };
        handler({ type: 'scenario_status', status: data.status });
      });
      return () => {
        stream?.close();
        stream = null;
      };
    },

    startScenario() {
      postAdmin('/v1/admin/scenario/start');
    },

    pauseScenario() {
      postAdmin('/v1/admin/scenario/pause');
    },

    resumeScenario() {
      postAdmin('/v1/admin/scenario/resume');
    },

    resetScenario() {
      postAdmin('/v1/admin/scenario/reset');
    },

    setSpeed() {
      // Live scenario timing belongs to the API; fixture-only speed control.
    },

    stepScenario() {
      postAdmin('/v1/admin/scenario/step');
    },

    injectCritical() {
      postAdmin('/v1/admin/scenario/inject-critical');
    },

    markResolved() {
      // Live resolution endpoint is intentionally separate from preview scope.
    },

    recomputeRoutes() {
      postAdmin('/v1/admin/routes/recompute');
    },
  };
}
