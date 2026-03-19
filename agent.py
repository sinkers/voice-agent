from __future__ import annotations

import atexit
import contextlib
import logging
import os
import platform
import threading
import time
import uuid

import httpx
from dotenv import load_dotenv

# Platform-specific file locking
_IS_WINDOWS = platform.system() == "Windows"
if not _IS_WINDOWS:
    import fcntl
else:
    import msvcrt

load_dotenv()

from openai import AsyncOpenAI

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents import RoomInputOptions
from livekit.plugins import deepgram, openai, silero

# Timeout constants (in seconds)
LLM_STREAMING_READ_TIMEOUT = 60.0  # Max time for LLM to stream a response
HUB_REQUEST_TIMEOUT = 30.0  # Default timeout for hub HTTP requests
HUB_HEARTBEAT_TIMEOUT = 10.0  # Timeout for individual heartbeat requests
HUB_HEARTBEAT_INTERVAL = 30.0  # Time between heartbeat requests
HUB_DEVICE_AUTH_POLL_INTERVAL = 3.0  # Time between device auth polls

logger = logging.getLogger("voice-agent")


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
    session = None

    @ctx.room.on("track_subscribed")
    def _dbg_track(track, pub, participant):
        try:
            logger.info("[debug] track_subscribed: kind=%s source=%s participant=%s",
                        track.kind, pub.source, participant.identity)
        except Exception as exc:
            logger.exception("Error in track_subscribed handler: %s", exc)

    @ctx.room.on("track_published")
    def _dbg_pub(pub, participant):
        try:
            logger.info("[debug] track_published: source=%s participant=%s subscribed=%s",
                        pub.source, participant.identity, pub.subscribed)
        except Exception as exc:
            logger.exception("Error in track_published handler: %s", exc)

    try:
        session = AgentSession(
            stt=deepgram.STT(model="nova-3"),
            llm=_llm,
            tts=openai.TTS(voice="alloy"),
            vad=ctx.proc.userdata["vad"],
        )

        @session.on("user_started_speaking")
        def _on_speech_start(_evt):
            try:
                _t["speech_start"] = time.perf_counter()
            except Exception as exc:
                logger.exception("Error in user_started_speaking handler: %s", exc)

        @session.on("user_stopped_speaking")
        def _on_speech_end(_evt):
            try:
                if "speech_start" in _t:
                    _t["speech_end"] = time.perf_counter()
                    logger.info("[timing] speech=%.3fs", _t["speech_end"] - _t["speech_start"])
            except Exception as exc:
                logger.exception("Error in user_stopped_speaking handler: %s", exc)

        @session.on("user_input_transcribed")
        def _on_transcribed(evt):
            try:
                _t["stt_done"] = time.perf_counter()
                ref = _t.get("speech_end") or _t.get("speech_start")
                if ref:
                    logger.info("[timing] stt_latency=%.3fs transcript=%r",
                                _t["stt_done"] - ref, getattr(evt, "transcript", ""))
            except Exception as exc:
                logger.exception("Error in user_input_transcribed handler: %s", exc)

        @session.on("agent_started_speaking")
        def _on_agent_speak(_evt):
            try:
                _t["tts_start"] = time.perf_counter()
                if "stt_done" in _t:
                    logger.info("[timing] stt_to_audio=%.3fs (LLM+TTS)",
                                _t["tts_start"] - _t["stt_done"])
            except Exception as exc:
                logger.exception("Error in agent_started_speaking handler: %s", exc)

        @session.on("agent_stopped_speaking")
        def _on_agent_done(_evt):
            try:
                if "tts_start" in _t:
                    logger.info("[timing] agent_speaking=%.3fs",
                                time.perf_counter() - _t["tts_start"])
            except Exception as exc:
                logger.exception("Error in agent_stopped_speaking handler: %s", exc)

        @session.on("input_speech_started")
        def _dbg_input(_evt):
            try:
                logger.info("[debug] input_speech_started fired")
            except Exception as exc:
                logger.exception("Error in input_speech_started handler: %s", exc)

        await session.start(
            agent=VoiceAssistant(),
            room=ctx.room,
            room_input_options=RoomInputOptions(),
        )

        logger.info("Agent ready in room: %s", ctx.room.name)
        logger.info("[debug] session.input.audio=%r", session.input.audio)
        logger.info("[debug] room participants: %r",
                    list(ctx.room.remote_participants.keys()))

        # Explicit set_participant in case track_subscribed fired before
        # _init_task resolved _participant_available_fut (race condition with
        # explicit dispatch). Find the first non-agent human participant.
        if session._room_io is not None:
            for p in ctx.room.remote_participants.values():
                if not p.identity.startswith("agent-"):
                    logger.info("[debug] explicit set_participant: %s", p.identity)
                    session._room_io.set_participant(p.identity)
                    break

        _greeting = os.getenv("AGENT_GREETING", "")
        if _greeting:
            await session.say(_greeting)
    except Exception:
        logger.exception("Agent failed to start")
        raise
    finally:
        # Clean up timing data
        _t.clear()
        logger.info("Agent entrypoint cleanup complete for room: %s", ctx.room.name)


def prewarm(proc) -> None:
    proc.userdata["vad"] = silero.VAD.load()


def _hub_authenticate(hub_url: str, base_name: str) -> str:
    """Return a valid hub token, prompting device auth if needed.
    Raises RuntimeError on network or server errors."""
    _here = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(_here, f".hub-token-{base_name}")

    if os.path.exists(token_file):
        try:
            with open(token_file, "r+") as f:
                with _file_lock(f):
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
            with open(temp_path, "w") as f:
                with _file_lock(f):
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


def _hub_get_config(hub_url: str, token: str, base_name: str) -> dict:
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
    except httpx.TimeoutException:
        raise RuntimeError(f"Hub request timed out after {HUB_REQUEST_TIMEOUT}s: {hub_url}")
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


def _hub_register(hub_url: str, token: str, agent_name: str, display_name: str, config: dict, base_name: str) -> str:
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
    with open(temp_path, "w") as f:
        with _file_lock(f):
            f.write(data["agent_id"])
            f.flush()
            os.fsync(f.fileno())
    # Set secure permissions before making visible
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, agent_id_file)

    return data["call_url_base"]


class HeartbeatThread:
    """Manages periodic heartbeat requests to the hub in a background thread."""

    def __init__(self, hub_url: str, token_getter: callable):
        """Initialize heartbeat thread.

        Args:
            hub_url: Base URL of the hub
            token_getter: Callable that returns the current auth token (allows refreshing)
        """
        self.hub_url = hub_url
        self.token_getter = token_getter
        self.shutdown_event = threading.Event()
        self.thread = None
        self.failure_count = 0
        self.max_failures = 10  # Stop logging after this many consecutive failures

    def _loop(self):
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

    def start(self):
        """Start the heartbeat thread."""
        if self.thread is not None:
            logger.warning("Heartbeat thread already started")
            return
        self.thread = threading.Thread(target=self._loop, daemon=True, name="HeartbeatThread")
        self.thread.start()
        logger.info("Heartbeat thread started")

    def stop(self, timeout=5.0):
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
        with open(_id_file, "r") as f:
            with _file_lock(f):
                _instance_id = f.read().strip()
    else:
        _instance_id = uuid.uuid4().hex[:8]
        temp_path = f"{_id_file}.tmp"
        with open(temp_path, "w") as f:
            with _file_lock(f):
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

    try:
        _config = _hub_get_config(_hub_url, _hub_token, _base_name)
    except ValueError:
        # Token was invalid; re-authenticate once
        _hub_token = _hub_authenticate(_hub_url, _base_name)
        _config = _hub_get_config(_hub_url, _hub_token, _base_name)

    # Hub keys are authoritative — override any .env values
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
            os.environ[_env_key] = _val

    _call_url_base = _hub_register(_hub_url, _hub_token, _agent_name, _display_name, _config, _base_name)
    print(f"[agent] Call URL: {_call_url_base}")

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
