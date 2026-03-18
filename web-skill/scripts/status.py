#!/usr/bin/env python3
"""Show status of the Fly.io deployment and running agent workers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def fly_bin() -> str:
    for candidate in ["fly", "flyctl", str(Path.home() / ".fly" / "bin" / "fly")]:
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    return "fly"


def main() -> None:
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    web_dir = repo_root / "web"

    # App name from fly.toml
    fly_toml = web_dir / "fly.toml"
    app_name = "voice-agent-web"
    if fly_toml.exists():
        for line in fly_toml.read_text().splitlines():
            if line.startswith("app ="):
                app_name = line.split("=", 1)[1].strip().strip('"')
                break

    print(f"\n── Fly.io app: {app_name} ──")
    result = subprocess.run(
        [fly_bin(), "status", "--app", app_name],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"  (Could not reach Fly.io: {result.stderr.strip()})")

    print("── Agent workers ──")
    ps_result = subprocess.run(
        ["pgrep", "-af", "python agent.py"],
        capture_output=True, text=True,
    )
    if ps_result.returncode == 0 and ps_result.stdout.strip():
        for line in ps_result.stdout.strip().splitlines():
            print(f"  running: {line}")
    else:
        print("  No agent workers running.")

    print("\n── Recent agent logs ──")
    for log_file in sorted(Path("/tmp").glob("agent*.log")):
        print(f"\n  {log_file}:")
        lines = log_file.read_text().splitlines()
        for line in lines[-5:]:
            print(f"    {line}")


if __name__ == "__main__":
    main()
