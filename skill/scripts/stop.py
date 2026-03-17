#!/usr/bin/env python3
"""stop.py — stop the LiveKit voice agent.

Usage: python3 stop.py [install_path]
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

DEFAULT_PATH = Path.home() / "livekit-voice-agent"


def main() -> None:
    install_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_PATH
    pid_file = install_path / "agent.pid"

    if not pid_file.exists():
        print("Voice agent is not running (no PID file found).")
        return

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink()
        print(f"Voice agent stopped (PID {pid}).")
    except ProcessLookupError:
        pid_file.unlink()
        print(f"Voice agent was not running (stale PID {pid}). Cleaned up.")


if __name__ == "__main__":
    main()
