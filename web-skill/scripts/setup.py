#!/usr/bin/env python3
"""
livekit-voice-web setup script.

Walks the user through deploying the voice agent web app to Fly.io:
  1. Check / install prerequisites
  2. Fly.io login
  3. App name + region
  4. LiveKit credentials
  5. Generate CONFIG_SECRET
  6. Set Fly secrets
  7. Build + deploy
  8. Print call URL

Usage:
    python3 scripts/setup.py [--update-secrets]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def h(text: str) -> str:
    return f"\n{BOLD}{CYAN}==> {text}{RESET}"


def ok(text: str) -> str:
    return f"{GREEN}✓{RESET} {text}"


def warn(text: str) -> str:
    return f"{YELLOW}⚠{RESET}  {text}"


def err(text: str) -> str:
    return f"{RED}✗{RESET}  {text}"


def prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{BOLD}{question}{suffix}: {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(1)
    return answer or default


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def run_check(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def fly(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    fly_bin = shutil.which("fly") or shutil.which("flyctl") or _fly_path()
    cmd = [fly_bin, *args]
    if capture:
        return run(cmd, capture_output=True, text=True)
    return run_check(cmd)


def _fly_path() -> str:
    # Default install location on Linux/macOS
    home = Path.home()
    candidates = [
        home / ".fly" / "bin" / "fly",
        home / ".fly" / "bin" / "flyctl",
        Path("/usr/local/bin/fly"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return "fly"  # Will fail with a clear error


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

def check_node() -> bool:
    result = run(["node", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        return False
    version = result.stdout.strip().lstrip("v")
    major = int(version.split(".")[0])
    return major >= 18


def install_flyctl() -> bool:
    """Install flyctl via the official install script."""
    print(warn("flyctl not found. Installing..."))
    system = platform.system().lower()
    if system in ("linux", "darwin"):
        result = run(
            ["sh", "-c", "curl -L https://fly.io/install.sh | sh"],
        )
        return result.returncode == 0
    else:
        print(err("Automatic flyctl install not supported on Windows."))
        print("  Install manually: https://fly.io/docs/hands-on/install-flyctl/")
        return False


def fly_authenticated() -> bool:
    result = fly("auth", "whoami", capture=True)
    return result.returncode == 0


def fly_app_exists(app_name: str) -> bool:
    result = fly("apps", "list", capture=True)
    return app_name in result.stdout


def read_env_file(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def write_env_value(env_path: Path, key: str, value: str) -> None:
    """Set or update a key in a .env file."""
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n")


# ---------------------------------------------------------------------------
# Main setup
# ---------------------------------------------------------------------------

def main(update_secrets_only: bool = False) -> None:
    # Locate the repo root (this script lives in web-skill/scripts/)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    web_dir = repo_root / "web"
    env_path = repo_root / ".env"

    print(textwrap.dedent(f"""
    {BOLD}{CYAN}╔══════════════════════════════════════════════════╗
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

    # Node.js
    if check_node():
        print(ok("Node.js ≥ 18 found"))
    else:
        print(err("Node.js ≥ 18 is required to build the frontend."))
        print("  Install from: https://nodejs.org/")
        sys.exit(1)

    # flyctl
    if shutil.which("fly") or shutil.which("flyctl") or Path.home().joinpath(".fly/bin/fly").exists():
        print(ok("flyctl found"))
    else:
        if not install_flyctl():
            sys.exit(1)
        # Add to PATH for this session
        fly_bin_dir = Path.home() / ".fly" / "bin"
        os.environ["PATH"] = f"{fly_bin_dir}:{os.environ['PATH']}"
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
            print(err("Login failed. Please run 'fly auth login' manually."))
            sys.exit(1)
        print(ok("Logged in"))

    # ------------------------------------------------------------------
    # 3. App name
    # ------------------------------------------------------------------
    print(h("Fly.io app configuration"))

    existing_env = read_env_file(env_path)
    existing_url = existing_env.get("CALL_BASE_URL", "")
    default_app = "voice-agent-web"
    if existing_url:
        # Extract app name from existing URL if possible
        default_app = existing_url.replace("https://", "").replace(".fly.dev", "") or default_app

    app_name = prompt("Fly app name", default_app)
    call_base_url = f"https://{app_name}.fly.dev"

    if fly_app_exists(app_name):
        print(ok(f"App '{app_name}' already exists — will redeploy"))
    else:
        print(f"  Will create new app: {BOLD}{app_name}{RESET}")

    # ------------------------------------------------------------------
    # 4. LiveKit credentials
    # ------------------------------------------------------------------
    print(h("LiveKit credentials"))
    print("  Find these at: https://cloud.livekit.io → your project → Settings")
    print()

    livekit_url = prompt(
        "LiveKit URL (wss://...)",
        existing_env.get("LIVEKIT_URL", ""),
    )
    livekit_api_key = prompt(
        "LiveKit API key",
        existing_env.get("LIVEKIT_API_KEY", ""),
    )
    livekit_api_secret = prompt(
        "LiveKit API secret",
        existing_env.get("LIVEKIT_API_SECRET", ""),
    )

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        print(err("All LiveKit credentials are required."))
        sys.exit(1)

    # ------------------------------------------------------------------
    # 5. CONFIG_SECRET
    # ------------------------------------------------------------------
    print(h("Signing secret (CONFIG_SECRET)"))

    existing_secret = existing_env.get("CONFIG_SECRET", "")
    if existing_secret and not update_secrets_only:
        print(ok("Using existing CONFIG_SECRET from .env"))
        config_secret = existing_secret
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

        # Write fly.toml with app name
        fly_toml = web_dir / "fly.toml"
        toml_content = fly_toml.read_text() if fly_toml.exists() else ""
        if "app = " in toml_content:
            lines = [
                f'app = "{app_name}"' if line.startswith("app =") else line
                for line in toml_content.splitlines()
            ]
            fly_toml.write_text("\n".join(lines) + "\n")
        print(ok("fly.toml updated with app name"))
    else:
        print(ok(f"App '{app_name}' already exists"))

    # ------------------------------------------------------------------
    # 9. Set Fly secrets
    # ------------------------------------------------------------------
    print(h("Setting Fly secrets"))
    _set_fly_secrets(app_name, livekit_url, livekit_api_key, livekit_api_secret, config_secret, cors_origins)

    # ------------------------------------------------------------------
    # 10. Build package-lock.json if missing (required for npm ci)
    # ------------------------------------------------------------------
    frontend_dir = web_dir / "frontend"
    lockfile = frontend_dir / "package-lock.json"
    if not lockfile.exists():
        print(h("Generating package-lock.json"))
        run_check(["npm", "install", "--package-lock-only"], cwd=frontend_dir)
        print(ok("package-lock.json generated"))

    # ------------------------------------------------------------------
    # 11. Deploy
    # ------------------------------------------------------------------
    print(h("Deploying to Fly.io"))
    print("  This will take 2–5 minutes (building Docker image remotely)...\n")
    fly("deploy", "--remote-only", "--app", app_name)

    # ------------------------------------------------------------------
    # 12. Done
    # ------------------------------------------------------------------
    print(textwrap.dedent(f"""
    {BOLD}{GREEN}
    ╔══════════════════════════════════════════════════╗
    ║   Deployment complete!                           ║
    ╚══════════════════════════════════════════════════╝{RESET}

    {ok(f'Web app: {BOLD}{call_base_url}{RESET}')}

    {BOLD}Next steps:{RESET}

    1. Start your agent worker on this machine:

         python agent.py start

    2. Generate a call URL:

         python generate_call_url.py --agent voice-agent --name "Your Name"

    3. Open the URL in a browser and make a call.

    {warn('The agent worker must be running for calls to connect.')}
    """))


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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy voice agent web app to Fly.io")
    parser.add_argument(
        "--update-secrets",
        action="store_true",
        help="Re-prompt for credentials and update Fly secrets without redeploying",
    )
    args = parser.parse_args()
    main(update_secrets_only=args.update_secrets)
