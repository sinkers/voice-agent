"""Tests for the VOICE_INSTRUCTIONS constant.

These ensure the instructions stay safe for TTS: no markdown symbols,
no bullet lists, no URLs.
"""

from __future__ import annotations

import re
import sys
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def voice_instructions(monkeypatch_module) -> str:
    # openai.AsyncClient() requires OPENAI_API_KEY at import time.
    monkeypatch_module.setenv("OPENAI_API_KEY", "test-dummy-key")
    with patch("dotenv.load_dotenv"):
        if "agent" in sys.modules:
            import importlib
            import agent
            importlib.reload(agent)
        else:
            import agent
    return agent.VOICE_INSTRUCTIONS


@pytest.fixture(scope="module")
def monkeypatch_module(request):
    """Module-scoped monkeypatch (pytest's built-in is function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


class TestNoMarkdown:
    def test_no_asterisks(self, voice_instructions):
        assert "*" not in voice_instructions

    def test_no_hashes(self, voice_instructions):
        assert "#" not in voice_instructions

    def test_no_backticks(self, voice_instructions):
        assert "`" not in voice_instructions

    def test_no_underscores(self, voice_instructions):
        assert "_" not in voice_instructions


class TestRequiredContent:
    def test_mentions_voice_call(self, voice_instructions):
        assert "voice call" in voice_instructions.lower()

    def test_instructs_against_bullet_points(self, voice_instructions):
        text = voice_instructions.lower()
        assert "bullet" in text or "list" in text

    def test_instructs_against_urls(self, voice_instructions):
        assert "url" in voice_instructions.lower()

    def test_not_empty(self, voice_instructions):
        assert len(voice_instructions.strip()) > 100
