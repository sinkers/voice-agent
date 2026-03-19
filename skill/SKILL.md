---
name: clawtalk
description: >
  Manage a LiveKit conversational voice agent. Use when the user wants to set up or install
  a voice agent for the first time, start or stop the voice agent, check voice agent status
  or logs, troubleshoot voice connection issues, or connect a voice channel to a specific
  OpenClaw agent. Triggers on phrases like "start voice agent", "stop voice agent",
  "voice agent status", "set up voice agent", "install voice agent", "voice channel".
---

# LiveKit Voice Agent

Manages a LiveKit-based conversational voice agent that routes calls through any configured OpenClaw agent. The voice agent handles WebRTC (browser) and SIP (phone) connections; the OpenClaw agent provides the intelligence.

## Quick Reference

| Task | Command |
|------|---------|
| First-time setup | `python3 scripts/setup.py [install_path] [agent_id]` |
| Start agent | `python3 scripts/start.py [install_path]` |
| Stop agent | `python3 scripts/stop.py [install_path]` |
| Check status | `python3 scripts/status.py [install_path]` |

Default install path: `~/livekit-voice-agent`

## Setup (First Time)

Run setup.sh — it installs dependencies and auto-populates OpenClaw config:

```bash
python3 scripts/setup.py ~/livekit-voice-agent
```

Setup will:
1. Copy agent code to the install path
2. Create a Python virtualenv and install packages
3. Read OPENCLAW_GATEWAY_URL and OPENCLAW_GATEWAY_TOKEN from `~/.openclaw/openclaw.json`
4. **Ask which OpenClaw agent to use** (lists all available agents)
5. Print what still needs manual config

To skip the agent selection prompt, pass the agent ID directly:

```bash
python3 scripts/setup.py ~/livekit-voice-agent your-agent-id
```

## Choosing an Agent

The voice agent routes all LLM calls through a single OpenClaw agent. Any configured agent works — choose based on which agent's memory, persona, and tools are appropriate for the voice channel.

To list available agents:
```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.openclaw/openclaw.json'))); [print(a['id']) for a in d.get('agents',{}).get('list',[])]"
```

`OPENCLAW_AGENT_ID` in `.env` controls which agent is used. Change it anytime and restart.

## Manual Configuration

After setup, edit `<install_path>/.env` and fill in:

| Variable | Where to get it |
|----------|----------------|
| `LIVEKIT_URL` | [cloud.livekit.io](https://cloud.livekit.io) → Project Settings |
| `LIVEKIT_API_KEY` | LiveKit Cloud → Project Settings |
| `LIVEKIT_API_SECRET` | LiveKit Cloud → Project Settings |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) — $200 free credit |

Auto-populated by setup (verify these are correct):
- `OPENCLAW_GATEWAY_URL`
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_AGENT_ID`

Optional:
- `OPENCLAW_SESSION_KEY` — pin voice calls to a specific session for shared memory across channels. To share context with an existing chat session (e.g. Telegram), ask the agent "what is your session key?" and use that value. Must be in the format `agent:<agent_id>:<channel>:<id>`.

## Starting and Stopping

```bash
# Start
python3 scripts/start.py ~/livekit-voice-agent

# Stop
python3 scripts/stop.py ~/livekit-voice-agent

# Status + recent logs
python3 scripts/status.py ~/livekit-voice-agent
```

Logs are written to `<install_path>/agent.log`.

## Testing

Once running, connect via the LiveKit Agents Playground at agents-playground.livekit.io using your LiveKit Cloud credentials.

## Troubleshooting

- **Agent not responding**: Check `agent.log` with `status.sh`. Common causes: missing API keys in `.env`, Gateway not running (`openclaw gateway status`).
- **Wrong agent answering**: Check `OPENCLAW_AGENT_ID` and `OPENCLAW_SESSION_KEY` in `.env`.
- **Routing to wrong OpenClaw agent**: Session key format must be `agent:<agent_id>:...`. A bare session key (e.g. `voice-session`) routes to the default (main) agent regardless of `OPENCLAW_AGENT_ID`.
