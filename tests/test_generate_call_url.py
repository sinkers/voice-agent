"""Tests for generate_call_url.py.

Covers:
- generate_url() produces a valid JWT with correct fields
- JWT decodes correctly with CONFIG_SECRET
- agent_name gets instance_id suffix appended
- expired token is rejected on decode
- missing CONFIG_SECRET raises ValueError
- per-agent instance ID file is read correctly
- LiveKit creds are included in payload when provided
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest

import generate_call_url

SECRET = "test-config-secret-abc-32bytes-padding"
BASE_URL = "https://voice-agent-web.fly.dev"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate(agent_name="voice-agent", display_name="Voice Agent", **kwargs):
    """Call generate_url() with CONFIG_SECRET patched to SECRET."""
    with patch.object(generate_call_url, "CONFIG_SECRET", SECRET):
        with patch.object(generate_call_url, "CALL_BASE_URL", BASE_URL):
            return generate_call_url.generate_url(
                agent_name=agent_name,
                display_name=display_name,
                **kwargs,
            )


def _extract_token(url: str) -> str:
    """Pull the JWT from the URL query string."""
    assert "?token=" in url
    return url.split("?token=")[1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateUrl:
    def test_returns_url_string(self):
        url = _generate()
        assert url.startswith(BASE_URL)

    def test_jwt_has_correct_fields(self):
        url = _generate(agent_name="my-agent", display_name="My Agent")
        token = _extract_token(url)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["display_name"] == "My Agent"
        assert "iat" in payload
        assert "exp" in payload

    def test_jwt_decodes_with_config_secret(self):
        url = _generate()
        token = _extract_token(url)
        # Should not raise
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert isinstance(payload, dict)

    def test_expiry_is_in_the_future(self):
        url = _generate(ttl_seconds=3600)
        token = _extract_token(url)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["exp"] > int(time.time())

    def test_agent_name_gets_instance_id_suffix(self, monkeypatch):
        """When OPENCLAW_INSTANCE_ID is set the agent_name gains the suffix."""
        monkeypatch.setenv("OPENCLAW_INSTANCE_ID", "abc12345")
        url = _generate(agent_name="voice-agent")
        token = _extract_token(url)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["agent_name"] == "voice-agent-abc12345"

    def test_no_double_suffix(self, monkeypatch):
        """Instance ID is not appended twice if agent_name already ends with it."""
        monkeypatch.setenv("OPENCLAW_INSTANCE_ID", "abc12345")
        url = _generate(agent_name="voice-agent-abc12345")
        token = _extract_token(url)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["agent_name"] == "voice-agent-abc12345"

    def test_expired_token_rejected(self):
        url = _generate(ttl_seconds=-1)
        token = _extract_token(url)
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, SECRET, algorithms=["HS256"])

    def test_missing_config_secret_raises(self):
        with patch.object(generate_call_url, "CONFIG_SECRET", ""):
            with pytest.raises(ValueError, match="CONFIG_SECRET is not set"):
                generate_call_url.generate_url("agent", "Agent")

    def test_livekit_creds_in_payload(self):
        url = _generate(
            livekit_url="wss://other.livekit.cloud",
            livekit_api_key="key-123",
            livekit_api_secret="secret-456",
        )
        token = _extract_token(url)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["livekit_url"] == "wss://other.livekit.cloud"
        assert payload["livekit_api_key"] == "key-123"
        assert payload["livekit_api_secret"] == "secret-456"

    def test_livekit_creds_omitted_when_not_provided(self):
        url = _generate()
        token = _extract_token(url)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert "livekit_url" not in payload
        assert "livekit_api_key" not in payload
        assert "livekit_api_secret" not in payload


class TestReadInstanceId:
    def test_reads_per_agent_file(self, tmp_path):
        """_read_instance_id reads from .agent-instance-id-{agent_name}."""
        agent_name = "test-reader"
        instance_id = "deadbeef"
        (tmp_path / f".agent-instance-id-{agent_name}").write_text(instance_id)
        with patch("generate_call_url.os.path.dirname", return_value=str(tmp_path)):
            result = generate_call_url._read_instance_id(agent_name)
        assert result == instance_id

    def test_falls_back_to_legacy_file(self, tmp_path):
        """_read_instance_id falls back to .agent-instance-id if per-agent file absent."""
        (tmp_path / ".agent-instance-id").write_text("legacy99")
        with patch("generate_call_url.os.path.dirname", return_value=str(tmp_path)):
            result = generate_call_url._read_instance_id("no-such-agent")
        assert result == "legacy99"

    def test_returns_empty_string_when_no_files(self, tmp_path):
        """_read_instance_id returns '' when neither file exists."""
        with patch("generate_call_url.os.path.dirname", return_value=str(tmp_path)):
            result = generate_call_url._read_instance_id("no-such-agent-xyz")
        assert result == ""

    def test_strips_whitespace(self, tmp_path):
        """_read_instance_id strips trailing whitespace from the file contents."""
        agent_name = "strip-test"
        (tmp_path / f".agent-instance-id-{agent_name}").write_text("abc123  \n")
        with patch("generate_call_url.os.path.dirname", return_value=str(tmp_path)):
            result = generate_call_url._read_instance_id(agent_name)
        assert result == "abc123"
