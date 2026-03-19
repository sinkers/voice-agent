from __future__ import annotations

import atexit
import contextlib
import logging
import os
import platform
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any, TypedDict

import httpx
from dotenv import load_dotenv

# Platform-specific file locking
_IS_WINDOWS = platform.system() == "Windows"
if not _IS_WINDOWS:
    import fcntl
else:
    import msvcrt

load_dotenv()

# ruff: noqa: E402 - load_dotenv() must run before livekit imports
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.plugins import deepgram, openai, silero
from openai import AsyncOpenAI

# Timeout constants (in seconds)
LLM_STREAMING_READ_TIMEOUT = 60.0  # Max time for LLM to stream a response
HUB_REQUEST_TIMEOUT = 30.0  # Default timeout for hub HTTP requests
HUB_HEARTBEAT_TIMEOUT = 10.0  # Timeout for individual heartbeat requests
HUB_HEARTBEAT_INTERVAL = 30.0  # Time between heartbeat requests
HUB_DEVICE_AUTH_POLL_INTERVAL = 3.0  # Time between device auth polls

logger = logging.getLogger("voice-agent")


# Type definitions for hub API responses
class HubConfig(TypedDict, total=False):
    """Configuration returned from hub /agent/config endpoint."""

    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    deepgram_api_key: str
    openai_api_key: str
    display_name: str


class HubRegisterResponse(TypedDict):
    """Response from hub /agent/register endpoint."""

    agent_id: str
    call_url_base: str


@contextlib.contextmanager
def _file_lock(file_obj):
    """Context manager for file locking (cross-platform).

    Args:
        file_obj: Open file object to lock

    Yields:
        The locked file object
    """
    try:
        if _IS_WINDOWS:
            # Windows: lock using msvcrt
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 1)
        else:
            # Unix: lock using fcntl
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
        yield file_obj
    finally:
        if _IS_WINDOWS:
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def _create_llm() -> openai.LLM:
    """Create the LLM client.

    Routes via the OpenClaw Gateway if OPENCLAW_GATEWAY_TOKEN is set,
    giving the agent access to memory, tools, and a configured persona.
    Falls back to direct GPT-4o if the token is not present.
    """
    token = os.getenv("OPENCLAW_GATEWAY_TOKEN")
    if not token:
        logger.info("LLM: using OpenAI GPT-4o directly (OPENCLAW_GATEWAY_TOKEN not set)")
        return openai.LLM(model="gpt-4o")

    url = os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1")
    agent_id = os.getenv("OPENCLAW_AGENT_ID", "main")
    session_key = os.getenv("OPENCLAW_SESSION_KEY")

    logger.info(
        "LLM: routing via OpenClaw Gateway → url=%s agent=%s session=%s",
        url,
        agent_id,
        session_key or "(new per request)",
    )

    headers: dict[str, str] = {"x-openclaw-agent-id": agent_id}
    if session_key:
        # Pin all voice calls to a specific session for persistent memory.
        # Without this, each API call creates a throwaway session.
        headers["x-openclaw-session-key"] = session_key

    client = AsyncOpenAI(
        base_url=url,
        api_key=token,
        default_headers=headers,
        timeout=httpx.Timeout(connect=10.0, read=LLM_STREAMING_READ_TIMEOUT, write=10.0, pool=10.0),
    )
    return openai.LLM(client=client, model=f"openclaw:{agent_id}")


_llm = _create_llm()


def _create_tts():
    """Create the TTS provider based on environment configuration.

    Supports multiple providers:
    - openai (default): OpenAI TTS with configurable voice
    - cartesia: Cartesia Sonic (faster, ~100ms first-audio)
    - elevenlabs: ElevenLabs Turbo v2.5 (higher quality)

    Falls back to OpenAI if requested provider isn't installed.
    """
    provider = os.getenv("TTS_PROVIDER", "openai").lower()

    if provider == "cartesia":
        try:
            from livekit.plugins import cartesia

            voice = os.getenv("CARTESIA_VOICE", "sonic")
            api_key = os.getenv("CARTESIA_API_KEY")
            if not api_key:
                logger.warning("CARTESIA_API_KEY not set, falling back to OpenAI TTS")
                provider = "openai"
            else:
                logger.info("TTS: using Cartesia with voice=%s", voice)
                return cartesia.TTS(voice=voice, api_key=api_key)
        except ImportError:
            logger.warning(
                "livekit-plugins-cartesia not installed, falling back to OpenAI TTS. "
                "Install with: uv add livekit-plugins-cartesia"
            )
            provider = "openai"

    if provider == "elevenlabs":
        try:
            from livekit.plugins import elevenlabs

            voice = os.getenv("ELEVENLABS_VOICE", "rachel")
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                logger.warning("ELEVENLABS_API_KEY not set, falling back to OpenAI TTS")
                provider = "openai"
            else:
                logger.info("TTS: using ElevenLabs with voice=%s", voice)
                return elevenlabs.TTS(voice=voice, api_key=api_key)
        except ImportError:
            logger.warning(
                "livekit-plugins-elevenlabs not installed, falling back to OpenAI TTS. "
                "Install with: uv add livekit-plugins-elevenlabs"
            )
            provider = "openai"

    # Default: OpenAI TTS
    voice = os.getenv("OPENAI_TTS_VOICE", "alloy")
    logger.info("TTS: using OpenAI with voice=%s", voice)
    return openai.TTS(voice=voice)


_tts = _create_tts()


VOICE_INSTRUCTIONS = """
You are responding via a real-time voice call. Your responses will be spoken aloud by a
text-to-speech engine, so format them accordingly.

VOICE FORMAT RULES — follow these strictly:
- Respond in plain spoken English only. No markdown whatsoever.
- No asterisks, hashes, backticks, underscores, or other symbols — they will be read aloud.
- No bullet points or numbered lists. Use natural connective language instead
  ("first... then... finally..." or "there are a couple of options:").
- No URLs. If you need to reference a website, describe it in words ("the LiveKit docs site").
- No code blocks. Describe code concepts in plain English.
- No emojis.
- Spell out abbreviations when reading them aloud would be unclear.
- Keep responses concise — 1 to 4 sentences is ideal. Long responses are hard to follow by ear.
- Use natural sentence rhythm. Short, clear sentences flow better through TTS than long ones.
- Don't start with filler phrases like "Certainly!", "Of course!", "Great question!" — just answer.
- If you need to use a tool to answer accurately, do so — but summarise the result in plain speech.
""".strip()


class VoiceAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=VOICE_INSTRUCTIONS)


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Agent connecting to room: %s", ctx.room.name)

    # Track timing data for debugging (cleared on exit)
    _t: dict = {}
    session: AgentSession | None = None

    @ctx.room.on("participant_connected")
    def _on_participant_connected(participant):
        try:
            logger.info("[AUDIO] 🟢 Participant connected: %s", participant.identity)
        except Exception as exc:
            logger.exception("Error in participant_connected handler: %s", exc)

    @ctx.room.on("track_subscribed")
    def _dbg_track(track, pub, participant):
        try:
            from livekit import rtc

            logger.info(
                "[AUDIO] 🎧 Track subscribed: kind=%s source=%s participant=%s",
                track.kind,
                pub.source,
                participant.identity,
            )
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info("[AUDIO] ✅ AUDIO TRACK READY - should receive audio frames now")
        except Exception as exc:
            logger.exception("Error in track_subscribed handler: %s", exc)

    @ctx.room.on("track_published")
    def _dbg_pub(pub, participant):
        try:
            logger.info(
                "[AUDIO] 📢 Track published: source=%s participant=%s subscribed=%s",
                pub.source,
                participant.identity,
                pub.subscribed,
            )
        except Exception as exc:
            logger.exception("Error in track_published handler: %s", exc)

    @ctx.room.on("track_unsubscribed")
    def _on_track_unsubscribed(track, pub, participant):
        try:
            logger.info("[AUDIO] ❌ Track unsubscribed: kind=%s participant=%s", track.kind, participant.identity)
        except Exception as exc:
            logger.exception("Error in track_unsubscribed handler: %s", exc)

    try:
        session = AgentSession(
            stt=deepgram.STT(model="nova-3"),
            llm=_llm,
            tts=_tts,
            vad=ctx.proc.userdata["vad"],
        )

        @session.on("user_started_speaking")  # type: ignore[arg-type]
        def _on_speech_start(_evt):
            try:
                _t["speech_start"] = time.perf_counter()
                logger.info("[AUDIO] 🎤 User started speaking (VAD detected speech)")
            except Exception as exc:
                logger.exception("Error in user_started_speaking handler: %s", exc)

        @session.on("user_stopped_speaking")  # type: ignore[arg-type]
        def _on_speech_end(_evt):
            try:
                if "speech_start" in _t:
                    _t["speech_end"] = time.perf_counter()
                    duration = _t["speech_end"] - _t["speech_start"]
                    logger.info("[AUDIO] 🎤 User stopped speaking (duration: %.3fs) - sending to STT", duration)
            except Exception as exc:
                logger.exception("Error in user_stopped_speaking handler: %s", exc)

        @session.on("user_input_transcribed")
        def _on_transcribed(evt):
            try:
                _t["stt_done"] = time.perf_counter()
                ref = _t.get("speech_end") or _t.get("speech_start")
                transcript = getattr(evt, "transcript", "")
                if ref:
                    stt_latency = _t["stt_done"] - ref
                    logger.info("[AUDIO] 📝 STT transcribed (%.3fs): %r - sending to LLM", stt_latency, transcript)
                else:
                    logger.info("[AUDIO] 📝 STT transcribed: %r - sending to LLM", transcript)
            except Exception as exc:
                logger.exception("Error in user_input_transcribed handler: %s", exc)

        @session.on("agent_started_speaking")  # type: ignore[arg-type]
        def _on_agent_speak(_evt):
            try:
                _t["tts_start"] = time.perf_counter()
                if "stt_done" in _t:
                    llm_tts_time = _t["tts_start"] - _t["stt_done"]
                    logger.info(
                        "[AUDIO] 🔊 Agent started speaking (LLM+TTS took %.3fs) - playing audio to room", llm_tts_time
                    )
                else:
                    logger.info("[AUDIO] 🔊 Agent started speaking - playing audio to room")
            except Exception as exc:
                logger.exception("Error in agent_started_speaking handler: %s", exc)

        @session.on("agent_stopped_speaking")  # type: ignore[arg-type]
        def _on_agent_done(_evt):
            try:
                if "tts_start" in _t:
                    speak_duration = time.perf_counter() - _t["tts_start"]
                    logger.info("[AUDIO] ✅ Agent finished speaking (duration: %.3fs)", speak_duration)
            except Exception as exc:
                logger.exception("Error in agent_stopped_speaking handler: %s", exc)

        @session.on("input_speech_started")  # type: ignore[arg-type]
        def _dbg_input(_evt):
            try:
                logger.info("[AUDIO] 🎙️ Input speech started (VAD detected audio)")
            except Exception as exc:
                logger.exception("Error in input_speech_started handler: %s", exc)

        @session.on("agent_speech_committed")  # type: ignore[arg-type]
        def _on_agent_speech_committed(evt):
            try:
                logger.info("[AUDIO] 💬 Agent response committed - generating TTS audio")
            except Exception as exc:
                logger.exception("Error in agent_speech_committed handler: %s", exc)

        await session.start(
            agent=VoiceAssistant(),
            room=ctx.room,
            room_input_options=RoomInputOptions(),
        )

        logger.info("Agent ready in room: %s", ctx.room.name)
        logger.info("[debug] session.input.audio=%r", session.input.audio)
        logger.info("[debug] room participants: %r", list(ctx.room.remote_participants.keys()))

        # Explicit set_participant in case track_subscribed fired before
        # _init_task resolved _participant_available_fut (race condition with
        # explicit dispatch). Find the first non-agent human participant.
        # Use public room_io property (not _room_io which is private).
        if session.room_io is not None:
            for p in ctx.room.remote_participants.values():
                if not p.identity.startswith("agent-"):
                    logger.info("[debug] explicit set_participant: %s", p.identity)
                    session.room_io.set_participant(p.identity)
                    break

        _greeting = os.getenv("AGENT_GREETING", "")
        if _greeting:
            logger.info("[AUDIO] 📣 Playing greeting: %r", _greeting)
            await session.say(_greeting)
            logger.info("[AUDIO] 🔊 Greeting completed")

    except Exception:
        logger.exception("Agent failed to start")
        raise
    finally:
        # Clean up timing data
        _t.clear()
        logger.info("Agent entrypoint cleanup complete for room: %s", ctx.room.name)


def prewarm(proc: Any) -> None:
    proc.userdata["vad"] = silero.VAD.load()


def _hub_authenticate(hub_url: str, base_name: str) -> str:
    """Return a valid hub token, prompting device auth if needed.
    Raises RuntimeError on network or server errors."""
    _here = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(_here, f".hub-token-{base_name}")

    if os.path.exists(token_file):
        try:
            with open(token_file, "r+") as f, _file_lock(f):
                token = f.read().strip()
                if token:
                    return token
        except OSError as exc:
            logger.warning("Failed to read token file, will re-authenticate: %s", exc)

    # Device-code flow
    try:
        with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
            resp = client.post(f"{hub_url}/auth/device")
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to initiate device auth: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to parse device auth response: {exc}") from exc

    device_code = data["device_code"]
    verification_url = data["verification_url"]
    expires_in = data.get("expires_in", 300)

    print(f"[agent] Sign in to Talk to Claw: {verification_url}")
    print("[agent] Waiting for sign-in approval...")

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(HUB_DEVICE_AUTH_POLL_INTERVAL)
        try:
            with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
                resp = client.get(f"{hub_url}/auth/device/token", params={"code": device_code})
                resp.raise_for_status()
                result = resp.json()
        except httpx.RequestError as exc:
            logger.warning("Device auth poll failed, will retry: %s", exc)
            continue
        except Exception as exc:
            logger.warning("Failed to parse device auth poll response, will retry: %s", exc)
            continue

        if "token" in result:
            token = result["token"]
            _here = os.path.dirname(os.path.abspath(__file__))
            token_path = os.path.join(_here, f".hub-token-{base_name}")
            # Use atomic write: write to temp file, then rename
            temp_path = f"{token_path}.tmp"
            with open(temp_path, "w") as f, _file_lock(f):
                f.write(token)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk
            # Set secure permissions before making visible
            os.chmod(temp_path, 0o600)
            # Atomic rename (overwrites existing file)
            os.replace(temp_path, token_path)
            return token

        status = result.get("status", "")
        if status == "expired":
            print("[agent] Sign-in approval expired. Please restart the agent.")
            raise SystemExit(1)
        # status == "pending" — keep polling

    print("[agent] Timed out waiting for sign-in approval.")
    raise SystemExit(1)


def _hub_get_config(hub_url: str, token: str, base_name: str) -> HubConfig:
    """Fetch agent config from hub. Returns config dict.
    Raises ValueError if token is invalid (caller should re-auth).
    Raises RuntimeError for network or server errors."""
    _here = os.path.dirname(os.path.abspath(__file__))
    try:
        with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
            resp = client.get(
                f"{hub_url}/agent/config",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Hub request timed out after {HUB_REQUEST_TIMEOUT}s: {hub_url}") from exc
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Failed to connect to hub: {hub_url}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Hub request failed: {exc}") from exc

    if resp.status_code == 401:
        # Token expired — delete it so next call triggers re-auth
        token_file = os.path.join(_here, f".hub-token-{base_name}")
        if os.path.exists(token_file):
            try:
                os.remove(token_file)
            except OSError as exc:
                logger.warning("Failed to remove expired token file: %s", exc)
        raise ValueError("hub token invalid or expired")

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Hub returned error {resp.status_code}: {resp.text}") from exc

    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"Failed to parse hub response as JSON: {resp.text[:200]}") from exc


def _hub_register(
    hub_url: str, token: str, agent_name: str, display_name: str, config: HubConfig, base_name: str
) -> str:
    """Register agent with hub, persist agent_id, return call_url_base.
    Raises RuntimeError on network or server errors."""
    _here = os.path.dirname(os.path.abspath(__file__))
    try:
        with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
            resp = client.post(
                f"{hub_url}/agent/register",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "agent_name": agent_name,
                    "display_name": display_name,
                    "livekit_url": config.get("livekit_url", ""),
                    "livekit_api_key": config.get("livekit_api_key", ""),
                    "livekit_api_secret": config.get("livekit_api_secret", ""),
                    "deepgram_api_key": config.get("deepgram_api_key", ""),
                    "openai_api_key": config.get("openai_api_key", ""),
                },
            )
    except httpx.RequestError as exc:
        raise RuntimeError(f"Hub registration request failed: {exc}") from exc

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Hub registration failed with status {resp.status_code}: {resp.text}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Failed to parse hub registration response: {resp.text[:200]}") from exc

    if "agent_id" not in data or "call_url_base" not in data:
        raise RuntimeError(f"Hub registration response missing required fields: {data}")

    # Write agent ID atomically
    agent_id_file = os.path.join(_here, f".hub-agent-id-{base_name}")
    temp_path = f"{agent_id_file}.tmp"
    with open(temp_path, "w") as f, _file_lock(f):
        f.write(data["agent_id"])
        f.flush()
        os.fsync(f.fileno())
    # Set secure permissions before making visible
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, agent_id_file)

    return data["call_url_base"]


class HeartbeatThread:
    """Manages periodic heartbeat requests to the hub in a background thread."""

    def __init__(self, hub_url: str, token_getter: Callable[[], str]):
        """Initialize heartbeat thread.

        Args:
            hub_url: Base URL of the hub
            token_getter: Callable that returns the current auth token (allows refreshing)
        """
        self.hub_url = hub_url
        self.token_getter = token_getter
        self.shutdown_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.failure_count = 0
        self.max_failures = 10  # Stop logging after this many consecutive failures

    def _loop(self) -> None:
        """Background thread loop that sends heartbeats."""
        while not self.shutdown_event.is_set():
            # Use wait() instead of sleep() so shutdown is responsive
            if self.shutdown_event.wait(timeout=HUB_HEARTBEAT_INTERVAL):
                break  # Shutdown requested

            try:
                token = self.token_getter()
                with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
                    resp = client.post(
                        f"{self.hub_url}/agent/heartbeat",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=HUB_HEARTBEAT_TIMEOUT,
                    )
                    resp.raise_for_status()
                # Reset failure count on success
                if self.failure_count > 0:
                    logger.info("Heartbeat recovered after %d failures", self.failure_count)
                    self.failure_count = 0
            except Exception as exc:
                self.failure_count += 1
                if self.failure_count <= self.max_failures:
                    logger.warning("Heartbeat failed (#%d): %s", self.failure_count, exc)
                elif self.failure_count == self.max_failures + 1:
                    logger.error("Heartbeat failing repeatedly, suppressing further warnings")

    def start(self) -> None:
        """Start the heartbeat thread."""
        if self.thread is not None:
            logger.warning("Heartbeat thread already started")
            return
        self.thread = threading.Thread(target=self._loop, daemon=True, name="HeartbeatThread")
        self.thread.start()
        logger.info("Heartbeat thread started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the heartbeat thread gracefully.

        Args:
            timeout: Max seconds to wait for thread to stop
        """
        if self.thread is None:
            return
        logger.info("Stopping heartbeat thread...")
        self.shutdown_event.set()
        self.thread.join(timeout=timeout)
        if self.thread.is_alive():
            logger.warning("Heartbeat thread did not stop within %s seconds", timeout)
        else:
            logger.info("Heartbeat thread stopped")
        self.thread = None


def _start_heartbeat(hub_url: str, token: str) -> HeartbeatThread:
    """Start a daemon thread that sends heartbeats every HUB_HEARTBEAT_INTERVAL seconds.

    Returns the HeartbeatThread instance for shutdown control."""
    # Use a lambda to allow token to be updated if needed
    # (though in current implementation it's static)
    heartbeat = HeartbeatThread(hub_url, lambda: token)
    heartbeat.start()
    return heartbeat


if __name__ == "__main__":
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
    _config = None
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
        _val = _config.get(_cfg_key, "")
        if _val:
            os.environ[_env_key] = str(_val)

    _call_url_base = _hub_register(_hub_url, _hub_token, _agent_name, _display_name, _config, _base_name)

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
