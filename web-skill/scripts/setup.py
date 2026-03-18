#!/usr/bin/env python3
"""
livekit-voice-web setup script.

Walks the user through deploying the voice agent web app to Fly.io:
  1. Check / install prerequisites
  2. Fly.io login
  3. App name
  4. LiveKit credentials
  5. Generate CONFIG_SECRET
  6. Set Fly secrets
  7. Build + deploy
  8. Print call URL

Usage:
    python3 web-skill/scripts/setup.py [--update-secrets]
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from utils import (
    BOLD, GREEN, YELLOW, RESET,
    h, ok, warn, err, prompt,
    fly, fly_authenticated, fly_app_exists, install_flyctl,
    read_app_name, read_env_file, write_env_value,
    tmp_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_node() -> bool:
    result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        return False
    version = result.stdout.strip().lstrip("v")
    try:
        return int(version.split(".")[0]) >= 18
    except ValueError:
        return False


def _set_fly_secrets(
    app_name: str,
    livekit_url: str,
    livekit_api_key: str,
    livekit_api_secret: str,
    config_secret: str,
    cors_origins: str,
) -> None:
    fly(
        "secrets", "set",
        "--app", app_name,
        f"LIVEKIT_URL={livekit_url}",
        f"LIVEKIT_API_KEY={livekit_api_key}",
        f"LIVEKIT_API_SECRET={livekit_api_secret}",
        f"CONFIG_SECRET={config_secret}",
        f"CORS_ORIGINS={cors_origins}",
    )
    print(ok("Fly secrets set"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(update_secrets_only: bool = False) -> None:
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    web_dir = repo_root / "web"
    env_path = repo_root / ".env"

    print(textwrap.dedent(f"""
    {BOLD}╔══════════════════════════════════════════════════╗
    ║   LiveKit Voice Web — Fly.io Setup               ║
    ╚══════════════════════════════════════════════════╝{RESET}

    This script will deploy the voice agent web app to Fly.io.
    You'll need:
      • A Fly.io account  (https://fly.io/app/sign-up)
      • A LiveKit Cloud project  (https://cloud.livekit.io)
      • Node.js ≥ 18

    Press Ctrl-C at any time to abort.
    """))

    # ------------------------------------------------------------------
    # 1. Prerequisites
    # ------------------------------------------------------------------
    print(h("Checking prerequisites"))

    if check_node():
        print(ok("Node.js ≥ 18 found"))
    else:
        print(err("Node.js ≥ 18 is required to build the frontend."))
        print("  Install from: https://nodejs.org/")
        sys.exit(1)

    if shutil.which("fly") or shutil.which("flyctl"):
        print(ok("flyctl found"))
    else:
        if not install_flyctl():
            sys.exit(1)
        print(ok("flyctl installed"))

    # ------------------------------------------------------------------
    # 2. Fly.io auth
    # ------------------------------------------------------------------
    print(h("Fly.io authentication"))

    if fly_authenticated():
        result = fly("auth", "whoami", capture=True)
        print(ok(f"Logged in as: {result.stdout.strip()}"))
    else:
        print("  Opening Fly.io login...")
        fly("auth", "login")
        if not fly_authenticated():
            print(err("Login failed. Run 'fly auth login' manually and retry."))
            sys.exit(1)
        print(ok("Logged in"))

    # ------------------------------------------------------------------
    # 3. App name
    # ------------------------------------------------------------------
    print(h("Fly.io app configuration"))

    existing_env = read_env_file(env_path)
    existing_url = existing_env.get("CALL_BASE_URL", "")
    fly_toml = web_dir / "fly.toml"
    toml_app = read_app_name(fly_toml)

    default_app = (
        toml_app
        or (existing_url.replace("https://", "").replace(".fly.dev", "") if existing_url else "")
        or "voice-agent-web"
    )

    app_name = prompt("Fly app name", default_app)
    call_base_url = f"https://{app_name}.fly.dev"

    _app_exists = fly_app_exists(app_name)
    if _app_exists:
        print(ok(f"App '{app_name}' already exists — will redeploy"))
        print(warn("If another OpenClaw instance deployed this app, use the same CONFIG_SECRET"))
        print("  so URLs generated on any machine work against the same backend.")
    else:
        print(f"  Will create new app: {BOLD}{app_name}{RESET}")

    # ------------------------------------------------------------------
    # 4. LiveKit credentials
    # ------------------------------------------------------------------
    print(h("LiveKit credentials"))
    print("  Find these at: https://cloud.livekit.io → your project → Settings\n")

    livekit_url = prompt("LiveKit URL (wss://...)", existing_env.get("LIVEKIT_URL", ""))
    livekit_api_key = prompt("LiveKit API key", existing_env.get("LIVEKIT_API_KEY", ""))
    livekit_api_secret = prompt("LiveKit API secret", existing_env.get("LIVEKIT_API_SECRET", ""))

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        print(err("All LiveKit credentials are required."))
        sys.exit(1)

    # ------------------------------------------------------------------
    # 5. CONFIG_SECRET
    # ------------------------------------------------------------------
    print(h("Signing secret (CONFIG_SECRET)"))

    existing_secret = existing_env.get("CONFIG_SECRET", "")
    if existing_secret and not update_secrets_only:
        print(ok("Reusing existing CONFIG_SECRET from .env"))
        config_secret = existing_secret
    else:
        if _app_exists:
            print(warn("App already exists on Fly.io."))
            print("  If another machine deployed this app, enter its CONFIG_SECRET to share the backend.")
            print("  Leave blank to generate a new one (existing URLs on other machines will break).")
            shared_secret = prompt("CONFIG_SECRET (leave blank to generate new)", "").strip()
            if shared_secret:
                config_secret = shared_secret
                print(ok("Using provided CONFIG_SECRET"))
            else:
                config_secret = secrets.token_hex(32)
                print(ok(f"Generated new CONFIG_SECRET: {config_secret[:8]}..."))
        else:
            config_secret = secrets.token_hex(32)
            print(ok(f"Generated new CONFIG_SECRET: {config_secret[:8]}..."))

    # ------------------------------------------------------------------
    # 6. CORS origins
    # ------------------------------------------------------------------
    cors_origins = prompt(
        "Allowed CORS origins (comma-separated, or * for all)",
        existing_env.get("CORS_ORIGINS", "*"),
    )

    # ------------------------------------------------------------------
    # 7. Write .env on agent host
    # ------------------------------------------------------------------
    print(h("Updating local .env"))
    for key, value in [
        ("LIVEKIT_URL", livekit_url),
        ("LIVEKIT_API_KEY", livekit_api_key),
        ("LIVEKIT_API_SECRET", livekit_api_secret),
        ("CONFIG_SECRET", config_secret),
        ("CALL_BASE_URL", call_base_url),
    ]:
        write_env_value(env_path, key, value)
    print(ok(f".env updated at {env_path}"))

    if update_secrets_only:
        print(h("Updating Fly secrets only"))
        _set_fly_secrets(app_name, livekit_url, livekit_api_key, livekit_api_secret, config_secret, cors_origins)
        print(ok("Fly secrets updated. No redeploy triggered."))
        return

    # ------------------------------------------------------------------
    # 8. Create Fly app if needed
    # ------------------------------------------------------------------
    print(h("Creating Fly app"))
    if not fly_app_exists(app_name):
        fly("apps", "create", app_name)
        print(ok(f"App '{app_name}' created"))

        # Update fly.toml app name
        if fly_toml.exists():
            lines = [
                f'app = "{app_name}"' if line.strip().startswith("app =") else line
                for line in fly_toml.read_text().splitlines()
            ]
            fly_toml.write_text("\n".join(lines) + "\n")
            print(ok("fly.toml updated"))
    else:
        print(ok(f"App '{app_name}' already exists"))

    # ------------------------------------------------------------------
    # 9. Set Fly secrets
    # ------------------------------------------------------------------
    print(h("Setting Fly secrets"))
    _set_fly_secrets(app_name, livekit_url, livekit_api_key, livekit_api_secret, config_secret, cors_origins)

    # ------------------------------------------------------------------
    # 10. Ensure package-lock.json exists (required for npm ci in Dockerfile)
    # ------------------------------------------------------------------
    frontend_dir = web_dir / "frontend"
    if not (frontend_dir / "package-lock.json").exists():
        print(h("Generating package-lock.json"))
        subprocess.run(["npm", "install", "--package-lock-only"], cwd=frontend_dir, check=True)
        print(ok("package-lock.json generated"))

    # ------------------------------------------------------------------
    # 11. Deploy
    # ------------------------------------------------------------------
    print(h("Deploying to Fly.io"))
    print("  This will take 2–5 minutes (building Docker image remotely)...\n")
    fly("deploy", "--remote-only", "--app", app_name, cwd=web_dir)

    # ------------------------------------------------------------------
    # 12. Start the agent worker
    # ------------------------------------------------------------------
    print(h("Starting agent worker"))

    agent_script = repo_root / "agent.py"
    if not agent_script.exists():
        print(warn(f"agent.py not found at {agent_script} — skipping worker start."))
        print(warn("Start it manually: python agent.py start"))
        call_url = None
    else:
        _WORKER_REGISTER_TIMEOUT = 30
        log_file = tmp_dir() / f"agent-{os.getenv('OPENCLAW_AGENT_NAME', 'voice-agent')}.log"
        agent_env = os.environ.copy()
        proc = subprocess.Popen(
            [sys.executable, str(agent_script), "start"],
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            cwd=repo_root,
            env=agent_env,
        )
        print(ok(f"Agent worker started (PID {proc.pid}), logging to {log_file}"))
        print("  Waiting for worker to register with LiveKit Cloud...")

        # Poll log for 'registered worker' or URL line (up to _WORKER_REGISTER_TIMEOUT seconds)
        call_url = None
        for _ in range(_WORKER_REGISTER_TIMEOUT):
            time.sleep(1)
            try:
                log_text = log_file.read_text()
            except OSError:
                continue
            if "registered worker" in log_text or "[agent] Call URL" in log_text:
                for line in log_text.splitlines():
                    if "[agent] Call URL" in line:
                        call_url = line.split("Call URL (24h): ", 1)[-1].strip()
                break
        else:
            print(warn(f"Worker didn't register within {_WORKER_REGISTER_TIMEOUT}s — check the log:"))
            print(f"  tail -f {log_file}")

        if call_url:
            print(ok("Worker registered successfully"))

    # ------------------------------------------------------------------
    # 13. Done
    # ------------------------------------------------------------------
    call_url_section = (
        f"\n    {BOLD}Your call URL (valid 24h):{RESET}\n\n    {call_url}\n"
        if call_url
        else f"\n    {warn('Generate a call URL once the worker is running:')}\n\n"
             f"    python3 web-skill/scripts/call_url.py --agent voice-agent --name \"Your Name\"\n"
    )

    print(textwrap.dedent(f"""
    {BOLD}{GREEN}
    ╔══════════════════════════════════════════════════╗
    ║   Setup complete!                                ║
    ╚══════════════════════════════════════════════════╝{RESET}

    {ok(f'Web app: {BOLD}{call_base_url}{RESET}')}
    {call_url_section}
    To generate a new call URL at any time:

      python3 web-skill/scripts/call_url.py --agent voice-agent --name "Your Name"

    {warn('Keep the agent worker running — calls will not connect without it.')}
    """))


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy voice agent web app to Fly.io")
    parser.add_argument(
        "--update-secrets",
        action="store_true",
        help="Re-prompt for credentials and update Fly secrets without redeploying",
    )
    args = parser.parse_args()
    main(update_secrets_only=args.update_secrets)
