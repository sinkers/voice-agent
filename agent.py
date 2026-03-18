from __future__ import annotations

import logging
import os
import threading
import time
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()

from openai import AsyncOpenAI

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents.voice.room_io.types import RoomOptions
from livekit.plugins import deepgram, openai, silero

_SECONDS_IN_A_DAY = 86400

logger = logging.getLogger("voice-agent")

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

    client = AsyncOpenAI(base_url=url, api_key=token, default_headers=headers)
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
    await ctx.connect()

    _t: dict = {}

    try:
        session = AgentSession(
            stt=deepgram.STT(model="nova-3"),
            llm=_llm,
            tts=openai.TTS(voice="alloy"),
            vad=ctx.proc.userdata["vad"],
        )

        @session.on("user_started_speaking")
        def _on_speech_start(_evt):
            _t["speech_start"] = time.perf_counter()

        @session.on("user_stopped_speaking")
        def _on_speech_end(_evt):
            if "speech_start" in _t:
                _t["speech_end"] = time.perf_counter()
                logger.info("[timing] speech=%.3fs", _t["speech_end"] - _t["speech_start"])

        @session.on("user_input_transcribed")
        def _on_transcribed(evt):
            _t["stt_done"] = time.perf_counter()
            ref = _t.get("speech_end") or _t.get("speech_start")
            if ref:
                logger.info("[timing] stt_latency=%.3fs transcript=%r",
                            _t["stt_done"] - ref, getattr(evt, "transcript", ""))

        @session.on("agent_started_speaking")
        def _on_agent_speak(_evt):
            _t["tts_start"] = time.perf_counter()
            if "stt_done" in _t:
                logger.info("[timing] stt_to_audio=%.3fs (LLM+TTS)",
                            _t["tts_start"] - _t["stt_done"])

        @session.on("agent_stopped_speaking")
        def _on_agent_done(_evt):
            if "tts_start" in _t:
                logger.info("[timing] agent_speaking=%.3fs",
                            time.perf_counter() - _t["tts_start"])

        @session.on("input_speech_started")
        def _dbg_input(_evt):
            logger.info("[debug] input_speech_started fired")

        await session.start(
            agent=VoiceAssistant(),
            room=ctx.room,
            room_options=RoomOptions(),
        )

        logger.info("Agent ready in room: %s", ctx.room.name)
        logger.info("[debug] session.input.audio=%r", session.input.audio)
        logger.info("[debug] room participants: %r",
                    list(ctx.room.remote_participants.keys()))

        _greeting = os.getenv("AGENT_GREETING", "")
        if _greeting:
            await session.say(_greeting)
    except Exception:
        logger.exception("Agent failed to start")
        raise


def prewarm(proc) -> None:
    proc.userdata["vad"] = silero.VAD.load()


def _hub_authenticate(hub_url: str, base_name: str) -> str:
    """Return a valid hub token, prompting device auth if needed."""
    _here = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(_here, f".hub-token-{base_name}")

    if os.path.exists(token_file):
        with open(token_file) as f:
            token = f.read().strip()
        if token:
            return token

    # Device-code flow
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{hub_url}/auth/device")
        resp.raise_for_status()
        data = resp.json()

    device_code = data["device_code"]
    verification_url = data["verification_url"]
    expires_in = data.get("expires_in", 300)

    print(f"[agent] Sign in to Talk to Claw: {verification_url}")
    print("[agent] Waiting for sign-in approval...")

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(3)
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{hub_url}/auth/device/token", params={"code": device_code})
            resp.raise_for_status()
            result = resp.json()

        if "token" in result:
            token = result["token"]
            _here = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(_here, f".hub-token-{base_name}"), "w") as f:
                f.write(token)
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
    Raises ValueError if token is invalid (caller should re-auth)."""
    _here = os.path.dirname(os.path.abspath(__file__))
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{hub_url}/agent/config",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code == 401:
        # Token expired — delete it so next call triggers re-auth
        token_file = os.path.join(_here, f".hub-token-{base_name}")
        if os.path.exists(token_file):
            os.remove(token_file)
        raise ValueError("hub token invalid or expired")
    resp.raise_for_status()
    return resp.json()


def _hub_register(hub_url: str, token: str, agent_name: str, display_name: str, config: dict, base_name: str) -> str:
    """Register agent with hub, persist agent_id, return call_url_base."""
    _here = os.path.dirname(os.path.abspath(__file__))
    with httpx.Client(timeout=30.0) as client:
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
    resp.raise_for_status()
    data = resp.json()

    agent_id_file = os.path.join(_here, f".hub-agent-id-{base_name}")
    with open(agent_id_file, "w") as f:
        f.write(data["agent_id"])

    return data["call_url_base"]


def _start_heartbeat(hub_url: str, token: str) -> None:
    """Start a daemon thread that sends heartbeats every 30 seconds."""
    def _loop():
        while True:
            time.sleep(30)
            try:
                with httpx.Client(timeout=30.0) as client:
                    client.post(
                        f"{hub_url}/agent/heartbeat",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10,
                    )
            except Exception as exc:
                logger.warning("Heartbeat failed: %s", exc)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    _base_name = os.getenv("OPENCLAW_AGENT_NAME", "voice-agent")
    _here = os.path.dirname(os.path.abspath(__file__))

    # Persist instance ID across restarts
    _id_file = os.path.join(_here, f".agent-instance-id-{_base_name}")
    if os.path.exists(_id_file):
        with open(_id_file) as f:
            _instance_id = f.read().strip()
    else:
        _instance_id = uuid.uuid4().hex[:8]
        with open(_id_file, "w") as f:
            f.write(_instance_id)

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

    _start_heartbeat(_hub_url, _hub_token)

    _port = int(os.getenv("AGENT_HTTP_PORT", "8081"))

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=_agent_name,
            port=_port,
        )
    )
