import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';

export function createApp() {
  const app = new Hono();

  app.use('*', logger());
  app.use(
    '*',
    cors({
      origin: (process.env.CORS_ORIGINS ?? 'http://localhost:5173,http://localhost:5174')
        .split(',')
        .map((s: string) => s.trim()),
    }),
  );

  app.get('/health', (c) =>
    c.json({
      ok: true,
      service: 'disaster-api',
      mode: 'stub',
      ts: new Date().toISOString(),
    }),
  );

  return app;
}

export const app = createApp();
