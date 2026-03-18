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
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
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
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
    chunks = []
    for frame in container.decode(audio=0):
        for rf in resampler.resample(frame):
            chunks.append(bytes(rf.planes[0]))
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# LiveKit room helpers
# ---------------------------------------------------------------------------

async def _collect_agent_audio(lk_token: str, lk_url: str,
                                wait_for_speech_s: float = 20.0,
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
                    agent_frames.append(fe.frame)
                    if not agent_speaking.is_set():
                        raw = bytes(fe.frame.data)
                        if any(b != 0 for b in raw[::50]):
                            agent_speaking.set()
            asyncio.ensure_future(collect())

    await room.connect(lk_url, lk_token)

    # Publish question audio if provided
    if pcm_to_publish:
        source = rtc.AudioSource(sample_rate=48000, num_channels=1)
        track = rtc.LocalAudioTrack.create_audio_track("test-mic", source)
        opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(track, opts)
        # Push PCM frames (10ms chunks at 48kHz = 480 samples = 960 bytes)
        chunk_bytes = 960
        for i in range(0, len(pcm_to_publish), chunk_bytes):
            chunk = pcm_to_publish[i:i + chunk_bytes]
            chunk = chunk.ljust(chunk_bytes, b'\x00')
            frame = rtc.AudioFrame(
                data=chunk,
                sample_rate=48000,
                num_channels=1,
                samples_per_channel=480,
            )
            await source.capture_frame(frame)
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(agent_speaking.wait(), timeout=wait_for_speech_s)
    except asyncio.TimeoutError:
        await room.disconnect()
        raise RuntimeError(f"Agent did not speak within {wait_for_speech_s:.0f}s — is the agent worker running?")

    # Drain until silence
    last_len = len(agent_frames)
    while True:
        await asyncio.sleep(drain_silence_s)
        if len(agent_frames) == last_len:
            break
        last_len = len(agent_frames)

    await room.disconnect()
    return agent_frames


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


def test_greeting(agent_id: str, display_name: str) -> None:
    """Agent joins room and greets with its configured display_name."""
    print("test_greeting … ", end="", flush=True)
    conn = _connect(agent_id)
    assert conn["token"], "No LiveKit token"
    assert conn["url"].startswith("wss://"), f"Bad url: {conn['url']}"

    frames = asyncio.run(_collect_agent_audio(conn["token"], conn["url"]))
    assert frames, "No audio frames received"

    wav = _frames_to_wav(frames)
    transcript = _transcribe(wav)
    assert display_name.lower() in transcript, \
        f"display_name {display_name!r} not in greeting transcript: {transcript!r}"
    print(f"OK (transcript: {transcript!r})")


def test_audio_response(agent_id: str) -> None:
    """Agent responds to a spoken question with relevant audio."""
    print("test_audio_response … ", end="", flush=True)
    try:
        import av  # noqa: F401
    except ImportError:
        print("SKIP (av not installed: uv add av)")
        return

    conn = _connect(agent_id)

    mp3 = _tts_question("What is your name?")
    pcm = _mp3_to_pcm48k(mp3)

    frames = asyncio.run(_collect_agent_audio(
        conn["token"], conn["url"],
        wait_for_speech_s=30.0,
        pcm_to_publish=pcm,
    ))
    assert frames, "No audio frames received from agent"

    wav = _frames_to_wav(frames)
    transcript = _transcribe(wav)
    assert transcript.strip(), f"Empty transcript — agent did not respond"
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
    test_audio_response(agent_id)

    print("\nAll smoke tests passed ✓")


if __name__ == "__main__":
    main()
