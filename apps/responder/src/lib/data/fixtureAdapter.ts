import type {
  Assignment,
  DashboardState,
  FixtureTimelineEvent,
  IncidentEnriched,
  Responder,
  ResourceRoster,
  ResourceType,
  RoutePreview,
  SSEEvent,
  UnmetResourceNeed,
} from '@disaster/types';
import {
  FIXTURE_ASSIGNMENTS,
  FIXTURE_INCIDENTS,
  FIXTURE_INITIAL_DASHBOARD,
  FIXTURE_RESPONDERS,
  FIXTURE_ROUTES,
  FIXTURE_UNMET,
  INJECT_CRITICAL_INCIDENT,
} from '@disaster/fixtures';
import { createScenarioPlayer } from '@disaster/fixtures/scenario';
import type { ScenarioPlayer } from '@disaster/fixtures/scenario';

import type { AdapterEvent, AdapterHandler, DataAdapter } from './types';

function cloneInitial(): DashboardState {
  // Deep clone via structuredClone to avoid mutation across reloads.
  // The fixture object is plain JSON-safe, so this is safe.
  return structuredClone({
    ...FIXTURE_INITIAL_DASHBOARD,
    mode: 'fixture' as const,
  });
}

function timelineEventToSSE(event: FixtureTimelineEvent): SSEEvent | null {
  switch (event.type) {
    case 'incident_new':
      return { type: 'incident_new', data: event.payload as IncidentEnriched };
    case 'incident_update':
      return {
        type: 'incident_update',
        data: event.payload as IncidentEnriched,
      };
    case 'cluster_update':
      return {
        type: 'cluster_update',
        data: event.payload as import('@disaster/types').ClusterView,
      };
    case 'assignment_new':
      return { type: 'assignment_new', data: event.payload as Assignment };
    case 'route_update':
      return { type: 'route_update', data: event.payload as RoutePreview };
    case 'resource_update':
      return {
        type: 'resource_update',
        data: event.payload as ResourceRoster[],
      };
    case 'victim_status_update':
      // Not relevant to responder dashboard; ignore.
      return null;
    default:
      return null;
  }
}

const UNMET_EMIT_AT_SEC = 31;

function makeInjectAssignments(): Assignment[] {
  // Move some "available" responders to the inject incident so users see
  // assignments + the route polyline recompute happen visibly.
  const incidentId = INJECT_CRITICAL_INCIDENT.incident_id;
  const requiredTypes: ResourceType[] = ['fire', 'paramedic', 'ems', 'doctor'];
  const out: Assignment[] = [];
  for (const type of requiredTypes) {
    const free = FIXTURE_RESPONDERS.find(
      (r: Responder) => r.type === type && r.status === 'available',
    );
    if (!free) continue;
    out.push({
      assignment_id: `a-inject-${type}`,
      incident_id: incidentId,
      responder_id: free.responder_id,
      resource_type: type,
      eta_sec: 480,
      status: 'enroute',
      assigned_at: new Date().toISOString(),
    });
  }
  return out;
}

function makeInjectRoute(): RoutePreview {
  const incidentId = INJECT_CRITICAL_INCIDENT.incident_id;
  return {
    responder_id: 'r-fire-04',
    assignment_ids: ['a-inject-fire'],
    stops: [{ incident_id: incidentId, eta_sec: 480, order: 1 }],
    total_eta_sec: 480,
    route_source: 'fallback',
  };
}

export function createFixtureAdapter(): DataAdapter {
  const handlers = new Set<AdapterHandler>();
  let unmetEmitted = false;

  const emit = (event: AdapterEvent) => {
    for (const h of handlers) h(event);
  };

  let player: ScenarioPlayer | null = null;

  const ensurePlayer = (): ScenarioPlayer => {
    if (player) return player;
    player = createScenarioPlayer({
      onEvent: (evt: FixtureTimelineEvent) => {
        const sse = timelineEventToSSE(evt);
        if (sse) emit(sse);
      },
      onTick: (elapsedSec: number) => {
        emit({ type: 'tick', elapsedSec });
        if (!unmetEmitted && elapsedSec >= UNMET_EMIT_AT_SEC) {
          unmetEmitted = true;
          emit({ type: 'unmet_update', data: FIXTURE_UNMET });
        }
      },
      onComplete: () => {
        emit({ type: 'scenario_status', status: 'complete' });
      },
    });
    return player;
  };

  return {
    mode: 'fixture',

    async loadInitialState(): Promise<DashboardState> {
      return cloneInitial();
    },

    subscribe(handler: AdapterHandler) {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
      };
    },

    startScenario(speed?: 1 | 2 | 4) {
      const p = ensurePlayer();
      p.start(speed ?? 1);
      emit({ type: 'scenario_status', status: 'running' });
    },

    pauseScenario() {
      const p = ensurePlayer();
      p.pause();
      emit({ type: 'scenario_status', status: 'paused' });
    },

    resumeScenario() {
      const p = ensurePlayer();
      if (p.status() === 'paused') {
        p.resume();
        emit({ type: 'scenario_status', status: 'running' });
      } else {
        p.start();
        emit({ type: 'scenario_status', status: 'running' });
      }
    },

    resetScenario() {
      if (player) player.reset();
      player = null;
      unmetEmitted = false;
      emit({ type: 'scenario_status', status: 'idle' });
      emit({ type: 'tick', elapsedSec: 0 });
      emit({ type: 'unmet_update', data: [] });
    },

    setSpeed(s: 1 | 2 | 4) {
      const p = ensurePlayer();
      p.setSpeed(s);
    },

    stepScenario() {
      const p = ensurePlayer();
      p.step();
    },

    injectCritical() {
      const incident = structuredClone(INJECT_CRITICAL_INCIDENT);
      emit({ type: 'incident_new', data: incident });
      const assignments = makeInjectAssignments();
      // Stagger assignments + route slightly so the polyline-recompute
      // animation is visible without overlapping the incident pin entry.
      let delay = 250;
      for (const a of assignments) {
        const local = a;
        setTimeout(() => emit({ type: 'assignment_new', data: local }), delay);
        delay += 220;
      }
      setTimeout(
        () =>
          emit({
            type: 'route_update',
            data: makeInjectRoute(),
          }),
        delay + 200,
      );
    },

    markResolved(incidentId: string) {
      const original = FIXTURE_INCIDENTS.find(
        (i: IncidentEnriched) => i.incident_id === incidentId,
      );
      if (!original) return;
      const updated: IncidentEnriched = {
        ...structuredClone(original),
        status: 'resolved',
      };
      emit({ type: 'incident_update', data: updated });

      // Free any responders assigned to this incident.
      const releasedTypes = new Set<ResourceType>();
      for (const a of FIXTURE_ASSIGNMENTS) {
        if (a.incident_id === incidentId) releasedTypes.add(a.resource_type);
      }
      // Recompute a tweaked roster: increment available for each released
      // type. We start from the fixture roster baseline.
      const baseline = FIXTURE_INITIAL_DASHBOARD.roster;
      const next: ResourceRoster[] = baseline.map((row) => {
        if (!releasedTypes.has(row.type)) return row;
        const released = FIXTURE_ASSIGNMENTS.filter(
          (a) => a.incident_id === incidentId && a.resource_type === row.type,
        ).length;
        return {
          ...row,
          busy: Math.max(0, row.busy - released),
          available: Math.min(row.total, row.available + released),
        };
      });
      emit({ type: 'resource_update', data: next });

      // Drop any unmet needs tied to this incident.
      const newUnmet: UnmetResourceNeed[] = FIXTURE_UNMET.filter(
        (u) => u.incident_id !== incidentId,
      );
      emit({ type: 'unmet_update', data: newUnmet });
    },

    recomputeRoutes() {
      let delay = 120;
      for (const route of FIXTURE_ROUTES) {
        const local = structuredClone(route);
        setTimeout(
          () => emit({ type: 'route_update', data: local }),
          delay,
        );
        delay += 180;
      }
    },
  };
}
