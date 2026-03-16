from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

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
_OPENCLAW_URL = os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1")
_OPENCLAW_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN")

_USE_OPENCLAW = bool(_OPENCLAW_TOKEN)

if _USE_OPENCLAW:
    logger.info("LLM: routing via OpenClaw Gateway at %s (agent: alex)", _OPENCLAW_URL)
    _llm = openai.LLM(
        model="openclaw:alex",
        base_url=_OPENCLAW_URL,
        api_key=_OPENCLAW_TOKEN,
    )
else:
    logger.info("LLM: using OpenAI GPT-4o directly")
    _llm = openai.LLM(model="gpt-4o")


class VoiceAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are responding via a real-time voice call. "
                "Keep responses brief (1-3 sentences), conversational, and clear. "
                "Avoid markdown, bullet lists, and long explanations — this is spoken audio. "
                "You can use your tools if needed to answer questions accurately."
            )
        )


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
