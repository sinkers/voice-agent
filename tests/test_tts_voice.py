"""Tests for TTS voice configuration.

Validates that OPENAI_TTS_VOICE environment variable is respected.
"""

from __future__ import annotations

import os


class TestTTSVoiceConfig:
    def test_voice_defaults_to_alloy_when_not_set(self, monkeypatch):
        """TTS voice should default to 'alloy' when OPENAI_TTS_VOICE is not set."""
        monkeypatch.delenv("OPENAI_TTS_VOICE", raising=False)
        voice = os.getenv("OPENAI_TTS_VOICE", "alloy")
        assert voice == "alloy"

    def test_voice_can_be_overridden(self, monkeypatch):
        """OPENAI_TTS_VOICE can be set to any valid OpenAI voice."""
        test_voices = ["echo", "fable", "onyx", "nova", "shimmer"]

        for test_voice in test_voices:
            monkeypatch.setenv("OPENAI_TTS_VOICE", test_voice)
            voice = os.getenv("OPENAI_TTS_VOICE", "alloy")
            assert voice == test_voice, f"Failed to override voice to {test_voice}"

    def test_env_example_documents_all_voices(self):
        """env.example should document all available OpenAI TTS voices."""
        with open(".env.example") as f:
            env_example = f.read()

        expected_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

        for voice in expected_voices:
            assert voice in env_example, f"Voice '{voice}' not documented in .env.example"

    def test_skill_env_example_documents_voices(self):
        """skill/assets/agent/env.example should also document voices."""
        with open("skill/assets/agent/env.example") as f:
            skill_env = f.read()

        expected_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

        for voice in expected_voices:
            assert voice in skill_env, f"Voice '{voice}' not documented in skill env.example"

    def test_env_example_has_tts_voice_setting(self):
        """env.example should have OPENAI_TTS_VOICE setting."""
        with open(".env.example") as f:
            env_example = f.read()
        assert "OPENAI_TTS_VOICE" in env_example
        assert "OPENAI_TTS_VOICE=alloy" in env_example

    def test_skill_env_example_has_tts_voice_setting(self):
        """skill env.example should have OPENAI_TTS_VOICE setting."""
        with open("skill/assets/agent/env.example") as f:
            skill_env = f.read()
        assert "OPENAI_TTS_VOICE" in skill_env
        assert "OPENAI_TTS_VOICE=alloy" in skill_env
