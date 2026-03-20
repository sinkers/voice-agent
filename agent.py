"""Voice agent - backward compatibility shim.

This file maintains backward compatibility with existing code that imports from agent.py.
The actual implementation has been refactored into the agent/ package.
"""

from __future__ import annotations

import importlib
import sys

from dotenv import load_dotenv

load_dotenv()

# ruff: noqa: E402, F401 - load_dotenv() must run before imports, and all imports are intentional re-exports

import os  # Re-exported for test compatibility

import httpx  # Re-exported for test compatibility

# When this module is reloaded (e.g. in tests), also reload the voice_agent submodules
# so that module-level initialization (_llm, _tts) runs again with updated env/patches
_voice_agent_modules = [
    "voice_agent.constants",
    "voice_agent.hub",
    "voice_agent.llm",
    "voice_agent.session",
    "voice_agent.heartbeat",
    "voice_agent.startup",
]
for _mod_name in _voice_agent_modules:
    if _mod_name in sys.modules:
        importlib.reload(sys.modules[_mod_name])

# Re-export everything from the voice_agent package
from voice_agent.constants import (
    HUB_DEVICE_AUTH_POLL_INTERVAL,
    HUB_HEARTBEAT_INTERVAL,
    HUB_HEARTBEAT_TIMEOUT,
    HUB_REQUEST_TIMEOUT,
    LLM_STREAMING_READ_TIMEOUT,
    HubConfig,
    HubRegisterResponse,
)
from voice_agent.heartbeat import HeartbeatThread, _start_heartbeat
from voice_agent.hub import _hub_authenticate, _hub_get_config, _hub_register
from voice_agent.llm import VOICE_INSTRUCTIONS, _create_llm, _create_tts, _llm, _tts
from voice_agent.session import VoiceAssistant, entrypoint, prewarm

# Main entry point
if __name__ == "__main__":
    from voice_agent.startup import main

    main()
