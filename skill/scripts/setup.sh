#!/usr/bin/env bash
# setup.sh — install and configure the LiveKit voice agent
# Usage: setup.sh [install_path] [agent_id]
# Default install path: ~/livekit-voice-agent

set -euo pipefail

INSTALL_PATH="${1:-$HOME/livekit-voice-agent}"
AGENT_ID="${2:-}"   # optional: pass agent id as second arg, e.g. "main" or "alex"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS_DIR="$SKILL_DIR/assets/agent"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

echo "=== LiveKit Voice Agent Setup ==="
echo "Install path: $INSTALL_PATH"

# Check uv is installed
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv is not installed."
    echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create install directory
mkdir -p "$INSTALL_PATH"

# Copy agent files (idempotent)
echo "Copying agent files..."
cp "$ASSETS_DIR/agent.py" "$INSTALL_PATH/agent.py"
cp "$ASSETS_DIR/pyproject.toml" "$INSTALL_PATH/pyproject.toml"
cp "$ASSETS_DIR/Makefile" "$INSTALL_PATH/Makefile"
# Only copy env.example → .env.example; don't overwrite existing .env
cp "$ASSETS_DIR/env.example" "$INSTALL_PATH/.env.example"

# Set up virtualenv and sync dependencies
echo "Setting up Python environment..."
cd "$INSTALL_PATH"
uv venv --python 3.11
uv sync

# Auto-populate .env from OpenClaw config
ENV_FILE="$INSTALL_PATH/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env from template..."
    cp "$INSTALL_PATH/.env.example" "$ENV_FILE"

    # Read OpenClaw gateway config — single python3 call for efficiency
    GATEWAY_PORT=18789
    GATEWAY_TOKEN=""
    if [ -f "$OPENCLAW_CONFIG" ] && command -v python3 &>/dev/null; then
        OC_VALUES=$(python3 - "$OPENCLAW_CONFIG" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    port = d.get("gateway", {}).get("port", 18789)
    token = d.get("gateway", {}).get("auth", {}).get("token", "")
    agents = [a.get("id","") for a in d.get("agents", {}).get("list", [])]
    agent_list = ",".join(a for a in agents if a)
    print(f"{port} {token} {agent_list}")
except Exception:
    print("18789  ")
PYEOF
)
        GATEWAY_PORT=$(echo "$OC_VALUES" | awk '{print $1}')
        GATEWAY_TOKEN=$(echo "$OC_VALUES" | awk '{print $2}')
        AGENT_LIST=$(echo "$OC_VALUES" | awk '{print $3}')
    fi

    GATEWAY_URL="http://127.0.0.1:${GATEWAY_PORT}/v1"

    # Auto-select agent ID if not provided
    if [ -z "$AGENT_ID" ] && [ -n "${AGENT_LIST:-}" ]; then
        echo ""
        echo "Available OpenClaw agents:"
        echo "$AGENT_LIST" | tr ',' '\n' | nl -w2 -s') '
        echo ""
        read -rp "Which agent should handle voice calls? [main]: " CHOSEN_AGENT
        AGENT_ID="${CHOSEN_AGENT:-main}"
    fi
    AGENT_ID="${AGENT_ID:-main}"

    # Replace placeholder values — use python3 for portable in-place edit
    python3 - "$ENV_FILE" "$GATEWAY_URL" "$GATEWAY_TOKEN" "$AGENT_ID" <<'PYEOF'
import sys, re

env_file, gateway_url, gateway_token, agent_id = sys.argv[1:]

with open(env_file) as f:
    content = f.read()

content = re.sub(r"^OPENCLAW_GATEWAY_URL=.*$", f"OPENCLAW_GATEWAY_URL={gateway_url}", content, flags=re.MULTILINE)
if gateway_token:
    content = re.sub(r"^OPENCLAW_GATEWAY_TOKEN=.*$", f"OPENCLAW_GATEWAY_TOKEN={gateway_token}", content, flags=re.MULTILINE)
content = re.sub(r"^OPENCLAW_AGENT_ID=.*$", f"OPENCLAW_AGENT_ID={agent_id}", content, flags=re.MULTILINE)

with open(env_file, "w") as f:
    f.write(content)
PYEOF

    echo "OpenClaw config applied:"
    echo "  OPENCLAW_GATEWAY_URL=$GATEWAY_URL"
    if [ -n "$GATEWAY_TOKEN" ]; then
        echo "  OPENCLAW_GATEWAY_TOKEN=<set from openclaw.json>"
    else
        echo "  OPENCLAW_GATEWAY_TOKEN=<not found — set manually>"
    fi
    echo "  OPENCLAW_AGENT_ID=$AGENT_ID"
else
    echo ".env already exists — skipping auto-population (edit manually if needed)"
fi

# Download model files
echo "Downloading agent model files..."
_OAI_KEY=$(grep "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
OPENAI_API_KEY="${_OAI_KEY:-stub-key-for-download}" \
uv run python agent.py download-files || echo "Warning: download-files failed — will retry on first start"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "The following values still need to be filled in manually in $ENV_FILE:"
echo ""
echo "  LIVEKIT_URL          — wss://your-project.livekit.cloud"
echo "                         Get from: https://cloud.livekit.io → project settings"
echo "  LIVEKIT_API_KEY      — from LiveKit Cloud project settings"
echo "  LIVEKIT_API_SECRET   — from LiveKit Cloud project settings"
echo "  OPENAI_API_KEY       — from https://platform.openai.com/api-keys"
echo "  DEEPGRAM_API_KEY     — from https://console.deepgram.com (\$200 free credit)"
echo "  OPENCLAW_SESSION_KEY — (optional) pin to a session for shared memory"
echo "                         Tip: ask your agent 'what is your session key?'"
echo ""
echo "Then run: bash scripts/start.sh $INSTALL_PATH"
