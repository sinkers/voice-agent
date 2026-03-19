"""
Agent smoke test — end-to-end test against a live hub and running agent worker.

Tests the full stack:
  1. Agent can connect to hub and is registered (agent/config responds)
  2. /connect dispatches agent to a room → caller receives audio (greeting)
     → transcript contains the agent's configured display name
  3. Caller publishes a question → agent responds → transcript is non-empty

Requirements:
  - Hub must be deployed and reachable (HUB_URL)
  - Agent worker must be running and registered (reads from .hub-agent-id-voice-agent)

Env vars:
  HUB_URL           - default: https://voice-agent-hub.fly.dev
  AGENT_REPO        - path to livekit-agent repo, default: directory containing this file's parent
  OPENAI_API_KEY    - for Whisper STT on received audio (required)
  LIVEKIT_API_KEY   - to verify LiveKit credentials (read from .env if not set)
  LIVEKIT_API_SECRET

Run:
  cd ~/Documents/livekit-agent
  uv run python tests/smoke_test.py
  # or:
  make smoke-test
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import wave
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AGENT_REPO = Path(os.environ.get("AGENT_REPO", Path(__file__).parent.parent))
HUB_URL = os.environ.get("HUB_URL", "https://voice-agent-hub.fly.dev").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Audio constants
AUDIO_SAMPLE_RATE = 48000  # 48kHz - LiveKit standard sample rate
AUDIO_CHANNELS = 1  # Mono audio
AUDIO_SAMPLE_WIDTH = 2  # 16-bit audio (2 bytes per sample)
FRAME_DURATION_MS = 10  # 10ms frames (LiveKit standard)
SAMPLES_PER_FRAME = AUDIO_SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 480 samples for 10ms at 48kHz
BYTES_PER_FRAME = SAMPLES_PER_FRAME * AUDIO_SAMPLE_WIDTH  # 960 bytes per 10ms frame
FRAME_DURATION_S = FRAME_DURATION_MS / 1000  # 0.01 seconds

# Silence detection constants
SILENCE_CHECK_SAMPLE_INTERVAL = 50  # Check every 50th byte for non-zero (optimization)

# Timeout constants (seconds)
DEFAULT_SPEECH_WAIT_TIMEOUT = 20.0  # Max time to wait for agent to start speaking
MAX_AUDIO_DRAIN_TIMEOUT = 15.0  # Max time to wait for agent to finish speaking
GREETING_WAIT_TIMEOUT = 20.0  # Max time to wait for greeting to complete
RESPONSE_WAIT_TIMEOUT = 20.0  # Max time to wait for agent response

# Load from .env if not set
_env_file = AGENT_REPO / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
if not OPENAI_API_KEY:
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def _load_agent_credentials() -> tuple[str, str]:
    """Return (hub_token, agent_id) from local files. Exits if missing."""
    token_file = AGENT_REPO / ".hub-token-voice-agent"
    id_file = AGENT_REPO / ".hub-agent-id-voice-agent"
    missing = []
    if not token_file.exists():
        missing.append(str(token_file))
    if not id_file.exists():
        missing.append(str(id_file))
    if missing:
        print(f"ERROR: Agent not registered. Missing files:\n  " + "\n  ".join(missing))
        print("Start the agent worker first: cd ~/Documents/livekit-agent && uv run python agent.py start")
        sys.exit(1)
    return token_file.read_text().strip(), id_file.read_text().strip()


def _check_env() -> None:
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY required for Whisper transcription")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _frames_to_wav(frames) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(AUDIO_SAMPLE_WIDTH)
        wf.setframerate(AUDIO_SAMPLE_RATE)
        for frame in frames:
            wf.writeframes(bytes(frame.data))
    return buf.getvalue()


def _transcribe(wav_bytes: bytes) -> str:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    return client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.wav", wav_bytes, "audio/wav"),
    ).text.lower()


def _tts_question(text: str) -> bytes:
    """Generate MP3 bytes of spoken text via OpenAI TTS."""
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    resp = client.audio.speech.create(model="tts-1", voice="alloy", input=text)
    return resp.content


def _mp3_to_pcm48k(mp3_bytes: bytes) -> bytes:
    import av
    buf = io.BytesIO(mp3_bytes)
    container = av.open(buf)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=AUDIO_SAMPLE_RATE)
    chunks = []
    for frame in container.decode(audio=0):
        for rf in resampler.resample(frame):
            chunks.append(bytes(rf.planes[0]))
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# LiveKit room helpers
# ---------------------------------------------------------------------------

async def _collect_agent_audio(lk_token: str, lk_url: str,
                                wait_for_speech_s: float = DEFAULT_SPEECH_WAIT_TIMEOUT,
                                drain_silence_s: float = 2.0,
                                pcm_to_publish: bytes | None = None) -> list:
    """
    Join room, optionally publish audio, collect agent audio frames.
    Returns frames list. Raises RuntimeError on timeout.
    """
    from livekit import rtc

    room = rtc.Room()
    agent_frames: list = []
    agent_speaking = asyncio.Event()

    @room.on("track_subscribed")
    def on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity != "caller":
            stream = rtc.AudioStream(track)
            async def collect():
                async for fe in stream:
                    # Only keep non-silent frames so the drain loop can detect
                    # when the agent stops speaking (LiveKit streams silence
                    # continuously — appending all frames means the frame count
                    # never stabilises and the drain loop runs forever).
                    raw = bytes(fe.frame.data)
                    if any(b != 0 for b in raw[::SILENCE_CHECK_SAMPLE_INTERVAL]):
                        agent_frames.append(fe.frame)
                        agent_speaking.set()
            asyncio.ensure_future(collect())

    await room.connect(lk_url, lk_token)

    # Publish question audio if provided
    if pcm_to_publish:
        source = rtc.AudioSource(sample_rate=AUDIO_SAMPLE_RATE, num_channels=AUDIO_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("test-mic", source)
        opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(track, opts)
        # Push PCM frames (10ms chunks at 48kHz = 480 samples = 960 bytes)
        chunk_bytes = BYTES_PER_FRAME
        for i in range(0, len(pcm_to_publish), chunk_bytes):
            chunk = pcm_to_publish[i:i + chunk_bytes]
            chunk = chunk.ljust(chunk_bytes, b'\x00')
            frame = rtc.AudioFrame(
                data=chunk,
                sample_rate=AUDIO_SAMPLE_RATE,
                num_channels=AUDIO_CHANNELS,
                samples_per_channel=SAMPLES_PER_FRAME,
            )
            await source.capture_frame(frame)
            await asyncio.sleep(FRAME_DURATION_S)

    try:
        await asyncio.wait_for(agent_speaking.wait(), timeout=wait_for_speech_s)
    except asyncio.TimeoutError:
        await room.disconnect()
        raise RuntimeError(f"Agent did not speak within {wait_for_speech_s:.0f}s — is the agent worker running?")

    # Drain: wait for silence (no new non-silent frames in drain_silence_s),
    # but cap total drain time at 15 s so the loop never runs forever.
    MAX_DRAIN_S = MAX_AUDIO_DRAIN_TIMEOUT
    drain_start = asyncio.get_event_loop().time()
    last_len = len(agent_frames)
    while True:
        await asyncio.sleep(drain_silence_s)
        elapsed = asyncio.get_event_loop().time() - drain_start
        if len(agent_frames) == last_len or elapsed >= MAX_DRAIN_S:
            break
        last_len = len(agent_frames)

    await room.disconnect()
    return agent_frames


async def _connect_async(agent_id: str) -> dict:
    """Call /connect and return the response dict."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{HUB_URL}/connect", json={"agent_id": agent_id})
        r.raise_for_status()
        return r.json()


def _connect(agent_id: str) -> dict:
    with httpx.Client(timeout=30) as client:
        r = client.post(f"{HUB_URL}/connect", json={"agent_id": agent_id})
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_agent_registered(hub_token: str) -> None:
    """Agent is registered and /agent/config returns display_name."""
    print("test_agent_registered … ", end="", flush=True)
    with httpx.Client(timeout=30) as client:
        r = client.get(f"{HUB_URL}/agent/config",
                       headers={"Authorization": f"Bearer {hub_token}"})
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("display_name"), "display_name is empty"
        assert data.get("livekit_url"), "livekit_url is empty"
    print(f"OK (display_name={data['display_name']!r})")
    return data["display_name"]


async def _greeting_flow(agent_id: str) -> tuple[list, dict]:
    """
    Call /connect then immediately join the LiveKit room — both in the same
    event loop so the room join happens within milliseconds of /connect
    returning, well inside the hub's 1.5 s agent-dispatch delay.
    """
    conn = await _connect_async(agent_id)
    assert conn["token"], "No LiveKit token"
    assert conn["url"].startswith("wss://"), f"Bad url: {conn['url']}"
    frames = await _collect_agent_audio(conn["token"], conn["url"])
    return frames, conn


def test_greeting(agent_id: str, display_name: str) -> None:
    """Agent joins room and greets with its configured display_name."""
    print("test_greeting … ", end="", flush=True)

    # Run /connect and room.connect() in the same event loop so we are in the
    # room before the hub's 1.5 s dispatch delay fires and the agent arrives.
    frames, conn = asyncio.run(_greeting_flow(agent_id))
    assert frames, "No audio frames received"

    wav = _frames_to_wav(frames)
    transcript = _transcribe(wav)
    assert display_name.lower() in transcript, \
        f"display_name {display_name!r} not in greeting transcript: {transcript!r}"
    print(f"OK (transcript: {transcript!r})")


async def _audio_response_flow(agent_id: str, pcm: bytes) -> list:
    """
    Connect to a fresh room. Wait for the agent's greeting to start, then
    wait a fixed window for it to finish before publishing the question and
    collecting the response.

    Strategy for greeting detection:
      1. Wait up to 20s for agent to start speaking (first non-silent frame).
      2. Once speech starts, wait GREETING_TAIL_S more seconds for it to
         finish — this is simpler and more reliable than silence counting,
         which is fragile over LiveKit's continuous silent-frame stream.
    """
    GREETING_TAIL_S = 6.0   # seconds to wait after greeting starts before asking

    conn = await _connect_async(agent_id)
    assert conn["token"], "No LiveKit token"
    assert conn["url"].startswith("wss://"), f"Bad url: {conn['url']}"

    from livekit import rtc

    room = rtc.Room()
    agent_frames: list = []
    greeting_started = asyncio.Event()
    collecting = False   # only True after question is fully published

    @room.on("track_subscribed")
    def on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity != "caller":
            stream = rtc.AudioStream(track)
            async def collect():
                async for fe in stream:
                    raw = bytes(fe.frame.data)
                    is_speech = any(b != 0 for b in raw[::50])
                    if is_speech and not greeting_started.is_set():
                        greeting_started.set()
                    if collecting and is_speech:
                        agent_frames.append(fe.frame)
            asyncio.ensure_future(collect())

    await room.connect(conn["url"], conn["token"])

    # Phase 1: wait for greeting to start
    try:
        await asyncio.wait_for(greeting_started.wait(), timeout=GREETING_WAIT_TIMEOUT)
    except asyncio.TimeoutError:
        await room.disconnect()
        raise RuntimeError("Agent did not start greeting within 20s — is the agent worker running?")

    # Phase 2: fixed tail — let the greeting finish
    await asyncio.sleep(GREETING_TAIL_S)

    # Now publish the question — agent has subscribed to our track by now
    source = rtc.AudioSource(sample_rate=48000, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("test-mic", source)
    opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await room.local_participant.publish_track(track, opts)

    # Small delay to ensure agent has subscribed to our newly published track
    await asyncio.sleep(1.0)

    # Start collecting agent response frames now — before we push the question
    # audio. The agent may begin responding partway through (or very shortly
    # after) we finish publishing, so we must not delay setting this flag.
    # collect() only captures non-caller audio so there's no risk of picking
    # up our own mic track.
    collecting = True

    # Push PCM frames
    chunk_bytes = 960
    for i in range(0, len(pcm), chunk_bytes):
        chunk = pcm[i:i + chunk_bytes].ljust(chunk_bytes, b"\x00")
        frame = rtc.AudioFrame(
            data=chunk, sample_rate=48000, num_channels=1, samples_per_channel=480
        )
        await source.capture_frame(frame)
        await asyncio.sleep(0.01)

    # Wait for response frames to arrive (up to 20s)
    deadline = asyncio.get_event_loop().time() + RESPONSE_WAIT_TIMEOUT
    while not agent_frames:
        if asyncio.get_event_loop().time() >= deadline:
            await room.disconnect()
            raise RuntimeError("Agent did not respond to question within 20s")
        await asyncio.sleep(0.5)

    # Drain: wait until frames stop arriving (max 15s)
    last_len = len(agent_frames)
    drain_deadline = asyncio.get_event_loop().time() + MAX_AUDIO_DRAIN_TIMEOUT
    while asyncio.get_event_loop().time() < drain_deadline:
        await asyncio.sleep(2.0)
        if len(agent_frames) == last_len:
            break
        last_len = len(agent_frames)

    await room.disconnect()
    return agent_frames


def test_audio_response(agent_id: str, display_name: str) -> None:
    """Agent responds to 'what is your name?' and mentions its display_name.

    Publishes TTS audio of the question after the greeting has finished,
    then verifies the agent's response audio contains the display_name.
    This confirms the full STT → LLM → TTS pipeline is working end-to-end.
    """
    print("test_audio_response … ", end="", flush=True)
    try:
        import av  # noqa: F401
    except ImportError:
        print("SKIP (av not installed: uv add av)")
        return

    # Generate TTS audio before /connect so room join is immediate.
    mp3 = _tts_question("What is your name?")
    pcm = _mp3_to_pcm48k(mp3)

    # /connect and room.connect() happen together — we are in the room before
    # the hub's 1.5 s dispatch delay fires.
    frames = asyncio.run(_audio_response_flow(agent_id, pcm))
    assert frames, "No audio frames received from agent"

    wav = _frames_to_wav(frames)
    transcript = _transcribe(wav)
    assert transcript.strip(), "Empty transcript — agent did not respond"

    # The agent must mention its display_name in response to "what is your name?"
    # This verifies STT heard the question and LLM generated a relevant response.
    assert display_name.lower() in transcript, (
        f"Agent did not identify itself as {display_name!r} in response.\n"
        f"Transcript: {transcript!r}\n"
        f"This means STT→LLM pipeline is broken or agent answered with wrong name."
    )
    print(f"OK (response: {transcript!r})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _check_env()
    hub_token, agent_id = _load_agent_credentials()

    print(f"Smoke test — hub: {HUB_URL}  agent: {agent_id}\n")

    display_name = test_agent_registered(hub_token)
    test_greeting(agent_id, display_name)
    test_audio_response(agent_id, display_name)

    print("\nAll smoke tests passed ✓")


if __name__ == "__main__":
    main()
