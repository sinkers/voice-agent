---
name: talk-to-claw
description: >
  Deploy a voice calling web app so anyone can talk to an OpenClaw agent by clicking a link.
  Sets up a Fly.io-hosted frontend + backend, generates signed call URLs, and manages
  multi-agent voice workers. Use when the user wants to set up voice calling, deploy the
  voice web app, generate a call link, or let someone talk to their OpenClaw agent by voice.
  Triggers on phrases like "talk to claw", "voice calling", "call link", "deploy voice app",
  "set up voice", "voice web app", "call URL", "let someone call my agent".
---

# Talk to Claw — Voice Calling for OpenClaw

## Installing this skill

Unzip the `.skill` package into your OpenClaw skills directory, then start a new session:

```bash
# Download (pin to a specific commit — replace with a release tag when available)
curl -L "https://github.com/sinkers/voice-agent/raw/8c3a2b55766f3b51402e92f382cbe1dae0c1634a/web-skill/talk-to-claw.skill" \
  -o talk-to-claw.skill

# Inspect before installing (recommended)
unzip -l talk-to-claw.skill

# Install (per-agent workspace)
unzip talk-to-claw.skill -d ~/.openclaw/workspace-<agent-id>/skills/

# Install (shared across all agents)
unzip talk-to-claw.skill -d ~/.openclaw/skills/
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
# From the repo root:
python3 web-skill/scripts/setup.py

# Or from the skill install directory (pass --repo so the script can find your repo):
python3 scripts/setup.py --repo ~/Documents/livekit-agent

# Or set an env var instead of --repo:
TALK_TO_CLAW_REPO=~/Documents/livekit-agent python3 scripts/setup.py
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
