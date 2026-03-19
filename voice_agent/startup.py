"""Agent startup and initialization."""

import atexit
import logging
import os
import uuid

from livekit.agents import WorkerOptions, cli

from .constants import HubConfig
from .heartbeat import _start_heartbeat
from .hub import _file_lock, _hub_authenticate, _hub_get_config, _hub_register
from .session import entrypoint, prewarm

logger = logging.getLogger("voice-agent")


def main() -> None:
    """Main entry point for the voice agent."""
    _base_name = os.getenv("OPENCLAW_AGENT_NAME", "voice-agent")
    _here = os.path.dirname(os.path.abspath(__file__))

    # Persist instance ID across restarts
    _id_file = os.path.join(_here, f".agent-instance-id-{_base_name}")
    if os.path.exists(_id_file):
        with open(_id_file) as f, _file_lock(f):
            _instance_id = f.read().strip()
    else:
        _instance_id = uuid.uuid4().hex[:8]
        temp_path = f"{_id_file}.tmp"
        with open(temp_path, "w") as f, _file_lock(f):
            f.write(_instance_id)
            f.flush()
            os.fsync(f.fileno())
        # Set secure permissions before making visible
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, _id_file)

    _agent_name = f"{_base_name}-{_instance_id}"
    _display_name = os.getenv("OPENCLAW_AGENT_DISPLAY_NAME", _base_name.replace("-", " ").title())

    print(f"[agent] Starting as: {_agent_name} (instance: {_instance_id})")

    # Hub authentication and configuration
    _hub_url = os.getenv("HUB_URL", "https://voice-agent-hub.fly.dev")

    _hub_token = _hub_authenticate(_hub_url, _base_name)

    # Try to get config from hub (may not exist on first run)
    _config: HubConfig | None = None
    try:
        _config = _hub_get_config(_hub_url, _hub_token, _base_name)
    except ValueError:
        # Token was invalid; re-authenticate once
        _hub_token = _hub_authenticate(_hub_url, _base_name)
        _config = _hub_get_config(_hub_url, _hub_token, _base_name)
    except RuntimeError as exc:
        # If agent not registered yet (404), use .env values as initial config
        if "404" in str(exc) and "No agent registered" in str(exc):
            logger.info("First run detected - using .env credentials for initial registration")
            _config = {
                "livekit_url": os.getenv("LIVEKIT_URL", ""),
                "livekit_api_key": os.getenv("LIVEKIT_API_KEY", ""),
                "livekit_api_secret": os.getenv("LIVEKIT_API_SECRET", ""),
                "deepgram_api_key": os.getenv("DEEPGRAM_API_KEY", ""),
                "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
            }
        else:
            # Other errors should still fail
            raise

    # Hub keys are authoritative — override any .env values (if hub returned config)
    _key_map = {
        "livekit_url": "LIVEKIT_URL",
        "livekit_api_key": "LIVEKIT_API_KEY",
        "livekit_api_secret": "LIVEKIT_API_SECRET",
        "deepgram_api_key": "DEEPGRAM_API_KEY",
        "openai_api_key": "OPENAI_API_KEY",
    }
    for _cfg_key, _env_key in _key_map.items():
        _val = _config.get(_cfg_key, "")  # type: ignore[union-attr]
        if _val:
            os.environ[_env_key] = str(_val)

    _call_url_base = _hub_register(_hub_url, _hub_token, _agent_name, _display_name, _config, _base_name)  # type: ignore[arg-type]

    # Print call URL prominently for easy testing
    print("\n" + "=" * 80)
    print("🎤 VOICE AGENT READY")
    print("=" * 80)
    print(f"\n📞 Call URL (for testing):\n   {_call_url_base}\n")
    print("=" * 80 + "\n")

    # Start heartbeat thread and register shutdown handler
    _heartbeat = _start_heartbeat(_hub_url, _hub_token)
    atexit.register(_heartbeat.stop)

    _port = int(os.getenv("AGENT_HTTP_PORT", "8081"))

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=_agent_name,
            port=_port,
        )
    )
