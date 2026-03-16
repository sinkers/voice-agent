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

| Variable | Where to get it |
|----------|----------------|
| `LIVEKIT_URL` | [LiveKit Cloud](https://cloud.livekit.io) → Project Settings |
| `LIVEKIT_API_KEY` | LiveKit Cloud → Project Settings |
| `LIVEKIT_API_SECRET` | LiveKit Cloud → Project Settings |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) ($200 free credit) |

> ⚠️ `.env` is gitignored. Never commit real credentials — use `.env.example` for the template.

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
