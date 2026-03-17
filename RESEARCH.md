# LiveKit Conversational Voice Agent — Research & Implementation Plan

_Created: 2026-03-17_

---

## Overview

Build a conversational voice AI agent using LiveKit that can:
1. Talk to users over WebRTC (browser/app)
2. Accept/make phone calls via SIP
3. Join Microsoft Teams calls

The agent's brain is your chosen OpenClaw agent rather than a raw GPT-4o call. Voice is the transport layer; the OpenClaw agent handles intelligence, memory, and tool use.

---

## Stack Decision: LiveKit Agents Framework

**Use LiveKit Agents (Python SDK).** It's the right foundation for all three use cases.

### Why

- Full WebRTC media stack handled by LiveKit — no DIY DTLS/ICE
- Native STT → LLM → TTS pipeline with turn detection and interruption handling
- Same framework covers WebRTC, SIP telephony, and (partially) Teams
- Apache 2.0 licensed, active community
- Python >= 3.10 required

**Decision: LiveKit Cloud.** Managed infra, built-in inference, less ops. Self-host later if usage/cost warrants.

---

## LLM: OpenClaw Gateway instead of raw GPT-4o

### The key insight

OpenClaw's Gateway already exposes an **OpenAI-compatible `/v1/chat/completions` endpoint**.
LiveKit's `openai.LLM` plugin supports a custom `base_url` override.

Result: **zero custom plugin code**. Point the LLM at the local Gateway, target a configured agent, and every voice call goes through me — with full memory, tools, and persona intact.

### What your OpenClaw agent brings to a voice call

| Capability | Detail |
|-----------|--------|
| **Long-term memory** | `MEMORY.md` — project context, preferences, past decisions |
| **Daily context** | `memory/YYYY-MM-DD.md` — recent session activity |
| **Persona** | `SOUL.md` — consistent personality across voice and text |
| **Tools** | Web search, file ops, exec, cron — your agent can *do things* during a call |
| **User context** | `USER.md` — knows who Andrew is, timezone, preferences |

### Architecture

```
User mic → LiveKit Cloud (WebRTC/SIP)
                ↓ audio
          Pi: LiveKit agent process
                ↓ audio chunks
          Deepgram Nova-3 (STT)
                ↓ text
          OpenClaw Gateway :18789/v1/chat/completions
                ↓ agent turn
          OpenClaw agent — memory + tools + persona
                ↓ text response
          OpenAI TTS (alloy voice)
                ↓ audio
          LiveKit Cloud → user speakers
```

### Implementation

```python
# agent.py — LLM config
import os

openai.LLM(
    model="openclaw:{OPENCLAW_AGENT_ID}",
    base_url=os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1"),
    api_key=os.getenv("OPENCLAW_GATEWAY_TOKEN"),
)
```

Gateway details:
- **Endpoint:** `http://127.0.0.1:18789/v1/chat/completions`
- **Auth:** Bearer token (from `OPENCLAW_GATEWAY_TOKEN`)
- **Agent targeting:** `model: "openclaw:{OPENCLAW_AGENT_ID}"` routes to the configured agent
- **Streaming:** SSE supported — compatible with LiveKit's openai plugin

### Session persistence

The gateway derives a stable session key from the OpenAI `user` field. Options:

| Strategy | `user` value | Result |
|----------|-------------|--------|
| **Per-caller session** (recommended) | `"voice-andrew"` | Agent remembers voice call history across calls — dedicated voice session separate from Telegram |
| **Stateless** | (omit) | New session per call, no cross-call memory |

With a stable user value, the agent will remember context between voice sessions (different from the Telegram session but same knowledge base from MEMORY.md).

### System prompt strategy

Your OpenClaw agent already has a configured persona. The `instructions` in the LiveKit agent should add **voice-mode constraints only** — not redefine the persona:

```python
instructions=(
    "You are responding via a real-time voice call. "
    "Keep responses brief (1–3 sentences max), conversational, and clear. "
    "Avoid markdown, lists, and long explanations — this is spoken audio. "
    "You can use your tools if needed to answer questions accurately."
)
```

This is additive — it layers on top of the agent's existing context.

### Security note

The Gateway token is a full operator credential — treat it like a root key. Keep it:
- In `.env` only (gitignored)
- Never in code or logs
- On loopback only — do not expose port 18789 to the internet

---

## Stage 1: WebRTC Voice Agent

### AI Model Pipeline

- **STT:** Deepgram Nova-3
- **LLM:** OpenClaw Gateway → configured agent
- **TTS:** OpenAI TTS (alloy voice)
- **VAD:** Silero (prewarmed)

### Dev Setup Steps

1. Create LiveKit Cloud account, get API keys
2. `uv sync` in project directory
3. `python agent.py download-files` (Silero VAD model)
4. `python agent.py dev`
5. Test via LiveKit Agents Playground

---

## Stage 2: SIP / Telephony Integration

LiveKit has **native SIP support** — this is well-trodden ground.

### Architecture

```
Phone network
      ↕ SIP trunk
  SIP provider (Telnyx — recommended for AU)
      ↕ SIP over UDP/TCP/TLS
  LiveKit SIP gateway
      ↕ (internal)
  LiveKit room (caller joins as SIP participant)
      ↕ same pipeline above
  Agent (Deepgram → OpenClaw agent → OpenAI TTS)
```

SIP callers appear as regular LiveKit participants — the agent code doesn't change.

### SIP Provider: Telnyx (AU)

- Telnyx has AU numbers (+61), competitive pricing, well-documented LiveKit integration
- Configure SIP trunk to point at your LiveKit SIP endpoint (LiveKit Cloud → Project Settings)
- Create inbound trunk + dispatch rule in LiveKit Cloud dashboard
- Create outbound trunk for agent-initiated calls

### Features available

- Inbound + outbound calls ✅
- DTMF tones ✅
- Call transfer (cold + warm) ✅
- Secure trunking (SRTP) ✅
- SIP REGISTER ❌ (not supported)

---

## Stage 3: Microsoft Teams Integration

### Requirement

**Always-on calling is required** — the agent must receive and initiate calls at any time. SIP dial-in is not viable (only works for scheduled meetings with PSTN dial-in enabled).

**Decision: Microsoft Graph Calling Bot (Option B)**

### Architecture

```
Teams user calls the bot (or bot initiates call)
        ↕ Teams Real-time Media Platform
  Azure VM (Windows) — .NET media bot
        ↕ SIP bridge (reuses Stage 2 infra)
  LiveKit room
        ↕
  Agent (Deepgram → OpenClaw agent → OpenAI TTS)
```

### What's required

| Component | Detail |
|-----------|--------|
| Azure Bot registration | App registration in Azure AD with bot channel enabled |
| Graph API permissions | `Calls.Initiate.All`, `Calls.JoinGroupCall.All`, `Calls.AccessMedia.All` |
| Admin consent | Teams admin must grant permissions |
| Media processing | Microsoft.Graph.Communications.Calls.Media (.NET) |
| Hosting | Windows Server or Azure VM (Linux not supported for media) |
| Bridge | .NET media bot dials LiveKit SIP endpoint (reuses Stage 2) |

### Setup steps

1. Azure AD app registration + Bot Framework channel
2. Request + get admin consent for Calls permissions
3. Deploy .NET media bot on Azure Windows VM
4. Bridge: Teams media bot dials into LiveKit SIP endpoint
5. Test inbound (user calls bot) and outbound (agent initiates)

---

## Staged Implementation Plan

### Phase 1 — WebRTC (complete)
- [x] LiveKit Cloud project + API keys
- [x] Python env (uv), agent.py scaffolded
- [x] Deepgram STT + OpenAI TTS + Silero VAD
- [x] Tested via LiveKit Agents Playground
- [ ] **Swap LLM to OpenClaw Gateway** ← current task

### Phase 2 — SIP / Phone Calls (next)
- [ ] Telnyx account + AU number
- [ ] Configure Telnyx SIP trunk → LiveKit SIP endpoint
- [ ] Inbound trunk + dispatch rule in LiveKit Cloud
- [ ] Outbound trunk
- [ ] Test: inbound call → agent answers
- [ ] Test: agent dials out

### Phase 3 — Microsoft Teams
- [ ] Azure AD app registration + Bot Framework channel
- [ ] Graph API permissions + admin consent
- [ ] Deploy .NET media bot on Azure Windows VM
- [ ] Build SIP bridge: Teams media bot ↔ LiveKit SIP endpoint
- [ ] Test inbound (user calls bot) and outbound

---

## Key Links

- LiveKit Agents docs: https://docs.livekit.io/agents/
- LiveKit Telephony: https://docs.livekit.io/telephony/
- LiveKit Agents Playground: https://agents-playground.livekit.io/
- LiveKit Cloud: https://cloud.livekit.io/
- OpenClaw Gateway docs: ~/.npm-global/lib/node_modules/openclaw/docs/gateway/
- OpenClaw chat completions API: /gateway/openai-http-api
- Telnyx: https://telnyx.com
- Teams Calling Bot: https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/calls-meetings-bots-overview
