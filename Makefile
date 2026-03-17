.PHONY: test test-all lint

# Run unit tests only (no integration tests)
test:
	uv run pytest -m "not integration" -v

# Run all tests including live gateway integration tests
test-all:
	uv run pytest -v

# Basic syntax check
lint:
	uv run python -m py_compile agent.py && echo "agent.py OK"
