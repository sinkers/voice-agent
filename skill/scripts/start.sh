#!/usr/bin/env bash
# start.sh — start the LiveKit voice agent
# Usage: start.sh [install_path]
# Default install path: ~/livekit-voice-agent

set -euo pipefail

INSTALL_PATH="${1:-$HOME/livekit-voice-agent}"
ENV_FILE="$INSTALL_PATH/.env"
PID_FILE="$INSTALL_PATH/agent.pid"
LOG_FILE="$INSTALL_PATH/agent.log"

# Check install path exists
if [ ! -d "$INSTALL_PATH" ]; then
    echo "ERROR: Install path not found: $INSTALL_PATH"
    echo "Run setup.sh first."
    exit 1
fi

# Check .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env not found at $ENV_FILE"
    echo "Run setup.sh first."
    exit 1
fi

# Check LIVEKIT_API_KEY is not a placeholder
LIVEKIT_KEY=$(grep "^LIVEKIT_API_KEY=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "$LIVEKIT_KEY" ] || [ "$LIVEKIT_KEY" = "your_livekit_api_key" ]; then
    echo "ERROR: LIVEKIT_API_KEY is not set in $ENV_FILE"
    echo "Edit $ENV_FILE and fill in your LiveKit credentials."
    exit 1
fi

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Voice agent is already running (PID $OLD_PID)."
        echo "Run stop.sh first, or check status.sh."
        exit 0
    else
        echo "Stale PID file found — cleaning up..."
        rm -f "$PID_FILE"
    fi
fi

# Start the agent
echo "Starting voice agent..."
cd "$INSTALL_PATH"
# shellcheck disable=SC1091
source .venv/bin/activate
nohup python agent.py dev > "$LOG_FILE" 2>&1 &
PID=$!

echo "$PID" > "$PID_FILE"
echo "Voice agent started (PID $PID). Logs: $LOG_FILE"
echo "Run scripts/status.sh to check it's up."
