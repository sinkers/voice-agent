from __future__ import annotations

import logging
import os

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


def _create_tts():
    """Create the TTS provider based on environment configuration.

    Supports multiple providers with automatic fallback to OpenAI.
    """
    provider = os.getenv("TTS_PROVIDER", "openai").lower()

    if provider == "cartesia":
        try:
            from livekit.plugins import cartesia

            voice = os.getenv("CARTESIA_VOICE", "sonic")
            api_key = os.getenv("CARTESIA_API_KEY")
            if not api_key:
                logger.warning("CARTESIA_API_KEY not set, falling back to OpenAI TTS")
            else:
                logger.info("TTS: using Cartesia with voice=%s", voice)
                return cartesia.TTS(voice=voice, api_key=api_key)
        except ImportError:
            logger.warning("livekit-plugins-cartesia not installed, falling back to OpenAI TTS")

    if provider == "elevenlabs":
        try:
            from livekit.plugins import elevenlabs

            voice = os.getenv("ELEVENLABS_VOICE", "rachel")
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                logger.warning("ELEVENLABS_API_KEY not set, falling back to OpenAI TTS")
            else:
                logger.info("TTS: using ElevenLabs with voice=%s", voice)
                return elevenlabs.TTS(voice=voice, api_key=api_key)
        except ImportError:
            logger.warning("livekit-plugins-elevenlabs not installed, falling back to OpenAI TTS")

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

    try:
        session = AgentSession(
            stt=deepgram.STT(model="nova-3"),
            llm=_llm,
            tts=_tts,
            vad=ctx.proc.userdata["vad"],
        )

        await session.start(
            agent=VoiceAssistant(),
            room=ctx.room,
            room_input_options=RoomInputOptions(),
        )

        logger.info("Agent ready in room: %s", ctx.room.name)

        await session.generate_reply(
            instructions="Greet the user briefly and let them know you're ready."
        )
    except Exception:
        logger.exception("Agent failed to start")
        raise


def prewarm(proc) -> None:
    proc.userdata["vad"] = silero.VAD.load()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
