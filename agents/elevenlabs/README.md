# ElevenLabs Agents — `agents/elevenlabs/`

Source of truth for the Conversational AI agent powering caller-ui's voice
intake flow. Managed via the [`@elevenlabs/cli`](https://elevenlabs.io/docs/eleven-agents/operate/cli).

## Layout

```
.
├── agents.json                            ← registry, references config files
├── agent_configs/
│   └── emergency-intake.json              ← agent: voice, prompt, first_message, tool_ids
├── tools.json                             ← registry, references tool configs
├── tool_configs/
│   ├── create_incident_provisional.json   ← agent's first call after location known
│   ├── update_assessment.json             ← patches victim fields, re-runs triage
│   ├── query_nearby_resources.json        ← STUBBED on the backend — returns canned units
│   └── finalize.json                      ← end-of-call: full transcript → backend extract
├── tests.json                             ← (unused — placeholder from `agents init`)
├── test_configs/                          ← (unused)
└── .env.example
```

The four tool URLs all point to backend endpoints under `/intake/voice/`.
The backend HMAC-verifies them via `ELEVENLABS_WEBHOOK_SECRET` (set in repo-root
`.env`, see `.env.example`).

## Sync to ElevenLabs cloud

```bash
# 1. One-time: authenticate the CLI (stores key under ~/.agents/)
elevenlabs auth login

# 2. Stand up the backend on a public HTTPS URL
ngrok http 8000
# → copy the https URL, e.g. https://abc123.ngrok.app

# 3. Push: one command does substitution + tools push + tool_ids injection + agent push
make agents-push BACKEND_URL=https://abc123.ngrok.app
```

The script (`scripts/elevenlabs_sync.py`) handles the full cycle:

1. Substitutes `BACKEND_URL` into every `tool_configs/*.json` (idempotent —
   re-runs replace the previous ngrok URL with the new one)
2. `elevenlabs tools push` — creates/updates tools, IDs written into `tools.json`
3. Reads the four assigned IDs, writes them into
   `agent_configs/emergency-intake.json` →
   `conversation_config.agent.prompt.tool_ids`
4. `elevenlabs agents push` — agent now bound to the tools
5. Prints the agent id with copy-paste instructions for
   `caller-ui/.env.local`

After it completes, paste the printed `NEXT_PUBLIC_ELEVENLABS_AGENT_ID=...`
into `caller-ui/.env.local` and you're done.

## Iterating

| Change | Command |
|---|---|
| Prompt / first_message / voice change | edit `agent_configs/*.json` → `make agents-push-agent-only BACKEND_URL=...` |
| Tool schema or URL change | edit `tool_configs/*.json` → `make agents-push BACKEND_URL=...` |
| Dashboard hand-edit (drift) | `make agents-pull` |
| See what would change | `make agents-dry-run BACKEND_URL=...` |

## Webhook auth

The backend's HMAC middleware verifies `x-elevenlabs-signature` on every
request to `/intake/voice/*`. The signing secret comes from the
`ELEVENLABS_WEBHOOK_SECRET` env var. In ElevenLabs's dashboard, set the
matching secret under the agent's webhook settings — they must be byte-for-byte
identical or every tool call returns 401.

If `ELEVENLABS_WEBHOOK_SECRET` is unset on the backend, requests pass with a
dev-mode warning. Set it before any public-URL demo.

## Stub note

`query_nearby_resources` hits a backend handler that returns canned units and
ETAs (`src/disaster/app/routes/intake_tools.py`). Hackathon scope. Swap the
`_STUB_NEARBY_UNITS` constant for `snowflake/tiles.py` + `responders.list()`
when ready.
