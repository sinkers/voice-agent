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

# Route LLM calls through the local OpenClaw Gateway (Alex agent) if configured,
# otherwise fall back to direct OpenAI GPT-4o.
#
# Session persistence: x-openclaw-session-key forces all voice calls to route
# to the same stable Alex session, giving the agent full memory and context
# across separate calls. Without this, each API call would create a fresh session.
_OPENCLAW_URL = os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1")
_OPENCLAW_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN")
_OPENCLAW_SESSION_KEY = os.getenv("OPENCLAW_SESSION_KEY", "voice-agent-andrew")

_USE_OPENCLAW = bool(_OPENCLAW_TOKEN)

if _USE_OPENCLAW:
    logger.info(
        "LLM: routing via OpenClaw Gateway at %s (session: %s)",
        _OPENCLAW_URL,
        _OPENCLAW_SESSION_KEY,
    )
    # Use a stable session key so Alex retains memory across voice calls.
    # x-openclaw-session-key tells the Gateway to use (or create) a named session
    # rather than spinning up a throwaway one per request.
    _oc_client = AsyncOpenAI(
        base_url=_OPENCLAW_URL,
        api_key=_OPENCLAW_TOKEN,
        default_headers={
            "x-openclaw-agent-id": "alex",
            "x-openclaw-session-key": _OPENCLAW_SESSION_KEY,
        },
    )
    _llm = openai.LLM(client=_oc_client, model="openclaw:alex")
else:
    logger.info("LLM: using OpenAI GPT-4o directly (no OPENCLAW_GATEWAY_TOKEN set)")
    _llm = openai.LLM(model="gpt-4o")


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
            tts=openai.TTS(voice="alloy"),
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
