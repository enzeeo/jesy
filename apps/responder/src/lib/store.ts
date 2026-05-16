import { create } from 'zustand';

import type {
  Assignment,
  ClusterView,
  DashboardState,
  IncidentCategory,
  IncidentEnriched,
  Responder,
  ResourceRoster,
  ResourceType,
  RoutePreview,
  ScenarioState,
  UnmetResourceNeed,
} from '@disaster/types';
import { RESOURCE_TYPES } from '@disaster/types';

import type { AdapterEvent } from './data';

// ---------------------------------------------------------------
// Types
// ---------------------------------------------------------------

export type StatusFilter = 'all' | 'open' | 'assigned' | 'in_progress' | 'resolved';

export interface Filters {
  minSeverity: number;
  categories: IncidentCategory[]; // empty = all
  status: StatusFilter;
  responderType: ResourceType | 'all';
}

export interface DashboardStore {
  mode: 'fixture' | 'live';
  scenario: ScenarioState;
  incidentsById: Record<string, IncidentEnriched>;
  clustersById: Record<string, ClusterView>;
  assignmentsById: Record<string, Assignment>;
  unmetByIncidentId: Record<string, UnmetResourceNeed[]>;
  routesByResponderId: Record<string, RoutePreview>;
  rosterByType: Partial<Record<ResourceType, ResourceRoster>>;
  respondersById: Record<string, Responder>;
  selectedIncidentId: string | null;
  selectedResponderId: string | null;
  filters: Filters;
  connectionLabel: 'fixture' | 'live';
  lastEventAt: number | null;

  hydrate: (state: DashboardState) => void;
  applyEvent: (event: AdapterEvent) => void;
  selectIncident: (id: string | null) => void;
  selectResponder: (id: string | null) => void;
  setFilters: (patch: Partial<Filters>) => void;
  setScenarioStatus: (status: ScenarioState['status']) => void;
  setElapsed: (sec: number) => void;
  setConnection: (label: 'fixture' | 'live') => void;
}

// ---------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------

const DEFAULT_SCENARIO: ScenarioState = {
  name: 'texas-flood',
  label: 'Houston Flash Flood, May 2026',
  elapsed_sec: 0,
  status: 'idle',
};

const DEFAULT_FILTERS: Filters = {
  minSeverity: 0,
  categories: [],
  status: 'all',
  responderType: 'all',
};

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

function byId<T, K extends keyof T>(rows: T[], key: K): Record<string, T> {
  const out: Record<string, T> = {};
  for (const r of rows) {
    const id = String(r[key]);
    out[id] = r;
  }
  return out;
}

function unmetBy(needs: UnmetResourceNeed[]): Record<string, UnmetResourceNeed[]> {
  const out: Record<string, UnmetResourceNeed[]> = {};
  for (const n of needs) {
    const list = out[n.incident_id] ?? [];
    list.push(n);
    out[n.incident_id] = list;
  }
  return out;
}

function rosterBy(
  rows: ResourceRoster[],
): Partial<Record<ResourceType, ResourceRoster>> {
  const out: Partial<Record<ResourceType, ResourceRoster>> = {};
  for (const r of rows) {
    out[r.type] = r;
  }
  return out;
}

// ---------------------------------------------------------------
// Store
// ---------------------------------------------------------------

export const useDashboardStore = create<DashboardStore>((set) => ({
  mode: 'fixture',
  scenario: DEFAULT_SCENARIO,
  incidentsById: {},
  clustersById: {},
  assignmentsById: {},
  unmetByIncidentId: {},
  routesByResponderId: {},
  rosterByType: {},
  respondersById: {},
  selectedIncidentId: null,
  selectedResponderId: null,
  filters: DEFAULT_FILTERS,
  connectionLabel: 'fixture',
  lastEventAt: null,

  hydrate(state) {
    set({
      mode: state.mode,
      scenario: state.scenario ?? DEFAULT_SCENARIO,
      incidentsById: byId(state.incidents, 'incident_id'),
      clustersById: byId(state.clusters, 'cluster_id'),
      assignmentsById: byId(state.assignments, 'assignment_id'),
      unmetByIncidentId: unmetBy(state.unmet_resource_needs),
      routesByResponderId: byId(state.routes, 'responder_id'),
      rosterByType: rosterBy(state.roster),
      respondersById: byId(state.responders, 'responder_id'),
      connectionLabel: state.mode,
    });
  },

  applyEvent(event) {
    set((s) => {
      const next: Partial<DashboardStore> = { lastEventAt: Date.now() };

      switch (event.type) {
        case 'incident_new':
        case 'incident_update': {
          const inc = event.data;
          next.incidentsById = {
            ...s.incidentsById,
            [inc.incident_id]: { ...s.incidentsById[inc.incident_id], ...inc },
          };
          break;
        }
        case 'cluster_update': {
          const cl = event.data;
          next.clustersById = {
            ...s.clustersById,
            [cl.cluster_id]: { ...s.clustersById[cl.cluster_id], ...cl },
          };
          break;
        }
        case 'assignment_new': {
          const a = event.data;
          next.assignmentsById = {
            ...s.assignmentsById,
            [a.assignment_id]: a,
          };
          // Roll the responder to busy.
          const prev = s.respondersById[a.responder_id];
          if (prev) {
            next.respondersById = {
              ...s.respondersById,
              [a.responder_id]: { ...prev, status: 'busy' },
            };
          }
          // Flip incident to "assigned" if currently open.
          const incident = s.incidentsById[a.incident_id];
          if (incident && incident.status === 'open') {
            next.incidentsById = {
              ...s.incidentsById,
              [a.incident_id]: { ...incident, status: 'assigned' },
            };
          }
          break;
        }
        case 'route_update': {
          const r = event.data;
          next.routesByResponderId = {
            ...s.routesByResponderId,
            [r.responder_id]: r,
          };
          break;
        }
        case 'resource_update': {
          next.rosterByType = rosterBy(event.data);
          break;
        }
        case 'unmet_update': {
          next.unmetByIncidentId = unmetBy(event.data);
          break;
        }
        case 'tick': {
          next.scenario = { ...s.scenario, elapsed_sec: event.elapsedSec };
          break;
        }
        case 'scenario_status': {
          next.scenario = { ...s.scenario, status: event.status };
          break;
        }
        default: {
          const exhaustive: never = event;
          void exhaustive;
        }
      }
      return next;
    });
  },

  selectIncident(id) {
    set({ selectedIncidentId: id });
  },

  selectResponder(id) {
    set({ selectedResponderId: id });
  },

  setFilters(patch) {
    set((s) => ({ filters: { ...s.filters, ...patch } }));
  },

  setScenarioStatus(status) {
    set((s) => ({ scenario: { ...s.scenario, status } }));
  },

  setElapsed(sec) {
    set((s) => ({ scenario: { ...s.scenario, elapsed_sec: sec } }));
  },

  setConnection(label) {
    set({ connectionLabel: label });
  },
}));

// ---------------------------------------------------------------
// Selectors (plain functions over store snapshot)
// ---------------------------------------------------------------

export function selectIncidents(s: DashboardStore): IncidentEnriched[] {
  return Object.values(s.incidentsById);
}

export function selectQueue(s: DashboardStore): IncidentEnriched[] {
  const { minSeverity, categories, status } = s.filters;
  const out = selectIncidents(s).filter((i) => {
    if (i.severity.score < minSeverity) return false;
    if (categories.length > 0 && !categories.includes(i.severity.category))
      return false;
    if (status !== 'all' && i.status !== status) return false;
    return true;
  });
  out.sort((a, b) => b.severity.score - a.severity.score);
  return out;
}

export function selectClusters(s: DashboardStore): ClusterView[] {
  return Object.values(s.clustersById);
}

export function selectRoutes(s: DashboardStore): RoutePreview[] {
  return Object.values(s.routesByResponderId);
}

export function selectRoster(s: DashboardStore): ResourceRoster[] {
  return RESOURCE_TYPES.map(
    (t) =>
      s.rosterByType[t] ?? { type: t, total: 0, available: 0, busy: 0 },
  );
}

export interface DashboardStats {
  open: number;
  resolved: number;
  avgSeverity: number;
  dispatched: number;
  elapsedSec: number;
}

export function selectStats(s: DashboardStore): DashboardStats {
  const incidents = selectIncidents(s);
  let open = 0;
  let resolved = 0;
  let totalSev = 0;
  for (const i of incidents) {
    if (i.status === 'resolved') resolved += 1;
    else open += 1;
    totalSev += i.severity.score;
  }
  const dispatched = Object.values(s.respondersById).filter(
    (r) => r.status === 'busy',
  ).length;
  return {
    open,
    resolved,
    avgSeverity: incidents.length ? Math.round(totalSev / incidents.length) : 0,
    dispatched,
    elapsedSec: s.scenario.elapsed_sec,
  };
}

export function selectAssignmentsForIncident(
  s: DashboardStore,
  incidentId: string,
): Assignment[] {
  return Object.values(s.assignmentsById).filter(
    (a) => a.incident_id === incidentId,
  );
}

export function selectUnmetForIncident(
  s: DashboardStore,
  incidentId: string,
): UnmetResourceNeed[] {
  return s.unmetByIncidentId[incidentId] ?? [];
}

export function selectClusterForIncident(
  s: DashboardStore,
  incidentId: string,
): ClusterView | undefined {
  for (const c of Object.values(s.clustersById)) {
    if (c.incident_ids.includes(incidentId)) return c;
  }
  return undefined;
}
