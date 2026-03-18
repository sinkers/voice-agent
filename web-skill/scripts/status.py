#!/usr/bin/env python3
"""Show status of the Fly.io deployment and running agent workers."""

from __future__ import annotations

from pathlib import Path

from utils import fly, read_app_name, find_agent_processes, tmp_dir


def main() -> None:
    script_dir = Path(__file__).parent
    web_dir = script_dir.parent.parent / "web"

    app_name = read_app_name(web_dir / "fly.toml") or "voice-agent-web"

    print(f"\n── Fly.io app: {app_name} ──")
    result = fly("status", "--app", app_name, capture=True)
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"  (Could not reach Fly.io: {result.stderr.strip()})")

    print("── Agent workers ──")
    processes = find_agent_processes()
    if processes:
        for line in processes:
            print(f"  running: {line}")
    else:
        print("  No agent workers running.")

    print("\n── Recent agent logs ──")
    for log_file in sorted(tmp_dir().glob("agent*.log")):
        print(f"\n  {log_file}:")
        lines = log_file.read_text().splitlines()
        for line in lines[-5:]:
            print(f"    {line}")


if __name__ == "__main__":
    main()
