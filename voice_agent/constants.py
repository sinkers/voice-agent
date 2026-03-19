"""Constants and type definitions for the voice agent."""

from typing import TypedDict

# Timeout constants (in seconds)
LLM_STREAMING_READ_TIMEOUT = 60.0  # Max time for LLM to stream a response
HUB_REQUEST_TIMEOUT = 30.0  # Default timeout for hub HTTP requests
HUB_HEARTBEAT_TIMEOUT = 10.0  # Timeout for individual heartbeat requests
HUB_HEARTBEAT_INTERVAL = 30.0  # Time between heartbeat requests
HUB_DEVICE_AUTH_POLL_INTERVAL = 3.0  # Time between device auth polls


# Type definitions for hub API responses
class HubConfig(TypedDict, total=False):
    """Configuration returned from hub /agent/config endpoint."""

    display_name: str
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    deepgram_api_key: str
    openai_api_key: str


class HubRegisterResponse(TypedDict):
    """Response from hub /agent/register endpoint."""

    call_url_base: str
