import 'dotenv/config';
import { serve } from '@hono/node-server';

import { app } from './app';

const port = Number(process.env.PORT ?? 8787);
serve({ fetch: app.fetch, port });
// eslint-disable-next-line no-console
console.log(`api listening on http://localhost:${port}`);
