"""Tests for web/backend/main.py (FastAPI backend).

Covers:
- GET /agents returns the configured agent list
- POST /connect with valid token returns room/token/url/dispatch_id
- POST /connect with expired token returns 401
- POST /connect with wrong secret returns 401
- POST /connect with missing agent_name returns 400
- POST /connect with missing env vars at startup raises RuntimeError
- Optional LiveKit creds in the JWT override server defaults

LiveKitAPI and AccessToken are mocked throughout — no real network calls.

NOTE: These tests require fastapi and httpx to be installed.  Run them via
the backend project's own venv or after ``pip install fastapi httpx``.
They are automatically skipped when those packages are absent.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

# Skip the entire module when the backend dependencies aren't installed.
fastapi = pytest.importorskip("fastapi", reason="fastapi not installed — skipping backend tests")
pytest.importorskip("httpx", reason="httpx not installed — skipping backend tests")

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# conftest.py has already set env vars and added web/backend to sys.path.
import main as _main_module
from main import app

CONFIG_SECRET = "test-config-secret-abc-32bytes-padding"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(payload_extra: dict | None = None, secret: str = CONFIG_SECRET, ttl: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "agent_name": "voice-agent-abc12345",
        "display_name": "Voice Agent",
        "iat": now,
        "exp": now + ttl,
    }
    if payload_extra:
        payload.update(payload_extra)
    return jwt.encode(payload, secret, algorithm="HS256")


def _expired_token() -> str:
    return _make_token(ttl=-10)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /agents
# ---------------------------------------------------------------------------

class TestListAgents:
    def test_returns_empty_list_by_default(self, client, monkeypatch):
        monkeypatch.setattr(_main_module, "LIVEKIT_AGENTS", [])
        resp = client.get("/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_configured_agents(self, client, monkeypatch):
        agents = [{"id": "voice-agent", "name": "Voice Agent"}]
        monkeypatch.setattr(_main_module, "LIVEKIT_AGENTS", agents)
        resp = client.get("/agents")
        assert resp.status_code == 200
        assert resp.json() == agents


# ---------------------------------------------------------------------------
# POST /connect — success path
# ---------------------------------------------------------------------------

class TestConnect:
    def test_valid_token_returns_200(self, client, mock_livekit_api, mock_access_token):
        mock_lk_cls, mock_dispatch = mock_livekit_api
        with patch("main.LiveKitAPI", mock_lk_cls), \
             patch("main.AccessToken", mock_access_token), \
             patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET):
            resp = client.post("/connect", json={"config_token": _make_token()})
        assert resp.status_code == 200

    def test_valid_token_response_fields(self, client, mock_livekit_api, mock_access_token):
        mock_lk_cls, mock_dispatch = mock_livekit_api
        with patch("main.LiveKitAPI", mock_lk_cls), \
             patch("main.AccessToken", mock_access_token), \
             patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET):
            resp = client.post("/connect", json={"config_token": _make_token()})
        body = resp.json()
        assert "token" in body
        assert "url" in body
        assert "room_name" in body
        assert "dispatch_id" in body
        assert "agent" in body
        assert body["agent"]["id"] == "voice-agent-abc12345"

    def test_dispatch_id_matches_mock(self, client, mock_livekit_api, mock_access_token):
        mock_lk_cls, mock_dispatch = mock_livekit_api
        with patch("main.LiveKitAPI", mock_lk_cls), \
             patch("main.AccessToken", mock_access_token), \
             patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET):
            resp = client.post("/connect", json={"config_token": _make_token()})
        assert resp.json()["dispatch_id"] == mock_dispatch.id

    def test_livekit_api_called_with_server_defaults(self, client, mock_livekit_api, mock_access_token):
        mock_lk_cls, _ = mock_livekit_api
        with patch("main.LiveKitAPI", mock_lk_cls), \
             patch("main.AccessToken", mock_access_token), \
             patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET), \
             patch.object(_main_module, "LIVEKIT_URL", "wss://test.livekit.local"), \
             patch.object(_main_module, "LIVEKIT_API_KEY", "test-api-key"), \
             patch.object(_main_module, "LIVEKIT_API_SECRET", "test-api-secret"):
            client.post("/connect", json={"config_token": _make_token()})
        mock_lk_cls.assert_called_once_with(
            url="wss://test.livekit.local",
            api_key="test-api-key",
            api_secret="test-api-secret",
        )


# ---------------------------------------------------------------------------
# POST /connect — error paths
# ---------------------------------------------------------------------------

class TestConnectErrors:
    def test_expired_token_returns_401(self, client):
        with patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET):
            resp = client.post("/connect", json={"config_token": _expired_token()})
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    def test_wrong_secret_returns_401(self, client):
        bad_token = jwt.encode(
            {"agent_name": "voice-agent", "exp": int(time.time()) + 3600},
            "WRONG-SECRET",
            algorithm="HS256",
        )
        with patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET):
            resp = client.post("/connect", json={"config_token": bad_token})
        assert resp.status_code == 401

    def test_missing_agent_name_returns_400(self, client):
        token = jwt.encode(
            {"display_name": "No Agent", "exp": int(time.time()) + 3600},
            CONFIG_SECRET,
            algorithm="HS256",
        )
        with patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET):
            resp = client.post("/connect", json={"config_token": token})
        assert resp.status_code == 400
        assert "agent_name" in resp.json()["detail"].lower()

    def test_config_secret_not_set_returns_503(self, client):
        with patch.object(_main_module, "CONFIG_SECRET", ""):
            resp = client.post("/connect", json={"config_token": "any-token"})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /connect — per-token LiveKit credential override
# ---------------------------------------------------------------------------

class TestConnectPerTokenCreds:
    def test_per_token_creds_override_server_defaults(self, client, mock_livekit_api, mock_access_token):
        mock_lk_cls, _ = mock_livekit_api
        token = _make_token({
            "livekit_url": "wss://override.livekit.cloud",
            "livekit_api_key": "override-key",
            "livekit_api_secret": "override-secret",
        })
        with patch("main.LiveKitAPI", mock_lk_cls), \
             patch("main.AccessToken", mock_access_token), \
             patch.object(_main_module, "CONFIG_SECRET", CONFIG_SECRET):
            resp = client.post("/connect", json={"config_token": token})
        assert resp.status_code == 200
        # LiveKitAPI must have been called with the per-token creds
        mock_lk_cls.assert_called_once_with(
            url="wss://override.livekit.cloud",
            api_key="override-key",
            api_secret="override-secret",
        )
        # The returned url should reflect the per-token livekit_url
        assert resp.json()["url"] == "wss://override.livekit.cloud"


# ---------------------------------------------------------------------------
# Startup: missing env vars
# ---------------------------------------------------------------------------

class TestMissingEnvVars:
    def test_missing_env_vars_raises_runtime_error(self):
        """_check_required_env raises RuntimeError when vars are absent."""
        import main as m
        with pytest.raises(RuntimeError, match="Missing required environment variables"):
            m._check_required_env({"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""})

    def test_partial_missing_raises(self):
        """_check_required_env raises when only some vars are set."""
        import main as m
        with pytest.raises(RuntimeError, match="LIVEKIT_API_SECRET"):
            m._check_required_env({"LIVEKIT_URL": "wss://x", "LIVEKIT_API_KEY": "key", "LIVEKIT_API_SECRET": ""})

    def test_all_present_does_not_raise(self):
        """_check_required_env passes when all vars are set."""
        import main as m
        m._check_required_env({"LIVEKIT_URL": "wss://x", "LIVEKIT_API_KEY": "key", "LIVEKIT_API_SECRET": "secret"})


# ---------------------------------------------------------------------------
# Async client smoke test (httpx AsyncClient)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agents_async_client(mock_livekit_api):
    monkeypatch_agents = [{"id": "agent-1", "name": "Agent One"}]
    _main_module.LIVEKIT_AGENTS = monkeypatch_agents
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/agents")
    _main_module.LIVEKIT_AGENTS = []
    assert resp.status_code == 200
    assert resp.json() == monkeypatch_agents
