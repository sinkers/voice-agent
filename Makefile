.PHONY: test test-py test-fe test-all lint install-test-deps

# Run all unit tests: Python + frontend
test: test-py test-fe

# Python unit tests only (no integration tests requiring a live gateway)
# Backend tests (test_backend.py) are skipped automatically when fastapi/httpx
# are not installed.  Run `make install-test-deps` to enable them.
test-py:
	@echo "==> Python tests"
	uv run pytest -m "not integration" -v

# Frontend (Vitest) tests only — requires `npm install` in web/frontend first
test-fe:
	@echo "==> Frontend tests"
	cd web/frontend && npm run test

# All tests including live gateway integration tests
test-all:
	@echo "==> All tests (including integration)"
	uv run pytest -v
	cd web/frontend && npm run test

# Install Python test dependencies (fastapi + httpx) so test_backend.py runs
install-test-deps:
	uv add --dev fastapi httpx

# Basic syntax check
lint:
	uv run python -m py_compile agent.py && echo "agent.py OK"
