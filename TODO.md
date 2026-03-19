# Voice Agent Code Review TODO

Generated: 2026-03-19
Last Updated: 2026-03-19 (Evening Session Complete)

## 📊 PROGRESS SUMMARY

**Completed:** 17/23 issues (74%)
**Critical Issues:** 4/4 fixed ✅ (100%)
**Major Issues:** 3/4 fixed ✅ (75%)
**Moderate Issues:** 5/5 fixed ✅ (100%)
**Code Quality:** 5/9 fixed (56%)

### Latest Session Improvements
- ✅ CI configuration fixed (skip integration/smoke tests)
- ✅ Magic numbers extracted to named constants
- ✅ Type hints added (TypedDict, Callable, return types)
- ✅ Logging standardized (logger vs print)
- ✅ Deprecated ensure_future() replaced with create_task()
- ✅ Smoke test task tracking and proper cancellation

## 🟡 MAJOR ISSUES

- [ ] 6. Synchronous Blocking in Main Thread (`agent.py:246-251`)
  - Device auth polling uses `time.sleep`, blocking startup.
  - Fix: Make polling async or move to supervised background task.
  - Note: Low priority - only affects startup, doesn't impact runtime

- [x] 8. Smoke Test Task/Memory Hygiene ✅
  - FIXED: Replaced ensure_future() with create_task() (commit bd5446a)
  - FIXED: Track all tasks in collect_tasks list (commit d7414de)
  - FIXED: Cancel tasks before disconnect with await gather() (commit d7414de)
  - FIXED: Wrapped collect() in try/except for clean CancelledError handling

## 🟠 MODERATE ISSUES

- [x] 13. Unit Test Regression: `_SECONDS_IN_A_DAY` ✅
  - FIXED: Removed obsolete test - constant no longer needed (commit 0557d97)
  - Tests passing without it (63/63)

## 📋 CODE QUALITY ISSUES

- [x] 14. Inconsistent Error Logging / Print Usage ✅
  - FIXED: Standardized diagnostic logging to use logger (commit cbd28d5)
  - print() now only for interactive UX (device auth, call URL banner)

- [x] 15. Hard-coded Magic Numbers ✅
  - FIXED: Extracted all audio constants in smoke_test.py (commit f745d68)
  - Added: AUDIO_SAMPLE_RATE, BYTES_PER_FRAME, timeouts, etc.
  - Self-documenting with clear intent

- [x] 16. Missing Type Hints ✅
  - FIXED: Added TypedDict for HubConfig, HubRegisterResponse (commit 07b989e)
  - FIXED: Type hints for all hub functions and HeartbeatThread
  - Better IDE support and type checking

- [ ] 17. No Rate Limiting on Hub Requests
  - Implement exponential backoff/jitter for hub polling and transient failures.

- [ ] 20. Frontend Error UX (`web/frontend/src/api.ts`)
  - Surface server `detail` messages when throwing on non-200 responses.

- [ ] 21. Tech Debt: Migrate to `RoomOptions`
  - `RoomInputOptions` works for `livekit-agents 1.x`; plan migration on library upgrade.

- [ ] 22. `load_dotenv()` at import time
  - Consider moving to `__main__` to avoid surprising env overrides; tests currently patch this.

- [ ] 23. Add Comprehensive Linting to CI
  - Add linting to make and CI workflow
  - Tools to consider: ruff (fast Python linter), mypy (type checking), black (formatting)
  - Should run on every commit and PR
  - Enforce consistent code style across codebase

- [ ] 24. Add Security Scanner to CI
  - Add security scanning to CI workflow
  - Tools to consider: bandit (Python security linter), safety (dependency vulnerability scanner)
  - Scan for common vulnerabilities (OWASP top 10)
  - Check dependencies for known CVEs
  - Should run on every PR and scheduled weekly

- [ ] 25. Document Self-Hosting Options
  - Current setup uses hosted hub (voice-agent-hub.fly.dev)
  - Add documentation for self-hosting the full stack:
    - How to deploy your own hub instance
    - How to configure agent to use custom hub URL
    - How to deploy web frontend to your own domain
    - Environment variable overrides needed
  - Benefits: full control, data sovereignty, cost optimization

- [ ] 26. Integration test: install skill into a fresh OpenClaw instance
  - No test currently verifies the end-to-end skill install flow.
  - **Approach:**
    1. Start a fresh OpenClaw Docker container (clean `~/.openclaw/` state).
    2. Serve the `skill/` directory at a local URL (e.g. `python3 -m http.server`).
    3. Point the OpenClaw instance at that URL to trigger skill install — OpenClaw fetches `livekit-voice.skill` and runs `scripts/setup.py`.
    4. `setup.py` reads the container's `openclaw.json`, lists available agents, and prompts for selection — simulate/automate this input with a pre-seeded agent config.
    5. Assert: `.env` is populated with correct gateway URL, token, and `OPENCLAW_AGENT_ID`; venv and model files are present; `agent.py start` exits cleanly.
  - **What it catches:** broken setup script, missing asset files, env patching regressions, incompatible `openclaw.json` schema changes.
  - **Credentials needed in CI:** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY` (or stubs for install-only verification).

- [ ] 27. Remove old POC frontend (`web/` directory)
  - `web/frontend/` and `web/backend/` are a standalone POC that pre-dates the hub.
  - The canonical frontend now lives in `voice-agent-hub/frontend/`.
  - README updated to clarify this (commit 4bacdbb)
  - Remove `web/`, `web-skill/`, and the Node.js prerequisite once confirmed safe.

- [ ] 28. Add WebRTC-based Smoke Test
  - Current smoke tests push PCM frames directly, bypassing WebRTC
  - Creates false positives - test passes but real browser clients may fail
  - Need smoke test using livekit-client SDK to simulate actual browser connection
  - Should use Room.connect() and publish LocalAudioTrack via WebRTC

## NOTES

- **Current Status:** All critical issues fixed, agent stable and working
- **Tests:** 63/63 passing ✅
- **CI:** Fixed to skip integration tests (needs manual workflow push due to OAuth scope)
- **Make Commands:** run, stop, cleanup, url, build-skill, test, smoke-test
- **Session:** Comprehensive bug fixes and tech debt cleanup complete
