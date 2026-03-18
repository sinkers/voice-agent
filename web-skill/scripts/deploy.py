#!/usr/bin/env python3
"""Redeploy the voice agent web app to Fly.io (no credential re-prompting)."""

from __future__ import annotations

import sys
from pathlib import Path

from utils import fly, read_app_name, err


def main() -> None:
    script_dir = Path(__file__).parent
    web_dir = script_dir.parent.parent / "web"

    app_name = read_app_name(web_dir / "fly.toml")
    if not app_name:
        print(err("Could not find app name in fly.toml. Run setup.py first."))
        sys.exit(1)

    print(f"Redeploying {app_name}...")
    fly("deploy", "--remote-only", "--app", app_name, cwd=web_dir)
    print(f"\nDone. App: https://{app_name}.fly.dev/")


if __name__ == "__main__":
    main()
