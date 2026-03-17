#!/usr/bin/env bash
# setup.sh — install and configure the LiveKit voice agent
# Usage: setup.sh [install_path]
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

    # Read OpenClaw gateway config
    GATEWAY_PORT=18789
    GATEWAY_TOKEN=""
    if [ -f "$OPENCLAW_CONFIG" ] && command -v python3 &>/dev/null; then
        GATEWAY_PORT=$(python3 -c "
import json, sys
try:
    d = json.load(open('$OPENCLAW_CONFIG'))
    print(d.get('gateway', {}).get('port', 18789))
except: print(18789)
")
        GATEWAY_TOKEN=$(python3 -c "
import json, sys
try:
    d = json.load(open('$OPENCLAW_CONFIG'))
    print(d.get('gateway', {}).get('auth', {}).get('token', ''))
except: print('')
")
    fi

    GATEWAY_URL="http://127.0.0.1:${GATEWAY_PORT}/v1"

    # Auto-select agent ID if not provided
    if [ -z "$AGENT_ID" ] && [ -f "$OPENCLAW_CONFIG" ] && command -v python3 &>/dev/null; then
        AVAILABLE_AGENTS=$(python3 -c "
import json
try:
    d = json.load(open('$OPENCLAW_CONFIG'))
    ids = [a['id'] for a in d.get('agents', {}).get('list', [])]
    print('\n'.join(ids))
except: print('main')
")
        echo ""
        echo "Available OpenClaw agents:"
        echo "$AVAILABLE_AGENTS" | nl -w2 -s') '
        echo ""
        read -rp "Which agent should handle voice calls? [main]: " CHOSEN_AGENT
        AGENT_ID="${CHOSEN_AGENT:-main}"
    fi
    AGENT_ID="${AGENT_ID:-main}"

    # Replace placeholder values with real OpenClaw values
    sed -i "s|OPENCLAW_GATEWAY_URL=.*|OPENCLAW_GATEWAY_URL=$GATEWAY_URL|" "$ENV_FILE"
    if [ -n "$GATEWAY_TOKEN" ]; then
        sed -i "s|OPENCLAW_GATEWAY_TOKEN=.*|OPENCLAW_GATEWAY_TOKEN=$GATEWAY_TOKEN|" "$ENV_FILE"
    fi
    sed -i "s|OPENCLAW_AGENT_ID=.*|OPENCLAW_AGENT_ID=$AGENT_ID|" "$ENV_FILE"

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

# Download model files (done after .env creation so env vars are available)
# agent.py creates the OpenAI client at import time, so we need API keys set.
# Use the .env values, falling back to stubs so download-files can run without real keys.
echo "Downloading agent model files..."
_OAI_KEY=$(grep "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
_OC_TOKEN=$(grep "^OPENCLAW_GATEWAY_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
# If neither key is set, provide stubs so the import doesn't crash (download-files doesn't call APIs)
OPENAI_API_KEY="${_OAI_KEY:-stub-key-for-download}" \
OPENCLAW_GATEWAY_TOKEN="${_OC_TOKEN:-}" \
uv run python agent.py download-files || echo "Warning: download-files failed — model files may need to be downloaded on first start"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "The following values still need to be filled in manually in $ENV_FILE:"
echo ""
echo "  LIVEKIT_URL          — wss://your-project.livekit.cloud"
echo "                         Get from: https://cloud.livekit.io → your project → Settings"
echo "  LIVEKIT_API_KEY      — from LiveKit Cloud project settings"
echo "  LIVEKIT_API_SECRET   — from LiveKit Cloud project settings"
echo "  OPENAI_API_KEY       — from https://platform.openai.com/api-keys"
echo "  DEEPGRAM_API_KEY     — from https://console.deepgram.com (\$200 free credit)"
echo "  OPENCLAW_AGENT_ID    — which OpenClaw agent handles voice calls (auto-set during setup)"
echo "                         To change: re-run setup.sh [path] [agent-id]"
echo "  OPENCLAW_SESSION_KEY — (optional) pin to a session for shared memory"
echo "                         Tip: ask your agent 'what is your session key?'"
echo ""
echo "Then run: scripts/start.sh $INSTALL_PATH"
