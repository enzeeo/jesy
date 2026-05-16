// =============================================================
// Scenario player — drives the fixture adapter from the timeline.
// Pure data + tiny scheduler. No React.
// =============================================================

import type { FixtureTimelineEvent } from '@disaster/types';
import { FIXTURE_TIMELINE } from './preview.js';

export type PlayerSpeed = 1 | 2 | 4;
export type PlayerStatus = 'idle' | 'running' | 'paused' | 'complete';

export interface PlayerOptions {
  /** Called once per event when its scheduled time passes. */
  onEvent: (event: FixtureTimelineEvent) => void;
  /** Called every tick with elapsed seconds (scenario-time). */
  onTick?: (elapsedSec: number) => void;
  /** Called when the player reaches the end of the timeline. */
  onComplete?: () => void;
  /** Optional override of the timeline. Defaults to FIXTURE_TIMELINE. */
  timeline?: FixtureTimelineEvent[];
  /** Tick interval in real-world ms. Defaults to 250ms. */
  tickMs?: number;
}

export interface ScenarioPlayer {
  status: () => PlayerStatus;
  elapsed: () => number;
  speed: () => PlayerSpeed;
  start: (speed?: PlayerSpeed) => void;
  pause: () => void;
  resume: () => void;
  reset: () => void;
  setSpeed: (s: PlayerSpeed) => void;
  /** Advance one event without playing real time. */
  step: () => FixtureTimelineEvent | null;
}

export function createScenarioPlayer(opts: PlayerOptions): ScenarioPlayer {
  const tickMs = opts.tickMs ?? 250;
  const timeline = [...(opts.timeline ?? FIXTURE_TIMELINE)].sort(
    (a, b) => a.at_sec - b.at_sec,
  );

  let status: PlayerStatus = 'idle';
  let elapsedSec = 0;
  let speed: PlayerSpeed = 1;
  let cursor = 0; // next timeline index
  let intervalId: ReturnType<typeof setInterval> | null = null;

  const stopInterval = () => {
    if (intervalId !== null) {
      clearInterval(intervalId);
      intervalId = null;
    }
  };

  const dispatchDueEvents = () => {
    while (cursor < timeline.length && timeline[cursor]!.at_sec <= elapsedSec) {
      opts.onEvent(timeline[cursor]!);
      cursor += 1;
    }
    if (cursor >= timeline.length && status === 'running') {
      status = 'complete';
      stopInterval();
      opts.onComplete?.();
    }
  };

  const tick = () => {
    elapsedSec += (tickMs / 1000) * speed;
    opts.onTick?.(elapsedSec);
    dispatchDueEvents();
  };

  return {
    status: () => status,
    elapsed: () => elapsedSec,
    speed: () => speed,
    start(s?: PlayerSpeed) {
      if (s) speed = s;
      if (status === 'running') return;
      status = 'running';
      stopInterval();
      intervalId = setInterval(tick, tickMs);
    },
    pause() {
      if (status !== 'running') return;
      status = 'paused';
      stopInterval();
    },
    resume() {
      if (status !== 'paused') return;
      status = 'running';
      stopInterval();
      intervalId = setInterval(tick, tickMs);
    },
    reset() {
      stopInterval();
      status = 'idle';
      elapsedSec = 0;
      cursor = 0;
    },
    setSpeed(s: PlayerSpeed) {
      speed = s;
    },
    step() {
      if (cursor >= timeline.length) return null;
      const evt = timeline[cursor]!;
      elapsedSec = evt.at_sec;
      cursor += 1;
      opts.onEvent(evt);
      opts.onTick?.(elapsedSec);
      if (cursor >= timeline.length) {
        status = 'complete';
        opts.onComplete?.();
      }
      return evt;
    },
  };
}
