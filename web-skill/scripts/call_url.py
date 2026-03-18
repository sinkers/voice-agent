#!/usr/bin/env python3
"""Wrapper around generate_call_url.py for use from the skill scripts/ directory."""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path so we can import generate_call_url
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from generate_call_url import generate_url  # noqa: E402

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a signed voice call URL")
    parser.add_argument("--agent", default="voice-agent", help="LiveKit agent base name")
    parser.add_argument("--name", default="Voice Agent", help="Display name shown in UI")
    parser.add_argument("--ttl", type=int, default=86400, help="Token TTL in seconds (default: 24h)")
    args = parser.parse_args()

    url = generate_url(
        agent_name=args.agent,
        display_name=args.name,
        ttl_seconds=args.ttl,
    )
    print(url)


if __name__ == "__main__":
    main()
