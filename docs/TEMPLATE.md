# Template Notes

This file records the current `main` template shape. It intentionally excludes
branch-only scaffolds that are not present on `main`.

## Current Layout

```text
src/disaster/        FastAPI backend package
frontend/            Next.js dashboard
scripts/             Snowflake setup and smoke scripts
tests/               Backend tests
docs/                Project docs
```

## Current Bootstrap

```bash
uv sync
cd frontend && npm install
```

## Current Run Commands

```bash
make dev
cd frontend && npm run dev
```

## Future Features

The following template ideas are not in `main`:

- `apps/victim`
- `apps/responder`
- `services/api`
- `packages/types`
- `packages/fixtures`
- `scenarios`
- `snowflake`
- `pnpm-workspace.yaml`
