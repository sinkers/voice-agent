"""Agent session and voice assistant implementation."""

import logging
import os
import time
from typing import Any

from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions
from livekit.plugins import deepgram, silero

from .llm import VOICE_INSTRUCTIONS, _llm, _tts

logger = logging.getLogger("voice-agent")


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
