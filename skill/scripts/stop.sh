#!/usr/bin/env bash
# stop.sh — stop the LiveKit voice agent
# Usage: stop.sh [install_path]

set -euo pipefail

INSTALL_PATH="${1:-$HOME/livekit-voice-agent}"
PID_FILE="$INSTALL_PATH/agent.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "Voice agent is not running (no PID file found)."
    exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    rm -f "$PID_FILE"
    echo "Voice agent stopped (PID $PID)."
else
    echo "Voice agent was not running (stale PID $PID). Cleaned up."
    rm -f "$PID_FILE"
fi
