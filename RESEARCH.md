# LiveKit Conversational Voice Agent — Research & Implementation Plan

_Created: 2026-03-17_

---

## Overview

Build a conversational voice AI agent using LiveKit that can:
1. Talk to users over WebRTC (browser/app)
2. Accept/make phone calls via SIP
3. Join Microsoft Teams calls

---

## Stack Decision: LiveKit Agents Framework

**Use LiveKit Agents (Python SDK).** It's the right foundation for all three use cases.

### Why

- Full WebRTC media stack handled by LiveKit — no DIY DTLS/ICE
- Native STT → LLM → TTS pipeline with turn detection and interruption handling
- Same framework covers WebRTC, SIP telephony, and (partially) Teams
- Apache 2.0 licensed, active community
- Python >= 3.10 required

### Deployment options

| Option | Tradeoffs |
|--------|-----------|
| **LiveKit Cloud** | Managed infra, built-in inference (no API keys needed for models), easy deploy, has costs | 
| **Self-hosted LiveKit server** | Free, full control, more ops work; requires your own model API keys |

**Decision: LiveKit Cloud.** Managed infra, built-in inference, less ops. Self-host later if usage/cost warrants.

---

## Stage 1: WebRTC Voice Agent

### Architecture

```
Browser (LiveKit JS SDK)
       ↕ WebRTC
  LiveKit Server (Cloud or self-hosted)
       ↕ LiveKit Agents SDK
  Agent process (Python)
       ↕ HTTP/WS
  AI providers: STT + LLM + TTS
```

### AI Model Pipeline

Two approaches:

**Option A: STT → LLM → TTS (modular pipeline)**
- STT: Deepgram Nova-3 or AssemblyAI (low latency, good accuracy)
- LLM: OpenAI GPT-4o or Claude (via OpenAI-compatible endpoint)
- TTS: Cartesia Sonic or ElevenLabs (most natural voice quality)
- Turn detection: LiveKit's built-in Silero VAD + custom turn detector

**Option B: Realtime speech-to-speech (OpenAI Realtime API)**
- Single model handles STT + LLM + TTS
- Lower latency, but locked to OpenAI
- Less control over individual components

**Recommendation:** Start with Option A (modular). More flexibility, cheaper long-term, not locked to one provider.

### Key SDK Components

```python
from livekit.agents import AgentSession, Agent
from livekit.plugins import openai, deepgram, cartesia, silero

session = AgentSession(
    stt=deepgram.STT(model="nova-3"),
    llm=openai.LLM(model="gpt-4o"),
    tts=cartesia.TTS(voice="..."),
    vad=silero.VAD.load(),
    # turn_detection=... (LiveKit's custom model)
)
```

### Frontend

LiveKit has a prebuilt React component library (`@livekit/components-react`). For a quick start, their [Agent Playground](https://github.com/livekit/agent-playground) is a ready-to-use web UI for testing agents.

### Dev Setup Steps (Stage 1)

1. Create LiveKit Cloud account, get API keys
2. `pip install livekit-agents[openai,deepgram,cartesia,silero]`
3. Bootstrap with `lk app create --template voice-pipeline-agent-python`
4. Run agent: `python agent.py dev`
5. Test via browser at the LiveKit playground URL

---

## Stage 2: SIP / Telephony Integration

LiveKit has **native SIP support** — this is well-trodden ground.

### Architecture

```
Phone network
      ↕ SIP trunk
  SIP provider (Telnyx, Twilio, Vonage, etc.)
      ↕ SIP over UDP/TCP/TLS
  LiveKit SIP gateway
      ↕ (internal)
  LiveKit room (caller joins as SIP participant)
      ↕ same as WebRTC path above
  Agent
```

SIP callers appear as regular LiveKit participants — the agent code doesn't change.

### SIP Provider Options

| Provider | Notes |
|----------|-------|
| **Telnyx** | Well-documented with LiveKit, competitive pricing, AU numbers |
| **Twilio** | Widely used, pricier, solid docs |
| **Vonage/Nexmo** | Another option with AU coverage |
| **LiveKit Phone Numbers** | US-only currently, not useful for AU |

**For Australia:** Telnyx or Twilio both have AU numbers. Telnyx tends to be cheaper.

### Setup Steps (Stage 2)

1. Sign up for Telnyx (or Twilio), purchase an AU number
2. Configure SIP trunk to point at LiveKit's SIP endpoint
3. Create **inbound trunk** in LiveKit Cloud dashboard (JSON config)
4. Create **dispatch rule** — maps inbound calls to a room, which dispatches your agent
5. For outbound: create **outbound trunk**, use `CreateSIPParticipant` API to dial out
6. Test: call your number → agent answers

### Features available

- Inbound + outbound calls ✅
- DTMF tones ✅ (useful for IVR/menus)
- Call transfer (cold + warm) ✅
- Secure trunking (SRTP) ✅
- HD voice ✅
- SIP REGISTER ❌ (not supported)

---

## Stage 3: Microsoft Teams Integration

This is the most complex stage. There are three viable approaches — ordered by effort:

---

### Option A: SIP via Teams Direct Routing (Recommended)

Teams supports **Direct Routing** — you connect your own SIP trunk to Teams, then any Teams meeting with a dial-in number can be joined by your agent calling in via SIP.

```
Teams meeting (with PSTN dial-in enabled)
      ↕ SIP
  Your SIP provider (same trunk as Stage 2)
      ↕
  LiveKit agent dials out → joins as phone participant
```

**Pros:**
- Reuses the same LiveKit SIP infrastructure from Stage 2
- No Microsoft Graph API complexity
- Agent audio works immediately

**Cons:**
- Appears as a phone participant, not a named bot
- Requires Teams Phone System license + Direct Routing setup (or existing PSTN dial-in numbers on meetings)
- No video

**Effort:** Medium — if SIP is already working, this is mostly Teams config

---

### Option B: Microsoft Graph Calling Bot API (Native Teams bot)

Register a bot via Azure, implement the Teams Real-time Media Platform SDK. The bot joins calls as a first-class Teams participant.

```
Teams call
      ↕ Teams Real-time Media Platform
  Azure Bot (Windows Server / Azure VM)
      ↕ WebSocket bridge
  LiveKit agent
```

**Pros:**
- Full Teams presence — named participant, can see/be seen
- Can handle inbound calls to the bot directly
- Access to transcription, video streams

**Cons:**
- **Requires .NET and Windows Server** for media processing (big constraint)
- Azure registration, Graph API permissions (`Calls.JoinGroupCall.All` etc.), admin consent
- Complex to set up and maintain
- Needs a bridge between Teams media and LiveKit

**Effort:** High

---

### Option C: Azure Communication Services (ACS) Bridge

ACS can join Teams meetings natively. You can connect ACS to LiveKit via SIP or WebRTC bridging.

```
Teams meeting
      ↕ ACS Teams interop
  Azure Communication Services
      ↕ SIP/WebRTC bridge
  LiveKit agent
```

**Pros:**
- Avoids Windows Server requirement
- ACS can be a "guest" in Teams meetings

**Cons:**
- Two cloud platforms to manage (ACS + LiveKit)
- ACS calling has its own costs
- Bridge adds latency

**Effort:** Medium-High

---

### Teams Requirement (updated)

**Always-on calling is required** — the agent must be able to receive calls or initiate calls at any time, not just join scheduled meetings. This rules out Option A (SIP dial-in), which only works when a meeting is already running with a PSTN dial-in number.

**Decision: Option B (Microsoft Graph Calling Bot)** — required for always-on inbound/outbound Teams calling. Option A is off the table.

---

## Staged Implementation Plan

### Phase 1 — WebRTC Voice Agent (1–2 days)

- [ ] LiveKit Cloud account + project
- [ ] Python env (uv), bootstrap from template
- [ ] Wire up: Deepgram STT + GPT-4o LLM + Cartesia TTS
- [ ] Silero VAD + turn detection
- [ ] Test with LiveKit browser playground
- [ ] Define agent persona/system prompt
- [ ] Basic tool use (e.g., get time, look things up)

**Output:** Agent you can talk to in a browser over WebRTC.

---

### Phase 2 — SIP / Phone Calls (2–3 days)

- [ ] Choose SIP provider (Telnyx recommended for AU)
- [ ] Purchase AU phone number
- [ ] Configure Telnyx SIP trunk → LiveKit
- [ ] Create inbound trunk + dispatch rule in LiveKit
- [ ] Create outbound trunk
- [ ] Test: inbound call → agent answers
- [ ] Test: agent dials out via `CreateSIPParticipant`
- [ ] DTMF handling if needed

**Output:** Agent accessible by phone.

---

### Phase 3 — Microsoft Teams (2–5 days)

**Chosen approach: Microsoft Graph Calling Bot (Option B)**
Always-on calling is required — the agent must receive and initiate calls at any time. SIP dial-in (Option A) is not viable as it only works for scheduled meetings with PSTN dial-in enabled.

- [ ] Azure AD app registration + Bot Framework channel
- [ ] Request Graph API permissions: `Calls.Initiate.All`, `Calls.JoinGroupCall.All`, `Calls.AccessMedia.All`
- [ ] Teams admin consent for permissions
- [ ] Deploy .NET media bot on Azure Windows VM
- [ ] Build audio bridge: Teams media bot ↔ LiveKit SIP endpoint
- [ ] Test inbound call to bot (user calls bot directly in Teams)
- [ ] Test outbound call (agent initiates call to Teams user)

**Output:** Agent that can join Teams calls.

---

## Key Links

- LiveKit Agents docs: https://docs.livekit.io/agents/
- LiveKit Telephony: https://docs.livekit.io/telephony/
- Voice AI quickstart: https://docs.livekit.io/agents/start/voice-ai/
- LiveKit Cloud: https://cloud.livekit.io/
- Agent Playground (frontend): https://github.com/livekit/agent-playground
- Telnyx LiveKit guide: https://telnyx.com/resources/livekit
- Teams Calling Bot docs: https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/calls-meetings-bots-overview
- Teams Direct Routing: https://learn.microsoft.com/en-us/microsoftteams/direct-routing-landing-page

---

## Open Questions

1. Self-hosted LiveKit vs LiveKit Cloud — what's the budget/privacy posture?
2. Which LLM? GPT-4o is lowest latency for voice. Claude needs an OpenAI-compatible wrapper.
3. TTS voice preference — need to audition Cartesia vs ElevenLabs
4. For Teams: do meetings already have dial-in numbers, or is Option B required?
5. What's the agent's persona and purpose? General assistant vs domain-specific?
