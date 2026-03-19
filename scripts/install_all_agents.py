#!/usr/bin/env python3
"""Install and configure voice agent workers for all OpenClaw agents.

Run from the livekit-agent repo dir:
    python3 scripts/install_all_agents.py

Each agent gets its own install dir at ~/livekit-voice-{id}/ with
the correct credentials, display name, greeting, and HTTP port.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent
SKILL_SETUP = REPO_DIR / "skill" / "scripts" / "setup.py"

# OpenClaw Gateway config (credentials pulled from hub at startup — not stored in .env)
SHARED = {
    "OPENCLAW_GATEWAY_URL": "http://127.0.0.1:18789/v1",
    "OPENCLAW_GATEWAY_TOKEN": "f595d5d394f820cd5bb8fc899c2072bc418eb387d1db3d8e",
}

# Per-agent config: (openclaw_agent_id, display_name, greeting, http_port, session_key)
AGENTS = [
    ("main",   "Clive",  "Hey, it's Clive. Go ahead.",   8081, ""),
    ("alex",   "Alex",   "Hey, it's Alex. Go ahead.",    8082, "agent:alex:telegram:direct:6946974355"),
    ("elysse", "Elysse", "Hi, Elysse here. Go ahead.",   8083, ""),
    ("colin",  "Colin",  "Hey, Colin here. What's up?",  8084, ""),
    ("mandy",  "Mandy",  "Hi, this is Mandy. Go ahead.", 8085, ""),
    ("moxie",  "Moxie",  "Hey, Moxie here. Go ahead.",   8086, ""),
]


def patch_env(env_file: Path, values: dict) -> None:
    content = env_file.read_text()
    for key, value in values.items():
        if re.search(rf"^{re.escape(key)}=", content, re.MULTILINE):
            content = re.sub(
                rf"^{re.escape(key)}=.*$",
                f"{key}={value}",
                content,
                flags=re.MULTILINE,
            )
        else:
            content += f"\n{key}={value}"
    env_file.write_text(content)


def install_agent(agent_id: str, display_name: str, greeting: str, port: int, session_key: str) -> Path:
    install_path = Path.home() / f"livekit-voice-{agent_id}"
    print(f"\n{'='*60}")
    print(f"  Installing: {display_name} ({agent_id}) → {install_path}")
    print(f"{'='*60}")

    if install_path.exists():
        print(f"  Dir exists — reinstalling (removing old install)...")
        shutil.rmtree(install_path)

    # Run setup.py (copies files, creates venv, creates .env from template)
    result = subprocess.run(
        [sys.executable, str(SKILL_SETUP), str(install_path), agent_id],
        # Pass a dummy OpenClaw config path so setup doesn't prompt
        env={**os.environ, "OPENCLAW_CONFIG_SKIP_PROMPT": "1"},
    )
    if result.returncode != 0:
        print(f"  ERROR: setup.py failed for {agent_id}")
        sys.exit(1)

    # Patch .env with real credentials + per-agent settings
    env_file = install_path / ".env"
    # Hosted mode: credentials come from the hub at startup.
    # Only write OpenClaw-specific and per-agent settings.
    HOSTED_KEYS = {
        "OPENCLAW_GATEWAY_URL",
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENCLAW_AGENT_ID",
        "OPENCLAW_AGENT_NAME",
        "OPENCLAW_AGENT_DISPLAY_NAME",
        "AGENT_GREETING",
        "AGENT_HTTP_PORT",
        "HUB_URL",
        "OPENCLAW_SESSION_KEY",
    }
    env_file.write_text(
        "# Voice agent config — hosted mode (credentials pulled from hub at startup)\n"
        "# Only OpenClaw-specific and per-agent settings needed here.\n\n"
    )
    updates = {
        "OPENCLAW_GATEWAY_URL": SHARED["OPENCLAW_GATEWAY_URL"],
        "OPENCLAW_GATEWAY_TOKEN": SHARED["OPENCLAW_GATEWAY_TOKEN"],
        "OPENCLAW_AGENT_ID": agent_id,
        "OPENCLAW_AGENT_NAME": f"voice-{agent_id}",
        "OPENCLAW_AGENT_DISPLAY_NAME": display_name,
        "AGENT_GREETING": greeting,
        "AGENT_HTTP_PORT": str(port),
    }
    if session_key:
        updates["OPENCLAW_SESSION_KEY"] = session_key
    patch_env(env_file, updates)
    print(f"  ✓ Credentials patched")

    return install_path


def start_agent(install_path: Path, agent_id: str) -> None:
    start_script = REPO_DIR / "skill" / "scripts" / "start.py"
    result = subprocess.run([sys.executable, str(start_script), str(install_path)])
    if result.returncode != 0:
        print(f"  WARNING: start.py returned non-zero for {agent_id} — check logs")


def main() -> None:
    print("LiveKit Voice Agent — Multi-Agent Install")
    print(f"Repo: {REPO_DIR}")
    print(f"Agents: {len(AGENTS)}")

    if not SKILL_SETUP.exists():
        print(f"ERROR: setup.py not found at {SKILL_SETUP}")
        sys.exit(1)

    installed = []
    for agent_id, display_name, greeting, port, session_key in AGENTS:
        install_path = install_agent(agent_id, display_name, greeting, port, session_key)
        installed.append((agent_id, display_name, install_path))

    print(f"\n{'='*60}")
    print("  All agents installed. Starting workers...")
    print(f"{'='*60}\n")

    for agent_id, display_name, install_path in installed:
        print(f"Starting {display_name} ({agent_id})...")
        start_agent(install_path, agent_id)

    print(f"\n{'='*60}")
    print("  Install complete!")
    print(f"{'='*60}")
    print()
    print("Each agent will register with the hub and print its Call URL to its log.")
    print("Logs are at ~/livekit-voice-<id>/agent.log")
    print()
    print("To check call URLs:")
    for agent_id, display_name, install_path in installed:
        print(f"  {display_name:8} → grep 'Call URL' {install_path}/agent.log")
    print()
    print("To check status of all agents:")
    print("  for d in ~/livekit-voice-*/; do echo \"=== $d ===\"; python3 "
          f"{REPO_DIR}/skill/scripts/status.py \"$d\"; done")


if __name__ == "__main__":
    main()
