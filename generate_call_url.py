#!/usr/bin/env python3
"""
Generate a signed call URL for the voice agent web app.

Usage:
    python generate_call_url.py --agent voice-agent --name "Alex" --ttl 3600
    python generate_call_url.py --agent other-agent --name "Clive" \
        --livekit-url wss://other.livekit.cloud \
        --livekit-key APIxxx --livekit-secret yyy

Environment (loaded from .env):
    CONFIG_SECRET       - shared signing secret (must match Fly secret)
    CALL_BASE_URL       - base URL of the web app (default: https://voice-agent-web.fly.dev)
    LIVEKIT_URL         - default LiveKit URL (used if --livekit-url not set)
    LIVEKIT_API_KEY     - default API key
    LIVEKIT_API_SECRET  - default API secret
"""

import argparse
import os
import time
import jwt
from dotenv import load_dotenv

load_dotenv()

CONFIG_SECRET = os.environ.get("CONFIG_SECRET", "")
CALL_BASE_URL = os.environ.get("CALL_BASE_URL", "https://voice-agent-web.fly.dev")

def _read_instance_id(agent_name: str) -> str:
    """Read the running instance ID for a given agent base name."""
    _id_file = os.path.join(os.path.dirname(__file__), f".agent-instance-id-{agent_name}")
    if os.path.exists(_id_file):
        with open(_id_file) as f:
            return f.read().strip()
    # Fallback: legacy single-file
    _legacy = os.path.join(os.path.dirname(__file__), ".agent-instance-id")
    if os.path.exists(_legacy):
        with open(_legacy) as f:
            return f.read().strip()
    return ""


def generate_url(
    agent_name: str,
    display_name: str,
    ttl_seconds: int = 3600,
    livekit_url: str | None = None,
    livekit_api_key: str | None = None,
    livekit_api_secret: str | None = None,
) -> str:
    if not CONFIG_SECRET:
        raise ValueError("CONFIG_SECRET is not set")

    # Namespace agent name with instance ID so multiple instances don't share workers
    _instance_id = os.environ.get("OPENCLAW_INSTANCE_ID") or _read_instance_id(agent_name)
    if _instance_id and not agent_name.endswith(f"-{_instance_id}"):
        agent_name = f"{agent_name}-{_instance_id}"

    payload: dict = {
        "agent_name": agent_name,
        "display_name": display_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_seconds,
    }

    # Only include LiveKit creds if they differ from the server defaults
    if livekit_url:
        payload["livekit_url"] = livekit_url
    if livekit_api_key:
        payload["livekit_api_key"] = livekit_api_key
    if livekit_api_secret:
        payload["livekit_api_secret"] = livekit_api_secret

    token = jwt.encode(payload, CONFIG_SECRET, algorithm="HS256")
    return f"{CALL_BASE_URL}/?token={token}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a signed voice call URL")
    parser.add_argument("--agent", default="voice-agent", help="LiveKit agent name")
    parser.add_argument("--name", default="Voice Agent", help="Display name shown in UI")
    parser.add_argument("--ttl", type=int, default=3600, help="Token validity in seconds")
    parser.add_argument("--livekit-url", help="Override LiveKit server URL")
    parser.add_argument("--livekit-key", help="Override LiveKit API key")
    parser.add_argument("--livekit-secret", help="Override LiveKit API secret")
    args = parser.parse_args()

    url = generate_url(
        agent_name=args.agent,
        display_name=args.name,
        ttl_seconds=args.ttl,
        livekit_url=args.livekit_url,
        livekit_api_key=args.livekit_key,
        livekit_api_secret=args.livekit_secret,
    )
    print(url)
