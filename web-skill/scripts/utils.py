"""Shared utilities for livekit-voice-web skill scripts."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Console colours
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


# ---------------------------------------------------------------------------
# flyctl
# ---------------------------------------------------------------------------

def fly_bin() -> str:
    """Return the path to flyctl, or 'fly' as a fallback."""
    for candidate in ["fly", "flyctl"]:
        if shutil.which(candidate):
            return candidate
    home = Path.home()
    for p in [home / ".fly" / "bin" / "fly", home / ".fly" / "bin" / "flyctl"]:
        if p.exists():
            return str(p)
    return "fly"


def fly(*args: str, capture: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [fly_bin(), *args]
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return subprocess.run(cmd, check=True, cwd=cwd)


def fly_authenticated() -> bool:
    return fly("auth", "whoami", capture=True).returncode == 0


def fly_app_exists(app_name: str) -> bool:
    """Return True only if app_name exactly matches a listed Fly app."""
    result = fly("apps", "list", capture=True)
    for line in result.stdout.splitlines():
        # 'fly apps list' output: columns separated by whitespace; first col is the app name
        cols = line.split()
        if cols and cols[0] == app_name:
            return True
    return False


# ---------------------------------------------------------------------------
# fly.toml parsing
# ---------------------------------------------------------------------------

def read_app_name(fly_toml: Path) -> str | None:
    """Read the app name from fly.toml using tomllib (Python 3.11+) or line scan."""
    if not fly_toml.exists():
        return None
    if tomllib is not None:
        try:
            with open(fly_toml, "rb") as f:
                data = tomllib.load(f)
            return data.get("app")
        except Exception:
            pass
    # Fallback: line scan
    for line in fly_toml.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("app") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"\'')
    return None


# ---------------------------------------------------------------------------
# .env file helpers
# ---------------------------------------------------------------------------

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
    """Set or update a key in a .env file (creates if absent)."""
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updated = False
    new_lines = []
    for line in lines:
        k = line.split("=", 1)[0].strip()
        if k == key:
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n")


# ---------------------------------------------------------------------------
# Portable tmp dir
# ---------------------------------------------------------------------------

def tmp_dir() -> Path:
    return Path(tempfile.gettempdir())


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

def find_agent_processes() -> list[str]:
    """Return a list of running agent.py process descriptions (cross-platform)."""
    system = platform.system().lower()
    if system in ("linux", "darwin"):
        result = subprocess.run(
            ["pgrep", "-af", "python agent.py"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()
    else:
        # Windows / other: try psutil if available
        try:
            import psutil
            matches = []
            for proc in psutil.process_iter(["pid", "cmdline"]):
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "agent.py" in cmdline:
                    matches.append(f"{proc.pid} {cmdline}")
            return matches
        except ImportError:
            pass
    return []


# ---------------------------------------------------------------------------
# flyctl install
# ---------------------------------------------------------------------------

def install_flyctl() -> bool:
    """Install flyctl via the official install script (Linux/macOS only)."""
    system = platform.system().lower()
    if system not in ("linux", "darwin"):
        print(err("Automatic flyctl install is not supported on this OS."))
        print("  Install manually: https://fly.io/docs/hands-on/install-flyctl/")
        return False

    print(warn("flyctl not found. Installing via official script..."))
    print(warn("Review the install script at: https://fly.io/install.sh"))
    try:
        confirm = input("  Proceed with install? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return False

    if confirm != "y":
        print("  Skipped. Install flyctl manually: https://fly.io/docs/hands-on/install-flyctl/")
        return False

    result = subprocess.run(["sh", "-c", "curl -L https://fly.io/install.sh | sh"])
    if result.returncode == 0:
        # Add to PATH for this session
        fly_bin_dir = Path.home() / ".fly" / "bin"
        os.environ["PATH"] = f"{fly_bin_dir}{os.pathsep}{os.environ['PATH']}"
        return True
    return False
