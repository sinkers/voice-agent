#!/usr/bin/env python3
"""status.py — check LiveKit voice agent status.

Usage: python3 status.py [install_path]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_PATH = Path.home() / "livekit-voice-agent"


def main() -> None:
    install_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_PATH
    pid_file = install_path / "agent.pid"
    log_file = install_path / "agent.log"

    if not pid_file.exists():
        print("Voice agent: STOPPED (no PID file)")
        return

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, 0)
        print(f"Voice agent: RUNNING (PID {pid})")
        if log_file.exists():
            lines = log_file.read_text().splitlines()
            if lines:
                print("\n--- Last 5 log lines ---")
                print("\n".join(lines[-5:]))
    except ProcessLookupError:
        pid_file.unlink()
        print(f"Voice agent: STOPPED (stale PID {pid} — run start.py to restart)")


if __name__ == "__main__":
    main()
