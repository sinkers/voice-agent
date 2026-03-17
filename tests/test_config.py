"""Unit tests for agent.py configuration loading.

Each test reloads the agent module with a controlled env so we can assert
which LLM path was selected and which defaults were applied.

load_dotenv() is patched to a no-op so that a local .env file cannot
interfere with the expected env state.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch


def _reload(monkeypatch, overrides: dict[str, str]) -> object:
    """Reload agent with a clean OPENCLAW_* environment.

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

    # openai.AsyncClient() requires OPENAI_API_KEY even when we don't use it directly.
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
        mod = _reload(monkeypatch, {"OPENCLAW_GATEWAY_TOKEN": "tok-test"})
        assert mod._USE_OPENCLAW is True

    def test_token_empty_string_treated_as_falsy(self, monkeypatch):
        mod = _reload(monkeypatch, {"OPENCLAW_GATEWAY_TOKEN": ""})
        assert mod._USE_OPENCLAW is False

    def test_missing_token_falls_back_to_gpt4o(self, monkeypatch):
        mod = _reload(monkeypatch, {})
        assert mod._USE_OPENCLAW is False


class TestDefaults:
    def test_agent_id_defaults_to_main(self, monkeypatch):
        mod = _reload(monkeypatch, {})
        assert mod._OPENCLAW_AGENT_ID == "main"

    def test_agent_id_can_be_overridden(self, monkeypatch):
        mod = _reload(monkeypatch, {"OPENCLAW_AGENT_ID": "alex"})
        assert mod._OPENCLAW_AGENT_ID == "alex"

    def test_session_key_optional_no_error(self, monkeypatch):
        mod = _reload(monkeypatch, {})
        assert mod._OPENCLAW_SESSION_KEY is None

    def test_session_key_is_read_when_set(self, monkeypatch):
        mod = _reload(monkeypatch, {"OPENCLAW_SESSION_KEY": "sess-abc"})
        assert mod._OPENCLAW_SESSION_KEY == "sess-abc"

    def test_gateway_url_default(self, monkeypatch):
        mod = _reload(monkeypatch, {})
        assert mod._OPENCLAW_URL == "http://127.0.0.1:18789/v1"

    def test_gateway_url_can_be_overridden(self, monkeypatch):
        mod = _reload(monkeypatch, {"OPENCLAW_GATEWAY_URL": "http://remote:9000/v1"})
        assert mod._OPENCLAW_URL == "http://remote:9000/v1"
