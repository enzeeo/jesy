import type {
  DashboardState,
  ScenarioState,
  SSEEvent,
  UnmetResourceNeed,
} from '@disaster/types';

/**
 * Events emitted to subscribers. Mostly mirrors `SSEEvent`, with two
 * scenario-control variants (`tick`, `scenario_status`) and one
 * fixture-supplemental variant (`unmet_update`) used by the fixture
 * adapter to surface partial-assignment unmet needs without re-shaping
 * the SSE contract.
 */
export type AdapterEvent =
  | SSEEvent
  | { type: 'tick'; elapsedSec: number }
  | { type: 'scenario_status'; status: ScenarioState['status'] }
  | { type: 'unmet_update'; data: UnmetResourceNeed[] };

export type AdapterHandler = (event: AdapterEvent) => void;

export type AdapterMode = 'fixture' | 'live';

export interface DataAdapter {
  readonly mode: AdapterMode;
  loadInitialState(): Promise<DashboardState>;
  subscribe(handler: AdapterHandler): () => void;
  startScenario(speed?: 1 | 2 | 4): void;
  pauseScenario(): void;
  resumeScenario(): void;
  resetScenario(): void;
  setSpeed(s: 1 | 2 | 4): void;
  stepScenario(): void;
  injectCritical(): void;
  markResolved(incidentId: string): void;
  recomputeRoutes(): void;
}
