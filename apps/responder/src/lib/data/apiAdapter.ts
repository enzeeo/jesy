import type { DashboardState } from '@disaster/types';

import type { AdapterHandler, DataAdapter } from './types';

const notImplemented = (label: string) => {
  throw new Error(`api adapter not implemented yet: ${label}`);
};

export function createApiAdapter(): DataAdapter {
  return {
    mode: 'live',
    async loadInitialState(): Promise<DashboardState> {
      return notImplemented('loadInitialState');
    },
    subscribe(_handler: AdapterHandler) {
      notImplemented('subscribe');
      return () => {};
    },
    startScenario() {
      notImplemented('startScenario');
    },
    pauseScenario() {
      notImplemented('pauseScenario');
    },
    resumeScenario() {
      notImplemented('resumeScenario');
    },
    resetScenario() {
      notImplemented('resetScenario');
    },
    setSpeed() {
      notImplemented('setSpeed');
    },
    stepScenario() {
      notImplemented('stepScenario');
    },
    injectCritical() {
      notImplemented('injectCritical');
    },
    markResolved() {
      notImplemented('markResolved');
    },
    recomputeRoutes() {
      notImplemented('recomputeRoutes');
    },
  };
}
