---
name: livekit-voice-web
description: >
  Deploy and manage the LiveKit voice agent web app on Fly.io. Use when the user wants to
  deploy the voice agent web interface, set up a public call URL, configure multi-agent
  support, or manage an existing deployment. Triggers on phrases like "deploy voice web app",
  "set up voice web", "voice agent web", "call URL", "fly deploy voice", "web app setup".
---

# LiveKit Voice Web — Fly.io Deployment Skill

## Installing this skill

Unzip the `.skill` package into your OpenClaw skills directory, then start a new session:

```bash
# Download (pin to a specific commit — replace with a release tag when available)
curl -L "https://github.com/sinkers/voice-agent/raw/4e0d29549a6ff9a5635d6a8309c08616d69d8ca1/web-skill/livekit-voice-web.skill" \
  -o livekit-voice-web.skill

# Inspect before installing (recommended)
unzip -l livekit-voice-web.skill

# Install (per-agent workspace)
unzip livekit-voice-web.skill -d ~/.openclaw/workspace-<agent-id>/skills/

# Install (shared across all agents)
unzip livekit-voice-web.skill -d ~/.openclaw/skills/
```

See [web-skill/README.md](README.md) for full install options.

Deploys the voice agent web app (React frontend + FastAPI backend) to Fly.io and sets up signed JWT call URLs so any OpenClaw instance can generate a click-to-call link.

## Quick Reference

| Task | Command |
|------|---------|
| First-time deploy | `python3 web-skill/scripts/setup.py` |
| Redeploy (after code changes) | `python3 web-skill/scripts/deploy.py` |
| Generate a call URL | `python3 web-skill/scripts/call_url.py --agent <name> --name "<display>"` |
| Check deployment status | `python3 web-skill/scripts/status.py` |

## Before You Start

### Required accounts and credentials

You need the following before running setup. If you already have an account, just grab the credentials — setup will prompt for each one.

| Service | What it's used for | Sign up | Free tier? |
|---------|-------------------|---------|-----------|
| **LiveKit Cloud** | WebRTC infrastructure, room management | https://cloud.livekit.io | ✅ Yes |
| **Deepgram** | Speech-to-text (STT) | https://console.deepgram.com | ✅ Yes ($200 credit) |
| **OpenAI** | LLM (GPT-4o) + TTS (alloy voice) | https://platform.openai.com | ❌ Pay per use |
| **Fly.io** | Hosts the web frontend + backend | https://fly.io/app/sign-up | ✅ Yes |

### Credentials the setup script will ask for

```
LIVEKIT_URL          wss://your-project.livekit.cloud
                     → LiveKit Cloud → Project Settings → URL

LIVEKIT_API_KEY      APIxxxxxxxxxxxxxxxxx
                     → LiveKit Cloud → Project Settings → API Keys → Create key

LIVEKIT_API_SECRET   (shown once at key creation — copy immediately)
                     → LiveKit Cloud → Project Settings → API Keys → Create key
```

The following are set in your agent's `.env` separately (not prompted by this script):

```
DEEPGRAM_API_KEY     → console.deepgram.com → API Keys → Create key
OPENAI_API_KEY       → platform.openai.com/api-keys → Create new secret key
```

The script will **auto-generate** `CONFIG_SECRET` and write it to `.env` and Fly secrets — you don't need to create this yourself.

### If you already have everything set up

You only need to provide:
- Your Fly.io app name (default: `voice-agent-web`)
- LiveKit URL, API key, and secret
- Confirmation to reuse the existing `CONFIG_SECRET` from `.env` (or generate a new one)

Run with `--update-secrets` to rotate credentials without redeploying:
```bash
python3 web-skill/scripts/setup.py --update-secrets
```

---

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
