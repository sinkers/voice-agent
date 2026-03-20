"""Tests for hub authentication and configuration flow.

These tests verify that the agent handles first-run scenarios and hub
communication errors correctly.
"""

from unittest.mock import Mock, patch

import httpx
import pytest


class TestHubFirstRun:
    """Test first-run scenario when agent is not yet registered with hub."""

    @patch("agent.httpx.Client")
    @patch("agent.os.getenv")
    def test_handles_404_no_agent_registered(self, mock_getenv, mock_client):
        """On first run, 404 from /agent/config should use .env values."""
        from agent import _hub_get_config

        # Mock environment variables
        mock_getenv.side_effect = lambda key, default="": {
            "LIVEKIT_URL": "wss://test.livekit.cloud",
            "LIVEKIT_API_KEY": "test_key",
            "LIVEKIT_API_SECRET": "test_secret",
            "DEEPGRAM_API_KEY": "test_deepgram",
            "OPENAI_API_KEY": "test_openai",
        }.get(key, default)

        # Mock HTTP response - 404 with "No agent registered"
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = '{"detail":"No agent registered"}'
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=Mock(), response=mock_response
        )
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        # Should raise RuntimeError with 404 message
        with pytest.raises(RuntimeError) as exc_info:
            _hub_get_config("https://test-hub.com", "test_token", "test-agent")

        assert "404" in str(exc_info.value)
        assert "No agent registered" in str(exc_info.value)

    @patch("agent.httpx.Client")
    def test_handles_valid_config_response(self, mock_client):
        """When agent is registered, config is returned successfully."""
        from agent import _hub_get_config

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "livekit_url": "wss://prod.livekit.cloud",
            "livekit_api_key": "prod_key",
            "livekit_api_secret": "prod_secret",
            "deepgram_api_key": "prod_deepgram",
            "openai_api_key": "prod_openai",
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        config = _hub_get_config("https://test-hub.com", "test_token", "test-agent")

        assert config["livekit_url"] == "wss://prod.livekit.cloud"
        assert config["livekit_api_key"] == "prod_key"

    @patch("agent.httpx.Client")
    def test_handles_401_invalid_token(self, mock_client):
        """401 response should delete token file and raise ValueError."""
        import os
        import tempfile

        from agent import _hub_get_config

        # Create a temp token file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="-test-agent") as f:
            token_file = f.name
            f.write("invalid_token")

        try:
            # Mock 401 response
            mock_response = Mock()
            mock_response.status_code = 401
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            # Patch the token file path
            with (
                patch("agent.os.path.join", return_value=token_file),
                pytest.raises(ValueError) as exc_info,
            ):
                _hub_get_config("https://test-hub.com", "invalid_token", "test-agent")

            assert "invalid or expired" in str(exc_info.value)
        finally:
            # Cleanup
            if os.path.exists(token_file):
                os.remove(token_file)

    @patch("agent.httpx.Client")
    def test_handles_network_error(self, mock_client):
        """Network errors should be retried then raise ConnectError."""
        from agent import _hub_get_config

        # Mock connection error - will be retried 3 times
        mock_client.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError("Connection refused")

        # After retries are exhausted, ConnectError is raised
        with pytest.raises(httpx.ConnectError) as exc_info:
            _hub_get_config("https://test-hub.com", "test_token", "test-agent")

        assert "Connection refused" in str(exc_info.value)
        # Verify it was retried (3 attempts total)
        assert mock_client.return_value.__enter__.return_value.get.call_count == 3

    @patch("agent.httpx.Client")
    def test_handles_timeout(self, mock_client):
        """Timeout errors should raise RuntimeError with timeout message."""
        from agent import _hub_get_config

        # Mock timeout
        mock_client.return_value.__enter__.return_value.get.side_effect = httpx.TimeoutException("Request timed out")

        with pytest.raises(RuntimeError) as exc_info:
            _hub_get_config("https://test-hub.com", "test_token", "test-agent")

        assert "timed out" in str(exc_info.value).lower()

    @patch("agent.httpx.Client")
    def test_handles_invalid_json_response(self, mock_client):
        """Invalid JSON in response should raise RuntimeError."""
        from agent import _hub_get_config

        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = Exception("Invalid JSON")
        mock_response.text = "not json"
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        with pytest.raises(RuntimeError) as exc_info:
            _hub_get_config("https://test-hub.com", "test_token", "test-agent")

        assert "Failed to parse" in str(exc_info.value)
