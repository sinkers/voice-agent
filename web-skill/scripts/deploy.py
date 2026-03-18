#!/usr/bin/env python3
"""Redeploy the voice agent web app to Fly.io (no credential re-prompting)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def fly_bin() -> str:
    for candidate in ["fly", "flyctl", str(Path.home() / ".fly" / "bin" / "fly")]:
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    print("flyctl not found. Run setup.py first.")
    sys.exit(1)


def main() -> None:
    script_dir = Path(__file__).parent
    web_dir = script_dir.parent.parent / "web"

    # Read app name from fly.toml
    fly_toml = web_dir / "fly.toml"
    app_name = None
    if fly_toml.exists():
        for line in fly_toml.read_text().splitlines():
            if line.startswith("app ="):
                app_name = line.split("=", 1)[1].strip().strip('"')
                break

    if not app_name:
        print("Could not find app name in fly.toml. Run setup.py first.")
        sys.exit(1)

    print(f"Redeploying {app_name}...")
    subprocess.run(
        [fly_bin(), "deploy", "--remote-only", "--app", app_name],
        cwd=web_dir,
        check=True,
    )
    print(f"\nDone. App: https://{app_name}.fly.dev/")


if __name__ == "__main__":
    main()
