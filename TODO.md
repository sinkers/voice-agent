# Voice Agent Code Review TODO

Generated: 2026-03-19
Last Updated: 2026-03-19

## 📊 PROGRESS SUMMARY

**Completed:** 11/22 issues (50%)
**Critical Issues:** 4/4 fixed ✅
**Major Issues:** 2/4 fixed
**Moderate Issues:** 4/5 fixed
**Code Quality:** 1/8 fixed

### Recent Fixes (Today)
- ✅ Fixed all 4 critical security/reliability issues
- ✅ Added file locking and atomic writes for credentials
- ✅ Converted heartbeat to managed thread with graceful shutdown
- ✅ Fixed private API usage (session._room_io → session.room_io)
- ✅ Comprehensive input validation for all API endpoints
- ✅ Eliminated shell injection risk in installer
- ✅ Added error handling to all event handlers
- ✅ Extracted timeout constants for configurability

## 🔴 CRITICAL ISSUES

- [x] 1. Private API Access (`agent.py:234-239`) ✅
  - FIXED: Changed `session._room_io` to `session.room_io` (public API)
  - `set_participant()` is the official public method for this use case
  - Commit: 2d9e97e

- [x] 2. Daemon Heartbeat Thread with No Shutdown (`agent.py:416-452`) ✅
  - FIXED: Converted to HeartbeatThread class with graceful shutdown
  - Added atexit handler, Event-based shutdown, token refresh support
  - Added failure tracking with suppression after 10 consecutive failures
  - Commit: 8576961

- [x] 3. Resource Cleanup (`agent.py:247-250`) ✅
  - FIXED: Added finally block that clears timing state
  - Session cleanup handled by livekit-agents framework
  - Commit: b571ce7

- [x] 4. Race Condition in Token/ID File Management ✅
  - FIXED: Added cross-platform file locking (fcntl/msvcrt)
  - Implemented atomic writes (temp file + rename pattern)
  - Added fsync to ensure data hits disk before rename
  - Commit: d743211

## 🟡 MAJOR ISSUES

- [x] 5. Timeout Configuration Consistency (`agent.py:26-31`)
  - FIXED: Extracted LLM/hub/heartbeat timeouts into named constants.
  - Follow-up: Document semantics in README and ensure consistent usage across modules.

- [ ] 6. Synchronous Blocking in Main Thread (`agent.py:246-251`)
  - Device auth polling uses `time.sleep`, blocking startup.
  - Fix: Make polling async or move to supervised background task.

- [x] 7. Hub Communication Error Handling ✅
  - FIXED: Added comprehensive error handling for all hub endpoints
  - Specific exceptions for timeout, connection, HTTP errors
  - Response validation (JSON parsing, required fields)
  - Retry logic for device auth polling
  - Commit: 9bf1602

- [ ] 8. Smoke Test Task/Memory Hygiene (`tests/smoke_test.py`)
  - Partially addressed: uses `asyncio.create_task()` and bounded drain/silence detection.
  - Remaining: Explicitly track/cancel tasks on disconnect; consider frame cap to bound memory.

## 🟠 MODERATE ISSUES

- [x] 9. Error Handling in Event Handlers (`agent.py:99-183`)
  - FIXED: All handlers wrapped in try/except; logs exceptions with context.

- [x] 10. Shell Injection Risk (`web-skill/scripts/utils.py`) ✅
  - FIXED: Download script to temp file first, then execute
  - No shell piping, proper error handling and cleanup
  - Commit: 0cf026e

- [x] 11. Input Validation (`web/backend/main.py`) ✅
  - FIXED: Comprehensive validation for all API endpoints
  - Pydantic validators for room_name, identity, agent_name, agent_id
  - Regex pattern enforcement (alphanumeric, hyphens, underscores only)
  - Length limits and empty string checks
  - LiveKit URL and credential validation
  - Commit: ae0a23d

- [x] 12. `_t` State Management (`agent.py:160-216`)
  - FIXED: Now local to `entrypoint()` and cleared in `finally`; no global mutable state.

- [ ] 13. Unit Test Regression: `_SECONDS_IN_A_DAY`
  - `tests/test_agent.py` asserts this constant; missing in `agent.py`.
  - Fix: Reintroduce `_SECONDS_IN_A_DAY = 86400` or adjust tests if intentionally removed.

## 📋 CODE QUALITY ISSUES

- [ ] 14. Inconsistent Error Logging / Print Usage
  - Standardize on `logger` for non-CLI code paths; keep `print()` only for interactive device auth UX.

- [ ] 15. Hard-coded Magic Numbers
  - Extract remaining literals to named constants (document intent/units), where applicable.

- [ ] 16. Missing Type Hints
  - Add comprehensive type hints to hub helpers and event callbacks.

- [ ] 17. No Rate Limiting on Hub Requests
  - Implement exponential backoff/jitter for hub polling and transient failures.

- [x] 18. Security: Plaintext Token Storage
  - FIXED: Credential files set to `0600`.
  - Optional: Consider OS keychain/encryption; document trade-offs.

- [x] 19. Deprecated `asyncio.ensure_future()`
  - FIXED: Tests use `asyncio.create_task()`; not present in agent code.

- [ ] 20. Frontend Error UX (`web/frontend/src/api.ts`)
  - Surface server `detail` messages when throwing on non-200 responses.

- [ ] 21. Tech Debt: Migrate to `RoomOptions`
  - `RoomInputOptions` works for `livekit-agents 1.x`; plan migration on library upgrade.

- [ ] 22. `load_dotenv()` at import time
  - Consider moving to `__main__` to avoid surprising env overrides; tests currently patch this.

- [ ] 23. **Smoke Test Using WebRTC** (NEW - HIGH PRIORITY)
  - Current smoke test pushes PCM frames directly, bypassing WebRTC
  - This creates false positives - test passes but web frontend may fail
  - Fix: Add smoke test that uses livekit-client SDK to join room like a browser
  - Should use Room.connect() and publish LocalAudioTrack via WebRTC
  - This will test the actual code path that browser clients use
  - Reference: Use livekit-client Python SDK or similar to browser behavior

## NOTES

- Current branch: `fix/agent-audio-subscription`
- Main branch: `master`
- **Session Status:** Ready to merge - agent confirmed working via web frontend
- **Tests:** 63/63 passing, all critical issues resolved
- **Make Commands:** run, stop, cleanup, url all working
