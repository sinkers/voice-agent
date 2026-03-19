"""Integration tests for OpenClaw Gateway connectivity.

These tests are skipped unless OPENCLAW_GATEWAY_TOKEN is set in the
environment.  Run them with:

    make test-all
    # or
    pytest -m integration
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN")
GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1")

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_token():
    if not GATEWAY_TOKEN:
        pytest.skip("OPENCLAW_GATEWAY_TOKEN not set — skipping integration tests")


def _request(path: str, token: str | None, method: str = "GET", body: bytes | None = None):
    """Make a simple HTTP request; return (status_code, body_bytes)."""
    url = GATEWAY_URL.rstrip("/") + path
    req = urllib.request.Request(url, method=method, data=body)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class TestGatewayReachability:
    def test_endpoint_is_reachable(self):
        """Any HTTP response (even 401) means the gateway is up."""
        try:
            status, _ = _request("/models", token=GATEWAY_TOKEN)
        except OSError as exc:
            pytest.fail(f"Gateway unreachable at {GATEWAY_URL}: {exc}")
        assert isinstance(status, int), "Expected an HTTP status code"

    def test_models_endpoint_returns_200_with_valid_token(self):
        status, _ = _request("/models", token=GATEWAY_TOKEN)
        assert status == 200, f"Expected 200 from /models, got {status}"


class TestGatewayAuth:
    def test_invalid_token_returns_401(self):
        payload = json.dumps(
            {
                "model": "openclaw:main",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
        ).encode()
        status, _ = _request(
            "/chat/completions",
            token="invalid-token-xyz",
            method="POST",
            body=payload,
        )
        assert status == 401, f"Expected 401 for bad token, got {status}"

    def test_valid_token_does_not_return_401(self):
        payload = json.dumps(
            {
                "model": "openclaw:main",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
        ).encode()
        status, _ = _request(
            "/chat/completions",
            token=GATEWAY_TOKEN,
            method="POST",
            body=payload,
        )
        assert status != 401, "Valid token was rejected (got 401)"
