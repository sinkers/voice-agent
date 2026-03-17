# LiveKit Voice Agent

A conversational voice AI agent built on LiveKit Agents v0.12+.

**Stack:** Deepgram STT (nova-3) → OpenAI GPT-4o → OpenAI TTS, with Silero VAD.  
**Infrastructure:** LiveKit Cloud

---

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) package manager
- A [LiveKit Cloud](https://cloud.livekit.io/) project
- OpenAI and Deepgram API keys

---

## Phase 1 — WebRTC Voice Agent

### 1. Environment setup

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Then edit `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `LIVEKIT_URL` | ✅ | [LiveKit Cloud](https://cloud.livekit.io) → Project Settings |
| `LIVEKIT_API_KEY` | ✅ | LiveKit Cloud → Project Settings |
| `LIVEKIT_API_SECRET` | ✅ | LiveKit Cloud → Project Settings |
| `OPENAI_API_KEY` | ✅ | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) — used for TTS and GPT-4o fallback |
| `DEEPGRAM_API_KEY` | ✅ | [console.deepgram.com](https://console.deepgram.com) — $200 free credit |
| `OPENCLAW_GATEWAY_TOKEN` | Optional | Enables LLM routing through OpenClaw. Without it, falls back to direct GPT-4o |
| `OPENCLAW_GATEWAY_URL` | Optional | Gateway URL. Defaults to `http://127.0.0.1:18789/v1` |
| `OPENCLAW_AGENT_ID` | Optional | Which OpenClaw agent to use. Defaults to `main` |
| `OPENCLAW_SESSION_KEY` | Optional | Pin to a specific session for shared memory. Omit for fresh session per call |

> ⚠️ `.env` is gitignored. Never commit real credentials — use `.env.example` for the template.
> See `.env.example` for full documentation on each variable.

### 2. Install dependencies

```bash
uv venv --python 3.11
source .venv/bin/activate
uv sync
```

### 3. Download model files (first time only)

```bash
python agent.py download-files
```

This downloads the Silero VAD model (~50MB).

### 4. Run in dev mode

```bash
python agent.py dev
```

The agent registers with LiveKit Cloud and waits for participants.

### 5. Connect and test

1. Go to [agents-playground.livekit.io](https://agents-playground.livekit.io/)
2. Enter your LiveKit Cloud URL + API key + secret
3. Click **Connect** — the agent joins the room and greets you

---

## OpenClaw Integration (Alex as the LLM)

Instead of calling GPT-4o directly, the agent routes all LLM calls through the **local OpenClaw Gateway** — targeting the `alex` agent. This means every voice call goes through Alex, who has:

- **Long-term memory** (`MEMORY.md`) — project context, preferences, past decisions
- **Daily context** (`memory/YYYY-MM-DD.md`) — recent activity
- **Persona** (`SOUL.md`) — consistent voice across text and voice channels
- **Tools** — web search, file ops, exec, cron — Alex can take actions during a call
- **User context** (`USER.md`) — knows who you are

### How it works

The LiveKit `openai.LLM` plugin supports a custom `base_url`. OpenClaw's Gateway exposes an OpenAI-compatible `/v1/chat/completions` endpoint. Zero custom plugin code needed.

```
Deepgram STT → text
    → POST {OPENCLAW_GATEWAY_URL}/chat/completions
      model: "openclaw:{OPENCLAW_AGENT_ID}"
      Authorization: Bearer {OPENCLAW_GATEWAY_TOKEN}
      x-openclaw-agent-id: {OPENCLAW_AGENT_ID}
      x-openclaw-session-key: {OPENCLAW_SESSION_KEY}
    → OpenClaw agent turn (with memory, tools, persona)
    → response text
→ OpenAI TTS → audio
```

All agent-specific values (`OPENCLAW_AGENT_ID`, `OPENCLAW_SESSION_KEY`) are configured in `.env` — no names or IDs are hardcoded in the source.

### Fallback to GPT-4o

If `OPENCLAW_GATEWAY_TOKEN` is not set, the agent falls back to direct GPT-4o automatically. Useful for testing without the Gateway running.

### Requirements

- OpenClaw Gateway must be running: `openclaw gateway status`
- `chatCompletions` endpoint must be enabled in `~/.openclaw/openclaw.json`:
  ```json
  { "gateway": { "http": { "endpoints": { "chatCompletions": { "enabled": true } } } } }
  ```
- The following set in `.env` (see `.env.example` for full documentation):
  - `OPENCLAW_GATEWAY_TOKEN`
  - `OPENCLAW_AGENT_ID`
  - `OPENCLAW_SESSION_KEY` (optional — omit for fresh session per call)

### Session key

The `OPENCLAW_SESSION_KEY` determines memory persistence:

| Value | Behaviour |
|-------|-----------|
| _(omit)_ | New session per call — no memory between calls |
| A unique key e.g. `voice-session-1` | Persistent voice-only session |
| Your chat session key | Voice and chat share the same session and context |

To find your chat session key, ask your OpenClaw agent: **"What is your session key?"**

> ⚠️ Session keys must be fully scoped to the correct agent. An incorrectly scoped key will route to the wrong agent. The format is typically `agent:<agent-id>:<channel>:<id>`.

### Security

The Gateway token is a full operator credential — treat it like a root key. Keep port 18789 on loopback or LAN only; never expose it to the public internet.

---

## Phase 2 — SIP / Phone Calls

### Telnyx setup

1. Create an account at [telnyx.com](https://telnyx.com) and add credit
2. Buy an AU number: **Numbers → Search & Buy** → filter by country AU (+61)
3. Go to **Voice → SIP Trunking → Trunks** → Create trunk:
   - Name: `livekit-agent`
   - **Origination URI:** your LiveKit SIP endpoint (found in LiveKit Cloud → Project Settings)
     - Format: `vjnxecm0tjk.sip.livekit.cloud` (the part after `sip:`)
   - **Authentication:** set a username + password (you'll need these for the outbound trunk)
4. Assign your phone number to the trunk

### LiveKit Cloud — Telephony setup

Go to [cloud.livekit.io](https://cloud.livekit.io) → **Telephony**

**Inbound trunk** (SIP Trunks → Create → Inbound):
```json
{
  "name": "Telnyx Inbound",
  "numbers": ["+61XXXXXXXXX"]
}
```

**Dispatch rule** (Dispatch Rules → Create):
```json
{
  "rule": {
    "dispatchRuleIndividual": {
      "roomPrefix": "call-"
    }
  },
  "trunkIds": ["<your-inbound-trunk-id>"]
}
```

Each caller gets their own room → your agent is dispatched automatically.

**Outbound trunk** (SIP Trunks → Create → Outbound):
```json
{
  "name": "Telnyx Outbound",
  "address": "sip.telnyx.com",
  "numbers": ["+61XXXXXXXXX"],
  "authUsername": "<telnyx-username>",
  "authPassword": "<telnyx-password>"
}
```

### Test inbound

Call your Telnyx number → agent should answer within a few seconds.

---

## Phase 3 — Microsoft Teams

### Approach: Microsoft Graph Calling Bot (required)

**Requirement:** The agent must be available to receive or initiate Teams calls at any time — not just join scheduled meetings. SIP dial-in is off the table for this reason.

The only path that satisfies this is a **Microsoft Graph Calling Bot** — a first-class Teams participant that can receive inbound calls directed to it and place outbound calls at will.

#### What's required

| Component | Detail |
|-----------|--------|
| Azure Bot registration | App registration in Azure AD with bot channel enabled |
| Graph API permissions | `Calls.Initiate.All`, `Calls.JoinGroupCall.All`, `Calls.JoinGroupCallAsGuest.All`, `Calls.AccessMedia.All` |
| Admin consent | Teams admin must grant the above permissions |
| Media processing | Microsoft.Graph.Communications.Calls.Media (.NET library) |
| Hosting | Windows Server or Azure VM (Linux not supported for media bot) |
| Bridge | Audio bridge between Teams media ↔ LiveKit agent |

#### Architecture

```
Teams user calls the bot (or bot initiates call)
        ↕ Teams Real-time Media Platform
  Azure VM (Windows) — .NET media bot
        ↕ audio bridge (RTP/WebSocket)
  LiveKit room
        ↕
  LiveKit agent (Python)
```

#### Setup steps (high level)

1. Register an app in Azure AD → enable Bot Framework channel
2. Request + get admin consent for Calls permissions
3. Deploy .NET media bot on Azure Windows VM
4. Build audio bridge: Teams media bot streams audio → LiveKit room via SIP or RTP
5. LiveKit agent handles the conversation as normal

#### Note on the media bridge

The .NET media bot handles Teams-side media. To connect to LiveKit, the bridge can either:
- Dial into a LiveKit SIP endpoint (reusing Phase 2 infrastructure), or
- Stream RTP audio directly into a LiveKit room

The SIP bridge approach is simpler — the .NET bot acts as a SIP client dialling into LiveKit.

---

## Project structure

```
agent.py        # Main agent entrypoint
pyproject.toml  # Dependencies
.env            # API keys (gitignored)
.gitignore
README.md
RESEARCH.md     # Architecture decisions and research notes
```

---

## Useful links

- [LiveKit Agents docs](https://docs.livekit.io/agents/)
- [LiveKit Telephony docs](https://docs.livekit.io/telephony/)
- [LiveKit Agents Playground](https://agents-playground.livekit.io/)
- [LiveKit Cloud dashboard](https://cloud.livekit.io/)
- [Telnyx dashboard](https://portal.telnyx.com/)
- [OpenAI API keys](https://platform.openai.com/api-keys)
- [Deepgram console](https://console.deepgram.com/)
