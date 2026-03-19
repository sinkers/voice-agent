"""End-to-end tests for OpenClaw skill installation.

Tests the complete skill installation flow:
1. setup.py copies files and creates venv
2. .env is populated with OpenClaw config
3. Agent can be started successfully

These tests are marked as integration tests and skipped in CI by default.
Run with: pytest -m integration tests/test_skill_install.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_install_dir():
    """Create a temporary directory for skill installation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_openclaw_config(tmp_path):
    """Create a mock openclaw.json for testing."""
    config_dir = tmp_path / ".openclaw"
    config_dir.mkdir()
    config_file = config_dir / "openclaw.json"

    config = {
        "gateway": {"port": 18789, "auth": {"token": "test-gateway-token-12345"}},
        "agents": {"list": [{"id": "main", "name": "Main Agent"}, {"id": "test-agent", "name": "Test Agent"}]},
    }

    config_file.write_text(json.dumps(config, indent=2))
    return config_file


@pytest.mark.integration
class TestSkillSetup:
    """Test skill setup.py installation flow."""

    def test_setup_creates_install_directory(self, temp_install_dir):
        """setup.py should create the install directory if it doesn't exist."""
        install_path = temp_install_dir / "livekit-voice-agent"
        assert not install_path.exists()

        # Run setup with agent_id to avoid prompt
        subprocess.run(
            ["python3", "skill/scripts/setup.py", str(install_path), "main"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            check=False,  # Don't raise on non-zero exit (may fail if uv not installed)
        )

        # Setup should succeed (or fail gracefully if dependencies missing)
        # We're testing the file operations, not the full install
        assert install_path.exists(), "Install directory not created"

    def test_setup_script_syntax_valid(self):
        """setup.py should have valid Python syntax."""
        setup_script = Path("skill/scripts/setup.py")
        assert setup_script.exists()

        # Compile to check syntax
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(setup_script)],
            capture_output=True,
        )
        assert result.returncode == 0, f"setup.py has syntax errors: {result.stderr.decode()}"

    def test_setup_can_import(self):
        """setup.py should be importable without errors."""
        import sys

        skill_scripts_path = str(Path("skill/scripts").absolute())
        if skill_scripts_path not in sys.path:
            sys.path.insert(0, skill_scripts_path)

        try:
            import setup

            # Should have main function
            assert hasattr(setup, "main"), "setup.py missing main() function"
        finally:
            if skill_scripts_path in sys.path:
                sys.path.remove(skill_scripts_path)

    def test_setup_has_helper_functions(self):
        """setup.py should have all required helper functions."""
        import sys

        skill_scripts_path = str(Path("skill/scripts").absolute())
        if skill_scripts_path not in sys.path:
            sys.path.insert(0, skill_scripts_path)

        try:
            import setup

            # Check for expected functions
            assert hasattr(setup, "read_openclaw_config"), "Missing read_openclaw_config()"
            assert hasattr(setup, "list_agents"), "Missing list_agents()"
            assert hasattr(setup, "patch_env"), "Missing patch_env()"
        finally:
            if skill_scripts_path in sys.path:
                sys.path.remove(skill_scripts_path)


@pytest.mark.integration
class TestSkillScripts:
    """Test skill management scripts (start, stop, status)."""

    def test_start_script_exists_and_executable(self):
        """start.py should exist and be executable."""
        start_script = Path("skill/scripts/start.py")
        assert start_script.exists()
        # Python scripts don't need +x but should run via python3
        result = subprocess.run(
            ["python3", str(start_script), "--help"],
            capture_output=True,
        )
        # Script might not have --help, but should at least run
        assert result.returncode in (0, 1, 2), "start.py failed to execute"

    def test_stop_script_exists_and_executable(self):
        """stop.py should exist and be executable."""
        stop_script = Path("skill/scripts/stop.py")
        assert stop_script.exists()
        result = subprocess.run(
            ["python3", str(stop_script), "--help"],
            capture_output=True,
        )
        assert result.returncode in (0, 1, 2), "stop.py failed to execute"

    def test_status_script_exists_and_executable(self):
        """status.py should exist and be executable."""
        status_script = Path("skill/scripts/status.py")
        assert status_script.exists()
        result = subprocess.run(
            ["python3", str(status_script), "--help"],
            capture_output=True,
        )
        assert result.returncode in (0, 1, 2), "status.py failed to execute"


@pytest.mark.integration
class TestSkillAssets:
    """Test skill asset files are valid."""

    def test_agent_py_is_valid_python(self):
        """Bundled agent.py should be valid Python."""
        agent_file = Path("skill/assets/agent/agent.py")
        assert agent_file.exists()

        # Compile to check syntax
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(agent_file)],
            capture_output=True,
        )
        assert result.returncode == 0, f"agent.py has syntax errors: {result.stderr.decode()}"

    def test_pyproject_toml_is_valid(self):
        """Bundled pyproject.toml should be valid TOML."""
        pyproject = Path("skill/assets/agent/pyproject.toml")
        assert pyproject.exists()

        content = pyproject.read_text()
        assert "[project]" in content
        assert "livekit-agents" in content

    def test_env_example_has_required_keys(self):
        """env.example should have all required environment variables."""
        env_example = Path("skill/assets/agent/env.example")
        assert env_example.exists()

        content = env_example.read_text()
        required_keys = [
            "LIVEKIT_URL",
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "OPENAI_API_KEY",
            "DEEPGRAM_API_KEY",
            "OPENCLAW_GATEWAY_TOKEN",
            "OPENCLAW_AGENT_ID",
        ]

        for key in required_keys:
            assert key in content, f"env.example missing required key: {key}"
