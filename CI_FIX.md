# CI Fix Required (Manual Push)

Due to OAuth scope restrictions, I cannot push GitHub workflow changes.

## Change Needed

File: `.github/workflows/ci.yml` (line 28)

**From:**
```yaml
run: uv run pytest tests/ -v --tb=short
```

**To:**
```yaml
run: uv run pytest -m "not integration" -v --tb=short
```

## Why

- Current CI runs ALL tests including smoke tests
- Smoke tests require running agent and live hub (fail in CI)
- Integration tests require live gateway (fail in CI)
- This change makes CI run only unit tests (same as `make test-py`)

## Status

✅ Fix ready in commit 14767d4 on branch `tech-debt/extract-magic-numbers`
✅ Tested locally - all tests pass
❌ Can't push due to GitHub workflow scope restriction

## To Apply

```bash
git push origin master  # (you have the permissions)
```

Or manually edit `.github/workflows/ci.yml` line 28 with the change above.
