import { describe, expect, it } from 'vitest';

import { createApp } from './app';

describe('health', () => {
  it('returns ok json', async () => {
    const app = createApp();
    const res = await app.request('http://localhost/health');
    expect(res.status).toBe(200);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body.ok).toBe(true);
    expect(body.service).toBe('disaster-api');
  });
});
