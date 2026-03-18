---
name: livekit-voice-web
description: >
  Deploy and manage the LiveKit voice agent web app on Fly.io. Use when the user wants to
  deploy the voice agent web interface, set up a public call URL, configure multi-agent
  support, or manage an existing deployment. Triggers on phrases like "deploy voice web app",
  "set up voice web", "voice agent web", "call URL", "fly deploy voice", "web app setup".
---

# LiveKit Voice Web — Fly.io Deployment Skill

Deploys the voice agent web app (React frontend + FastAPI backend) to Fly.io and sets up signed JWT call URLs so any OpenClaw instance can generate a click-to-call link.

## Quick Reference

| Task | Command |
|------|---------|
| First-time deploy | `python3 web-skill/scripts/setup.py` |
| Redeploy (after code changes) | `python3 web-skill/scripts/deploy.py` |
| Generate a call URL | `python3 web-skill/scripts/call_url.py --agent <name> --name "<display>"` |
| Check deployment status | `python3 web-skill/scripts/status.py` |

## What Gets Deployed

A single Fly.io app with:
- **React frontend** — connect-to-call UI with agent state badges (Listening / Thinking / Speaking)
- **FastAPI backend** — `/connect` endpoint: verifies signed JWT, issues LiveKit room token, dispatches agent
- **Signed URL flow** — `CONFIG_SECRET` shared between Pi and Fly signs JWT call URLs; no agent registry needed

## Prerequisites

The setup script will check for these and guide you through anything missing:

1. **Fly.io account** — https://fly.io/app/sign-up (free tier works)
2. **flyctl** — the setup script installs it automatically if absent
3. **LiveKit Cloud project** — https://cloud.livekit.io (free tier works)
4. **LiveKit credentials** — URL, API key, API secret from your LiveKit dashboard
5. **Node.js ≥ 18** — for building the React frontend (checked at setup time)

## Setup (First Time)

```bash
python3 scripts/setup.py
```

The setup script will:
1. Check prerequisites (flyctl, Node.js, LiveKit creds)
2. Install flyctl if missing (Linux/macOS)
3. Prompt for Fly.io login if not authenticated
4. Ask for a Fly app name (default: `voice-agent-web`)
5. Prompt for LiveKit credentials (URL, API key, API secret)
6. Generate a `CONFIG_SECRET` automatically
7. Set all Fly secrets
8. Build and deploy the app
9. Print your app URL and a test call URL

## Generating Call URLs

After setup, generate signed URLs for each agent (run from the repo root):

```bash
python3 web-skill/scripts/call_url.py --agent voice-agent --name "Alex"
python3 web-skill/scripts/call_url.py --agent main --name "Clive"
```

URLs are valid for 24 hours by default. Pass `--ttl 3600` for 1 hour.

## Multi-Agent Setup

Each agent worker needs a unique port and agent ID:

```bash
# Agent 1 (Alex) — uses defaults from .env
python agent.py start

# Agent 2 (Clive) — override agent name, port, and OpenClaw routing
OPENCLAW_AGENT_NAME=main OPENCLAW_AGENT_DISPLAY_NAME=Clive \
OPENCLAW_AGENT_ID=main AGENT_HTTP_PORT=8082 \
AGENT_GREETING="Hey, it's Clive. Go ahead." \
python agent.py start
```

## Environment Variables (agent host .env)

| Variable | Description |
|----------|-------------|
| `LIVEKIT_URL` | LiveKit WebSocket URL (`wss://...`) |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `CONFIG_SECRET` | Shared JWT signing secret (must match Fly secret) |
| `CALL_BASE_URL` | Web app URL (e.g. `https://voice-agent-web.fly.dev`) |
| `OPENCLAW_AGENT_NAME` | Base agent name (default: `voice-agent`) |
| `OPENCLAW_AGENT_DISPLAY_NAME` | Display name shown in UI |
| `OPENCLAW_AGENT_ID` | OpenClaw agent ID to route LLM through |
| `OPENCLAW_SESSION_KEY` | Pin voice calls to a specific OpenClaw session |
| `AGENT_HTTP_PORT` | LiveKit worker HTTP port (default: `8081`) |
| `AGENT_GREETING` | Text spoken on connect via TTS (bypasses LLM) |

## Redeploying

After code changes:

```bash
python3 scripts/deploy.py
```

This rebuilds and redeploys without re-prompting for credentials.

## Troubleshooting

**Call URL gives 401** — `CONFIG_SECRET` mismatch between `.env` and Fly secret. Re-run `python3 scripts/setup.py --update-secrets`.

**Agent not responding** — check the worker is running: `grep '[agent]' /tmp/agent-*.log`. Worker name in the JWT must match the registered LiveKit worker.

**"Waiting for agent to join" never resolves** — the agent worker isn't registered with LiveKit. Restart with `python agent.py start` and check the log for `registered worker`.
