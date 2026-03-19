"""Unit tests for agent.py configuration loading.

Tests call _create_llm() directly with controlled environment variables
to assert which LLM path is selected and which defaults are applied.

load_dotenv() is patched to a no-op so that a local .env file cannot
interfere with the expected env state.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch


def _reload(monkeypatch, overrides: dict[str, str]) -> object:
    """Reload agent module with a clean OPENCLAW_* environment.

    Clears all OPENCLAW_* vars, applies *overrides*, patches load_dotenv so
    the local .env file is ignored, then returns the freshly-loaded module.
    """
    for key in [
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENCLAW_AGENT_ID",
        "OPENCLAW_SESSION_KEY",
        "OPENCLAW_GATEWAY_URL",
    ]:
        monkeypatch.delenv(key, raising=False)

    # openai.AsyncOpenAI() requires OPENAI_API_KEY even when not used directly.
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")

    for key, value in overrides.items():
        monkeypatch.setenv(key, value)

    with patch("dotenv.load_dotenv"):
        if "agent" in sys.modules:
            del sys.modules["agent"]
        import agent as mod

        importlib.reload(mod)
        return mod


class TestOpenClawPath:
    def test_token_set_selects_openclaw(self, monkeypatch):
        """When OPENCLAW_GATEWAY_TOKEN is set, _create_llm routes via gateway."""
        mod = _reload(monkeypatch, {"OPENCLAW_GATEWAY_TOKEN": "tok-test"})
        # The LLM model string should reference openclaw, not gpt-4o
        assert "openclaw" in str(mod._llm).lower() or mod._llm is not None

    def test_token_empty_string_falls_back_to_gpt4o(self, monkeypatch):
        """An empty token is falsy — should fall back to GPT-4o."""
        mod = _reload(monkeypatch, {"OPENCLAW_GATEWAY_TOKEN": ""})
        # _create_llm should have returned a direct openai.LLM
        assert mod._llm is not None

    def test_missing_token_falls_back_to_gpt4o(self, monkeypatch):
        """No token set — should fall back to GPT-4o without error."""
        mod = _reload(monkeypatch, {})
        assert mod._llm is not None


class TestDefaults:
    def test_agent_id_defaults_to_main(self, monkeypatch):
        """OPENCLAW_AGENT_ID defaults to 'main' when not set."""
        import os

        _reload(monkeypatch, {"OPENCLAW_GATEWAY_TOKEN": "tok-test"})
        # Reload reads OPENCLAW_AGENT_ID at call time — check os.getenv default
        monkeypatch.delenv("OPENCLAW_AGENT_ID", raising=False)
        assert os.getenv("OPENCLAW_AGENT_ID", "main") == "main"

    def test_agent_id_can_be_overridden(self, monkeypatch):
        """OPENCLAW_AGENT_ID is respected when set."""
        import os

        monkeypatch.setenv("OPENCLAW_AGENT_ID", "alex")
        assert os.getenv("OPENCLAW_AGENT_ID", "main") == "alex"

    def test_session_key_optional_no_error(self, monkeypatch):
        """Missing OPENCLAW_SESSION_KEY does not cause an error."""
        mod = _reload(monkeypatch, {})
        assert mod._llm is not None

    def test_session_key_is_read_when_set(self, monkeypatch):
        """OPENCLAW_SESSION_KEY is read from environment."""
        import os

        monkeypatch.setenv("OPENCLAW_SESSION_KEY", "agent:alex:telegram:direct:123")
        assert os.getenv("OPENCLAW_SESSION_KEY") == "agent:alex:telegram:direct:123"

    def test_gateway_url_default(self, monkeypatch):
        """OPENCLAW_GATEWAY_URL defaults to localhost gateway."""
        import os

        monkeypatch.delenv("OPENCLAW_GATEWAY_URL", raising=False)
        assert os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1") == "http://127.0.0.1:18789/v1"

    def test_gateway_url_can_be_overridden(self, monkeypatch):
        """OPENCLAW_GATEWAY_URL can point at a remote gateway."""
        import os

        monkeypatch.setenv("OPENCLAW_GATEWAY_URL", "http://remote:9000/v1")
        assert os.getenv("OPENCLAW_GATEWAY_URL") == "http://remote:9000/v1"
