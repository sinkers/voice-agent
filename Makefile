.PHONY: test test-py test-fe test-all lint install-test-deps run stop cleanup

# Run the voice agent in dev mode (prints call URL and streams logs)
# The call URL is printed after hub registration and remains valid while the agent runs
# Logs are streamed to stdout in real-time
run:
	@echo "==> Starting voice agent in dev mode..."
	@echo "==> The call URL will be printed after registration with the hub"
	@echo "==> Logs will stream below (press Ctrl+C to stop)"
	@echo ""
	uv run python agent.py dev

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

# Basic syntax check
lint:
	uv run python -m py_compile agent.py && echo "agent.py OK"

# Smoke test — requires hub deployed + agent worker running
# Reads credentials from .hub-token-voice-agent and .hub-agent-id-voice-agent
smoke-test:
	uv run python tests/smoke_test.py
