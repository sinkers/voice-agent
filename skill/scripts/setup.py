#!/usr/bin/env python3
"""setup.py — install and configure the LiveKit voice agent.

Usage:
    python3 setup.py [install_path] [agent_id]

Defaults:
    install_path: ~/livekit-voice-agent
    agent_id:     (prompted from list of available agents)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
ASSETS_DIR = SKILL_DIR / "assets" / "agent"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def read_openclaw_config() -> dict:
    if not OPENCLAW_CONFIG.exists():
        return {}
    try:
        return json.loads(OPENCLAW_CONFIG.read_text())
    except Exception:
        return {}


def list_agents(config: dict) -> list[str]:
    return [a.get("id", "") for a in config.get("agents", {}).get("list", []) if a.get("id")]


def patch_env(env_file: Path, values: dict[str, str]) -> None:
    """Replace specific key=value lines in .env file."""
    content = env_file.read_text()
    for key, value in values.items():
        content = re.sub(
            rf"^{re.escape(key)}=.*$",
            f"{key}={value}",
            content,
            flags=re.MULTILINE,
        )
    env_file.write_text(content)


def main() -> None:
    install_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "livekit-voice-agent"
    agent_id_arg = sys.argv[2] if len(sys.argv) > 2 else ""

    print("=== LiveKit Voice Agent Setup ===")
    print(f"Install path: {install_path}")

    # Check uv
    if not shutil.which("uv"):
        print("ERROR: uv is not installed.")
        print("Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
        sys.exit(1)

    # Create install directory and copy agent files
    install_path.mkdir(parents=True, exist_ok=True)
    print("Copying agent files...")
    for src in ASSETS_DIR.iterdir():
        dest = install_path / src.name
        shutil.copy2(src, dest)
    # Rename env.example → .env.example
    plain = install_path / "env.example"
    dotted = install_path / ".env.example"
    if plain.exists() and not dotted.exists():
        plain.rename(dotted)
    elif plain.exists():
        plain.unlink()

    # Install dependencies
    print("Setting up Python environment...")
    run(["uv", "venv", "--python", "3.11"], cwd=install_path)
    run(["uv", "sync"], cwd=install_path)

    # Create .env if it doesn't exist
    env_file = install_path / ".env"
    if not env_file.exists():
        print("Creating .env from template...")
        shutil.copy2(install_path / ".env.example", env_file)

        config = read_openclaw_config()
        gateway = config.get("gateway", {})
        port = gateway.get("port", 18789)
        token = gateway.get("auth", {}).get("token", "")
        gateway_url = f"http://127.0.0.1:{port}/v1"
        agents = list_agents(config)

        # Prompt for agent ID if not provided
        agent_id = agent_id_arg
        if not agent_id and agents:
            print("\nAvailable OpenClaw agents:")
            for i, name in enumerate(agents, 1):
                print(f"  {i}) {name}")
            choice = input("\nWhich agent should handle voice calls? [main]: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(agents):
                agent_id = agents[int(choice) - 1]
            else:
                agent_id = choice or "main"
        agent_id = agent_id or "main"

        # Prompt for TTS voice selection
        print("\nAvailable TTS voices:")
        voices = [
            ("alloy", "Neutral, balanced (default)"),
            ("echo", "Male, clear and articulate"),
            ("fable", "British accent, expressive"),
            ("onyx", "Deep male voice, authoritative"),
            ("nova", "Female, energetic and friendly"),
            ("shimmer", "Female, warm and soft"),
        ]
        for i, (voice_id, desc) in enumerate(voices, 1):
            print(f"  {i}) {voice_id:8s} - {desc}")

        voice_choice = input("\nSelect TTS voice [1-6, default: 1 (alloy)]: ").strip()
        tts_voice = "alloy"
        if voice_choice.isdigit() and 1 <= int(voice_choice) <= len(voices):
            tts_voice = voices[int(voice_choice) - 1][0]

        # Patch .env with auto-detected values
        updates: dict[str, str] = {"OPENCLAW_GATEWAY_URL": gateway_url}
        if token:
            updates["OPENCLAW_GATEWAY_TOKEN"] = token
        updates["OPENCLAW_AGENT_ID"] = agent_id
        updates["OPENAI_TTS_VOICE"] = tts_voice
        patch_env(env_file, updates)

        print("\nOpenClaw config applied:")
        print(f"  OPENCLAW_GATEWAY_URL={gateway_url}")
        print(f"  OPENCLAW_GATEWAY_TOKEN={'<set from openclaw.json>' if token else '<not found — set manually>'}")
        print(f"  OPENCLAW_AGENT_ID={agent_id}")
        print(f"  OPENAI_TTS_VOICE={tts_voice}")
    else:
        print(".env already exists — skipping auto-population (edit manually if needed)")

    # Download model files
    print("Downloading agent model files...")
    env = os.environ.copy()
    if not env.get("OPENAI_API_KEY"):
        env["OPENAI_API_KEY"] = "stub-key-for-download"
    result = subprocess.run(["uv", "run", "python", "agent.py", "download-files"], cwd=install_path, env=env)
    if result.returncode != 0:
        print("Warning: download-files failed — model files will be downloaded on first start")

    print(f"""
=== Setup complete! ===

Fill in the following values in {env_file}:

  LIVEKIT_URL         — wss://your-project.livekit.cloud
                        Get from: https://cloud.livekit.io → project settings
  LIVEKIT_API_KEY     — from LiveKit Cloud project settings
  LIVEKIT_API_SECRET  — from LiveKit Cloud project settings
  OPENAI_API_KEY      — from https://platform.openai.com/api-keys
  DEEPGRAM_API_KEY    — from https://console.deepgram.com ($200 free credit)
  OPENCLAW_SESSION_KEY (optional) — pin to a session for shared memory
                        Tip: ask your agent "what is your session key?"

Then run: python3 scripts/start.py {install_path}
""")


if __name__ == "__main__":
    main()
