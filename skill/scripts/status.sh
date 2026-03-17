#!/usr/bin/env bash
# status.sh — check LiveKit voice agent status
# Usage: status.sh [install_path]

set -euo pipefail

INSTALL_PATH="${1:-$HOME/livekit-voice-agent}"
PID_FILE="$INSTALL_PATH/agent.pid"
LOG_FILE="$INSTALL_PATH/agent.log"

if [ ! -f "$PID_FILE" ]; then
    echo "Voice agent: STOPPED (no PID file)"
    exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    echo "Voice agent: RUNNING (PID $PID)"
    if [ -f "$LOG_FILE" ]; then
        echo ""
        echo "--- Last 5 log lines ---"
        tail -5 "$LOG_FILE"
    fi
else
    echo "Voice agent: STOPPED (stale PID $PID — run start.sh to restart)"
    rm -f "$PID_FILE"
fi
