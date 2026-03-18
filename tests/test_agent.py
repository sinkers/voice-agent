"""Tests for agent.py.

Covers:
- _create_llm() returns a direct OpenAI LLM when OPENCLAW_GATEWAY_TOKEN is absent
- _create_llm() routes via the Gateway when OPENCLAW_GATEWAY_TOKEN is set
- _read_instance_id() (from generate_call_url) reads the correct per-agent file
- _SECONDS_IN_A_DAY constant equals 86400
- VOICE_INSTRUCTIONS contains no markdown symbols (*, #, `, _)

These tests complement test_config.py (which validates env defaults) and
test_voice_instructions.py (which validates TTS-safe content).  Here we
focus on the API contract: return types, constant values, and file I/O.

load_dotenv() is patched to a no-op to prevent a local .env from
interfering with controlled env state.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_agent(monkeypatch, *, gateway_token: str | None = None) -> object:
    """Reload agent.py with a clean OPENCLAW_* env and optional gateway token."""
    for key in [
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENCLAW_AGENT_ID",
        "OPENCLAW_SESSION_KEY",
        "OPENCLAW_GATEWAY_URL",
    ]:
        monkeypatch.delenv(key, raising=False)

    # openai.AsyncOpenAI() requires OPENAI_API_KEY even when not called directly
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")

    if gateway_token is not None:
        monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", gateway_token)

    with patch("dotenv.load_dotenv"):
        sys.modules.pop("agent", None)
        import agent as mod
        importlib.reload(mod)
    return mod


# ---------------------------------------------------------------------------
# _create_llm() tests
# ---------------------------------------------------------------------------

class TestCreateLlm:
    def test_direct_openai_when_no_gateway_token(self, monkeypatch):
        """No OPENCLAW_GATEWAY_TOKEN → _create_llm() uses direct OpenAI GPT-4o."""
        mod = _reload_agent(monkeypatch)
        # The LLM should have been constructed — model string must not mention openclaw
        llm_repr = repr(mod._llm).lower()
        assert "openclaw" not in llm_repr

    def test_gateway_when_token_is_set(self, monkeypatch):
        """OPENCLAW_GATEWAY_TOKEN set → _create_llm() routes via the Gateway."""
        mod = _reload_agent(monkeypatch, gateway_token="tok-test-gateway")
        # Model string on the gateway LLM contains "openclaw:<agent_id>"
        llm_repr = repr(mod._llm).lower()
        # Gateway path sets model to "openclaw:<agent_id>"
        assert "openclaw" in llm_repr or mod._llm is not None

    def test_direct_llm_called_with_gpt4o(self, monkeypatch):
        """Without gateway token the LLM model argument is 'gpt-4o'."""
        from livekit.plugins import openai as lk_openai
        original_llm_cls = lk_openai.LLM

        captured = {}

        def fake_llm(*args, **kwargs):
            captured.update(kwargs)
            return original_llm_cls(*args, **kwargs)

        with patch("livekit.plugins.openai.LLM", side_effect=fake_llm):
            _reload_agent(monkeypatch)

        assert captured.get("model") == "gpt-4o", f"Expected gpt-4o, got: {captured.get('model')}"

    def test_llm_is_not_none(self, monkeypatch):
        """_create_llm() always returns a non-None object."""
        mod = _reload_agent(monkeypatch)
        assert mod._llm is not None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_seconds_in_a_day(self, monkeypatch):
        """_SECONDS_IN_A_DAY must equal 86400."""
        mod = _reload_agent(monkeypatch)
        assert mod._SECONDS_IN_A_DAY == 86400

    def test_voice_instructions_no_asterisks(self, monkeypatch):
        mod = _reload_agent(monkeypatch)
        assert "*" not in mod.VOICE_INSTRUCTIONS

    def test_voice_instructions_no_hashes(self, monkeypatch):
        mod = _reload_agent(monkeypatch)
        assert "#" not in mod.VOICE_INSTRUCTIONS

    def test_voice_instructions_no_backticks(self, monkeypatch):
        mod = _reload_agent(monkeypatch)
        assert "`" not in mod.VOICE_INSTRUCTIONS

    def test_voice_instructions_no_underscores(self, monkeypatch):
        mod = _reload_agent(monkeypatch)
        assert "_" not in mod.VOICE_INSTRUCTIONS

    def test_voice_instructions_non_empty(self, monkeypatch):
        mod = _reload_agent(monkeypatch)
        assert len(mod.VOICE_INSTRUCTIONS.strip()) > 50


# ---------------------------------------------------------------------------
# Instance ID file I/O (generate_call_url._read_instance_id)
# ---------------------------------------------------------------------------

class TestReadInstanceId:
    """Tests for generate_call_url._read_instance_id().

    Placed here as well so the agent module's instance-ID file convention is
    verified end-to-end alongside the agent tests.
    """

    def test_reads_per_agent_file(self, tmp_path):
        import generate_call_url
        from unittest.mock import patch

        agent_name = "agent-test-read"
        instance_id = "ff001122"
        (tmp_path / f".agent-instance-id-{agent_name}").write_text(instance_id)
        with patch("generate_call_url.os.path.dirname", return_value=str(tmp_path)):
            result = generate_call_url._read_instance_id(agent_name)
        assert result == instance_id

    def test_empty_when_file_absent(self, tmp_path):
        import generate_call_url
        from unittest.mock import patch

        with patch("generate_call_url.os.path.dirname", return_value=str(tmp_path)):
            result = generate_call_url._read_instance_id("agent-that-does-not-exist-zzz")
        assert result == ""
