#!/usr/bin/env python3
"""start.py — start the LiveKit voice agent.

Usage: python3 start.py [install_path]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PATH = Path.home() / "livekit-voice-agent"


def main() -> None:
    install_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_PATH
    env_file = install_path / ".env"
    pid_file = install_path / "agent.pid"
    log_file = install_path / "agent.log"

    if not install_path.is_dir():
        print(f"ERROR: Install path not found: {install_path}")
        print("Run setup.py first.")
        sys.exit(1)

    if not env_file.exists():
        print(f"ERROR: .env not found at {env_file}")
        print("Run setup.py first.")
        sys.exit(1)

    # Check LIVEKIT_API_KEY is set
    env_vars = dict(
        line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line and not line.startswith("#")
    )
    livekit_key = env_vars.get("LIVEKIT_API_KEY", "").strip().strip('"').strip("'")
    if not livekit_key or livekit_key == "your_livekit_api_key":
        print(f"ERROR: LIVEKIT_API_KEY is not set in {env_file}")
        print("Edit the file and fill in your LiveKit credentials.")
        sys.exit(1)

    # Check if already running
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            print(f"Voice agent is already running (PID {pid}).")
            print("Run stop.py first, or check status.py.")
            sys.exit(0)
        except ProcessLookupError:
            print("Stale PID file found — cleaning up...")
            pid_file.unlink()

    # Start the agent
    print("Starting voice agent...")
    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            ["uv", "run", "python", "agent.py", "dev"],
            cwd=install_path,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    pid_file.write_text(str(proc.pid))
    print(f"Voice agent started (PID {proc.pid}). Logs: {log_file}")
    print("Run python3 scripts/status.py to check it's up.")


if __name__ == "__main__":
    main()
