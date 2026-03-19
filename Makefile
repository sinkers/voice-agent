.PHONY: test test-py test-fe test-all lint install-test-deps run stop cleanup url build-skill

# Run the voice agent in dev mode (prints call URL and streams logs)
# The call URL is printed after hub registration and remains valid while the agent runs
# Logs are streamed to stdout in real-time
run:
	@echo "==> Starting voice agent in dev mode..."
	@echo "==> The call URL will be printed after registration with the hub"
	@echo "==> Logs will stream below (press Ctrl+C to stop)"
	@echo ""
	uv run python agent.py dev

# Print the call URL for the running/registered agent
# This generates a fresh URL that can be shared for testing
# Each visitor gets their own room - URLs don't expire
url:
	@if [ -f .hub-agent-id-voice-agent ]; then \
		agent_id=$$(cat .hub-agent-id-voice-agent); \
		hub_url=$${HUB_URL:-https://voice-agent-hub.fly.dev}; \
		echo ""; \
		echo "================================================================================"; \
		echo "📞 Voice Agent Call URL"; \
		echo "================================================================================"; \
		echo ""; \
		echo "   $$hub_url/call?agent_id=$$agent_id"; \
		echo ""; \
		echo "Share this URL to start a voice call. Each visitor gets their own room."; \
		echo "================================================================================"; \
		echo ""; \
	else \
		echo "Error: Agent not registered yet. Run 'make run' first."; \
		exit 1; \
	fi

# Stop any running agent processes (finds processes using port 8081)
stop:
	@echo "==> Stopping voice agent..."
	@if lsof -ti:8081 > /dev/null 2>&1; then \
		echo "Found agent process on port 8081, killing..."; \
		lsof -ti:8081 | xargs kill; \
		echo "Agent stopped"; \
	else \
		echo "No agent process found on port 8081"; \
	fi

# Clean up temporary files and cached credentials
# Warning: This will log you out and require re-authentication with the hub
cleanup:
	@echo "==> Cleaning up agent files..."
	@echo "Warning: This will remove cached credentials and require re-authentication"
	@read -p "Continue? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		rm -f .hub-token-* .hub-agent-id-* .agent-instance-id-*; \
		rm -f .hub-token-*.tmp .hub-agent-id-*.tmp .agent-instance-id-*.tmp; \
		echo "Cleaned up:"; \
		echo "  - Hub authentication tokens (.hub-token-*)"; \
		echo "  - Hub agent IDs (.hub-agent-id-*)"; \
		echo "  - Agent instance IDs (.agent-instance-id-*)"; \
		echo "  - Temporary files (*.tmp)"; \
		echo "Done! Run 'make run' to re-authenticate."; \
	else \
		echo "Cleanup cancelled"; \
	fi

# Run all unit tests: Python + frontend
test: test-py test-fe

# Python unit tests only (no integration tests requiring a live gateway)
# Backend tests (test_backend.py) are skipped automatically when fastapi/httpx
# are not installed.  Run `make install-test-deps` to enable them.
test-py:
	@echo "==> Python tests"
	uv run pytest -m "not integration" -v

# Frontend (Vitest) tests only
test-fe: web/frontend/node_modules
	@echo "==> Frontend tests"
	cd web/frontend && npm run test

web/frontend/node_modules:
	cd web/frontend && npm install

# All tests including live gateway integration tests
test-all:
	@echo "==> All tests (including integration)"
	uv run pytest -v
	$(MAKE) test-fe

# Install Python test dependencies (fastapi + httpx) so test_backend.py runs
install-test-deps:
	uv add --dev fastapi httpx

# Lint and format check
lint:
	@echo "==> Running ruff linter..."
	uv run ruff check agent.py tests/ skill/scripts/*.py web/backend/*.py
	@echo "==> Running ruff format check..."
	uv run ruff format --check agent.py tests/ skill/scripts/*.py web/backend/*.py
	@echo "✅ All lint checks passed"

# Auto-fix linting issues
lint-fix:
	@echo "==> Auto-fixing linting issues..."
	uv run ruff check --fix agent.py tests/ skill/scripts/*.py web/backend/*.py
	uv run ruff format agent.py tests/ skill/scripts/*.py web/backend/*.py
	@echo "✅ Linting issues fixed"

# Smoke test — requires hub deployed + agent worker running
# Reads credentials from .hub-token-voice-agent and .hub-agent-id-voice-agent
# Note: Make sure agent is running first with 'make run' in another terminal
smoke-test:
	@echo "==> Running smoke tests"
	@if ! lsof -ti:8081 > /dev/null 2>&1; then \
		echo "ERROR: No agent running on port 8081"; \
		echo "Start the agent first: make run"; \
		exit 1; \
	fi
	uv run python tests/smoke_test.py

# Build the OpenClaw skill package (livekit-voice.skill)
# Creates a zip archive from skill/ directory contents
build-skill:
	@echo "==> Building OpenClaw skill package..."
	@cd skill && rm -f clawtalk.skill
	@cd skill && zip -r clawtalk.skill \
		SKILL.md \
		scripts/*.py \
		scripts/*.sh \
		assets/ \
		-x "*.pyc" "*__pycache__*"
	@echo "Built: skill/clawtalk.skill"
	@ls -lh skill/clawtalk.skill
