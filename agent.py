from __future__ import annotations

import logging
import os
import time
import uuid

import jwt as _jwt
from dotenv import load_dotenv

load_dotenv()

from openai import AsyncOpenAI

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.plugins import deepgram, openai, silero

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

        await session.start(
            agent=VoiceAssistant(),
            room=ctx.room,
            room_input_options=RoomInputOptions(),
        )

        logger.info("Agent ready in room: %s", ctx.room.name)

        _greeting = os.getenv("AGENT_GREETING", "")
        if _greeting:
            await session.say(_greeting)
    except Exception:
        logger.exception("Agent failed to start")
        raise


def prewarm(proc) -> None:
    proc.userdata["vad"] = silero.VAD.load()


_SECONDS_IN_A_DAY = 86400

if __name__ == "__main__":
    _base_name = os.getenv("OPENCLAW_AGENT_NAME", "voice-agent")
    # Use a persistent instance ID so call URLs stay valid across restarts.
    # Only generate a new UUID if no ID file exists yet (first run).
    _id_file = os.path.join(os.path.dirname(__file__), f".agent-instance-id-{_base_name}")
    if os.path.exists(_id_file):
        with open(_id_file) as f:
            _instance_id = f.read().strip()
    else:
        _instance_id = uuid.uuid4().hex[:8]
        with open(_id_file, "w") as f:
            f.write(_instance_id)

    _agent_name = f"{_base_name}-{_instance_id}"

    print(f"[agent] Starting as: {_agent_name} (instance: {_instance_id})")

    # Print call URL at startup if configured
    _call_base = os.getenv("CALL_BASE_URL", "")
    _config_secret = os.getenv("CONFIG_SECRET", "")
    if _call_base and _config_secret:
        try:
            _display = os.getenv("OPENCLAW_AGENT_DISPLAY_NAME", _base_name.replace("-", " ").title())
            _now = int(time.time())
            _payload = {
                "agent_name": _agent_name,
                "display_name": _display,
                "iat": _now,
                "exp": _now + _SECONDS_IN_A_DAY,
            }
            _token = _jwt.encode(_payload, _config_secret, algorithm="HS256")
            print(f"[agent] Call URL (24h): {_call_base}/?token={_token}")
        except Exception as e:
            print(f"[agent] Could not generate call URL: {e}")

    _port = int(os.getenv("AGENT_HTTP_PORT", "8081"))

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=_agent_name,
            port=_port,
        )
    )
