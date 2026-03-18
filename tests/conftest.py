"""Shared test configuration for the livekit-agent test suite.

This module is loaded by pytest before any test file.  It:

1. Adds the project root and web/backend to sys.path so tests can import
   source modules without installation.
2. Sets the required environment variables that main.py checks at import
   time, so test_backend.py can import the FastAPI app without crashing.
3. Provides shared fixtures used across multiple test files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Source roots
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web" / "backend"))

# ---------------------------------------------------------------------------
# Required env vars for web/backend/main.py (checked at module import time)
# ---------------------------------------------------------------------------
os.environ.setdefault("LIVEKIT_URL", "wss://test.livekit.local")
os.environ.setdefault("LIVEKIT_API_KEY", "test-api-key")
os.environ.setdefault("LIVEKIT_API_SECRET", "test-api-secret")
os.environ.setdefault("CONFIG_SECRET", "test-config-secret-exactly-32bytes!")

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def livekit_env(monkeypatch):
    """Full set of required LiveKit env vars (resets to clean state)."""
    monkeypatch.setenv("LIVEKIT_URL", "wss://test.livekit.local")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-api-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-api-secret")
    monkeypatch.setenv("CONFIG_SECRET", "test-config-secret-exactly-32bytes!")


@pytest.fixture
def mock_livekit_api():
    """Return (MockClass, mock_dispatch) for patching main.LiveKitAPI.

    Usage::

        with patch("main.LiveKitAPI", mock_lk_cls):
            ...
        assert mock_dispatch.id == "dispatch-test-id"
    """
    mock_dispatch = MagicMock()
    mock_dispatch.id = "dispatch-test-id"
    mock_dispatch.room = "room-test-abc"

    lk_ctx = AsyncMock()
    lk_ctx.__aenter__ = AsyncMock(return_value=lk_ctx)
    lk_ctx.__aexit__ = AsyncMock(return_value=None)
    lk_ctx.agent_dispatch.create_dispatch = AsyncMock(return_value=mock_dispatch)

    mock_cls = MagicMock(return_value=lk_ctx)
    return mock_cls, mock_dispatch


@pytest.fixture
def mock_access_token():
    """Return a mock AccessToken that chains .with_* calls and returns a JWT."""
    tok = MagicMock()
    tok.with_identity.return_value = tok
    tok.with_name.return_value = tok
    tok.with_grants.return_value = tok
    tok.to_jwt.return_value = "mock-livekit-jwt"
    return MagicMock(return_value=tok)
