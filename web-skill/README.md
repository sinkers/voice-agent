# livekit-voice-web skill

OpenClaw skill for deploying and managing the LiveKit voice agent web app on Fly.io.

## Installing the skill

OpenClaw loads skills from `<workspace>/skills/` or `~/.openclaw/skills/`. There are two ways to install:

### Option A — Manual install (recommended for now)

```bash
# 1. Download the skill package (pin to a specific commit or release tag)
SKILL_URL="https://github.com/sinkers/voice-agent/raw/4e0d29549a6ff9a5635d6a8309c08616d69d8ca1/web-skill/livekit-voice-web.skill"
curl -L "$SKILL_URL" -o livekit-voice-web.skill

# 2. Inspect the package contents before installing (optional but recommended)
unzip -l livekit-voice-web.skill

# 3. Unzip into your OpenClaw skills directory
#    Per-agent (only your agent sees it):
mkdir -p ~/.openclaw/workspace-<your-agent>/skills
unzip livekit-voice-web.skill -d ~/.openclaw/workspace-<your-agent>/skills/

#    Or shared across all agents on this machine:
mkdir -p ~/.openclaw/skills
unzip livekit-voice-web.skill -d ~/.openclaw/skills/

# 4. Start a new OpenClaw session — the skill loads automatically
```

> **Tip:** Replace the commit SHA with a [release tag](https://github.com/sinkers/voice-agent/releases) once one is available (e.g. `v1.0.0` instead of the SHA).

Replace `<your-agent>` with your agent ID (e.g. `alex`, `main`).

### Option B — Clone the repo and point OpenClaw at it

```bash
git clone https://github.com/sinkers/voice-agent.git ~/voice-agent

# Add to openclaw.json:
# "skills": { "load": { "extraDirs": ["~/voice-agent/web-skill"] } }
```

---

## Using the skill

Once installed, tell your OpenClaw agent:

> "Deploy the voice agent web app"

or

> "Set up the voice web app on Fly.io"

The agent will read the skill and run the setup script, walking you through the full deployment.

You can also run the scripts directly:

```bash
# From the voice-agent repo root:
python3 web-skill/scripts/setup.py         # First-time deploy
python3 web-skill/scripts/deploy.py        # Redeploy after changes
python3 web-skill/scripts/status.py        # Check Fly app + agent workers
python3 web-skill/scripts/call_url.py \
  --agent voice-agent --name "Alex"        # Generate a signed call URL
```

## Prerequisites

See the main [README.md](../README.md#account-setup) for account setup — you'll need:

- [LiveKit Cloud](https://cloud.livekit.io) account (free)
- [Deepgram](https://console.deepgram.com) account (free, $200 credit)
- [OpenAI](https://platform.openai.com) account + billing
- [Fly.io](https://fly.io) account (free tier works)
