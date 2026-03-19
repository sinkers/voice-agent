# Multi-Agent Install — Session Notes
*2026-03-19, Alex*

## What was done

### Goal
Install and configure a voice agent worker for every OpenClaw agent on the Pi,
so that each agent (Clive, Alex, Elysse, Colin, Mandy, Moxie) can be called by
voice and will respond in character.

### Agents installed

| Agent ID | Display Name | Install Dir | Port | Session Key |
|----------|-------------|-------------|------|-------------|
| main | Clive | ~/livekit-voice-main | 8081 | agent:main:voice:direct:hub |
| alex | Alex | ~/livekit-voice-alex | 8082 | agent:alex:telegram:direct:6946974355 |
| elysse | Elysse | ~/livekit-voice-elysse | 8083 | agent:elysse:voice:direct:hub |
| colin | Colin | ~/livekit-voice-colin | 8084 | agent:colin:voice:direct:hub |
| mandy | Mandy | ~/livekit-voice-mandy | 8085 | agent:mandy:voice:direct:hub |
| moxie | Moxie | ~/livekit-voice-moxie | 8086 | agent:moxie:voice:direct:hub |

### Call URLs (current — regenerated each worker restart)

```
Clive:  https://voice-agent-hub.fly.dev/call?agent_id=91168b30-c701-45c8-9f76-85fb856eb0ed
Alex:   https://voice-agent-hub.fly.dev/call?agent_id=54a95df9-9f5a-4999-9e4e-49c37c596c5b
Elysse: https://voice-agent-hub.fly.dev/call?agent_id=58b2287a-1a11-4111-87a4-e788f1bf2518
Colin:  https://voice-agent-hub.fly.dev/call?agent_id=51775caa-c7f1-45fd-945e-a4868c10cd15
Mandy:  https://voice-agent-hub.fly.dev/call?agent_id=b4f6f84e-a280-42a9-bb1c-caebd98d9afe
Moxie:  https://voice-agent-hub.fly.dev/call?agent_id=6fe76acb-b961-4962-99d2-592a714e03cc
```

Agent IDs are stable across restarts (persisted by the hub).

To refresh URLs after restart:
```bash
for agent in main alex elysse colin mandy moxie; do
  echo -n "$agent: "
  grep "Call URL:" ~/livekit-voice-$agent/agent.log | tail -1 | awk '{print $NF}'
done
```

---

## Key decisions & discoveries

### Hosted mode — .env is minimal
In the hosted hub flow, `LIVEKIT_*`, `OPENAI_API_KEY`, and `DEEPGRAM_API_KEY` are
pulled from the hub at startup (via `/agent/config`). The `.env` only needs:
- `OPENCLAW_GATEWAY_URL` + `OPENCLAW_GATEWAY_TOKEN` — route LLM through OpenClaw
- `OPENCLAW_AGENT_ID` — which agent to use
- `OPENCLAW_AGENT_NAME` — worker identity / hub token filename
- `OPENCLAW_AGENT_DISPLAY_NAME` — display name in hub
- `AGENT_GREETING` — opening line when call connects
- `AGENT_HTTP_PORT` — unique port per worker (8081–8086)
- `OPENCLAW_SESSION_KEY` — pin voice calls to the correct agent session

### Session key is critical
Without a pinned `OPENCLAW_SESSION_KEY`, voice calls with no session key create an
anonymous session. The gateway's `dmScope: per-channel-peer` routing has no peer ID
for hub-originated calls, so sessions collapse to `main` / Clive. All agents were
answering as Clive until session keys were added.

Session key format: `agent:<agentId>:voice:direct:hub`

### CLAWTALK.md is not auto-injected
OpenClaw auto-injects: `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`,
`TOOLS.md`, `HEARTBEAT.md`, `MEMORY.md` (main sessions only).

Custom files like `CLAWTALK.md` are NOT auto-injected. The fix was to:
1. Write the call URL into `IDENTITY.md` (always injected) at the bottom
2. Write the call URL into `MEMORY.md` with clear retrieval instructions
3. Have `agent.py` write `CLAWTALK.md` at startup as a backup reference

### agent.py from skill assets is stripped
`skill/assets/agent/agent.py` is a simplified version without hub auth or port
config. For multi-agent installs, use the full repo `agent.py` which includes:
- Hub device-auth flow + token caching
- Hub registration + call URL generation
- Per-agent workspace CLAWTALK.md writing
- `AGENT_HTTP_PORT` env var support
- Heartbeat thread

### Hub token reuse
The hub token is stored per `OPENCLAW_AGENT_NAME` in `.hub-token-{name}`.
Copying the existing `voice-agent` token to `.hub-token-voice-{agentId}` in each
install dir skips the device-auth flow. All 6 agents share the same hub account.

---

## Files changed

### `agent.py`
Added workspace write after hub registration: writes call URL to
`~/.openclaw/workspace[-{agentId}]/CLAWTALK.md` so the agent always has its
current voice URL available.

### `scripts/install_all_agents.py` (new)
Installs all 6 agents in one shot. Handles:
- Calling `skill/scripts/setup.py` for each agent
- Patching `.env` with per-agent identity + hosted-mode credentials
- Copying the full repo `agent.py` (not the stripped skill asset)
- Starting all workers

### Per-workspace IDENTITY.md
Each agent's `IDENTITY.md` now includes a `ClawTalk URL` line. This is the
reliable way to ensure agents know their own call URL — IDENTITY.md is always
injected into every session context.

### Per-workspace MEMORY.md
Each agent's `MEMORY.md` includes a `My Voice Call URL` section with the URL
and retrieval instructions.

---

## How to restart workers

```bash
# Kill all
ps aux | grep "agent.py" | grep -v grep | awk '{print $2}' | xargs -r kill -9

# Start all
for agent in main alex elysse colin mandy moxie; do
  dir=~/livekit-voice-$agent
  : > "$dir/agent.log"
  cd "$dir"
  PYTHONUNBUFFERED=1 nohup uv run python -u agent.py > "$dir/agent.log" 2>&1 &
  echo $! > "$dir/agent.pid"
  echo "Started $agent PID=$!"
done
```

Note: after restart, `agent.py` rewrites CLAWTALK.md and IDENTITY.md is already
updated. No further action needed.

---

## Known issues / TODO

- [ ] Workers are not managed by systemd — they die if the Pi reboots. Add
      systemd units for each worker (or one unit that starts all 6).
- [ ] The `install_all_agents.py` script has credentials hardcoded. Should read
      from `.env.shared` or the existing `~/Documents/livekit-agent/.env` instead.
- [ ] CLAWTALK.md being in workspace root doesn't help current sessions — only
      freshly started ones see it. IDENTITY.md is the reliable injection point.
- [ ] `agent.py` CLAWTALK.md write should also update IDENTITY.md at startup
      rather than relying on a one-time manual edit.
