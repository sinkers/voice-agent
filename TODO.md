# Voice Agent Code Review TODO

Generated: 2026-03-19
Last Updated: 2026-03-19

## 📊 PROGRESS SUMMARY

**Completed:** 14/23 issues (61%)
**Critical Issues:** 4/4 fixed ✅
**Major Issues:** 2/4 fixed
**Moderate Issues:** 4/5 fixed
**Code Quality:** 4/10 fixed

## 🟡 MAJOR ISSUES

- [ ] 6. Synchronous Blocking in Main Thread (`agent.py:246-251`)
  - Device auth polling uses `time.sleep`, blocking startup.
  - Fix: Make polling async or move to supervised background task.

- [ ] 8. Smoke Test Task/Memory Hygiene (`tests/smoke_test.py`)
  - Partially addressed: uses bounded drain/silence detection; connects via WebRTC.
  - Remaining: `asyncio.ensure_future()` still used at line 177 — replace with `create_task()`.
  - Remaining: Explicitly track/cancel tasks on disconnect; consider frame cap to bound memory.

## 🟠 MODERATE ISSUES

- [ ] 13. Unit Test Regression: `_SECONDS_IN_A_DAY` (verify closed)
  - `_SECONDS_IN_A_DAY` absent from `agent.py` and no longer referenced in tests.
  - Confirm intentional; close if tests are green without it.

## 📋 CODE QUALITY ISSUES

- [ ] 14. Inconsistent Error Logging / Print Usage
  - Standardize on `logger` for non-CLI code paths; keep `print()` only for interactive device auth UX.
  - Startup banner (`agent.py:610-614`) and registration logging still use `print()`.

- [ ] 15. Hard-coded Magic Numbers
  - Extract remaining literals to named constants (document intent/units), where applicable.

- [ ] 16. Missing Type Hints
  - Add comprehensive type hints to hub helpers and event callbacks.

- [ ] 17. No Rate Limiting on Hub Requests
  - Implement exponential backoff/jitter for hub polling and transient failures.

- [ ] 20. Frontend Error UX (`web/frontend/src/api.ts`)
  - Surface server `detail` messages when throwing on non-200 responses.

- [ ] 21. Tech Debt: Migrate to `RoomOptions`
  - `RoomInputOptions` works for `livekit-agents 1.x`; plan migration on library upgrade.

- [ ] 22. `load_dotenv()` at import time
  - Consider moving to `__main__` to avoid surprising env overrides; tests currently patch this.

- [ ] 25. Integration test: install skill into a fresh OpenClaw instance
  - No test currently verifies the end-to-end skill install flow.
  - **Approach:**
    1. Start a fresh OpenClaw Docker container (clean `~/.openclaw/` state).
    2. Serve the `skill/` directory at a local URL (e.g. `python3 -m http.server`).
    3. Point the OpenClaw instance at that URL to trigger skill install — OpenClaw fetches `livekit-voice.skill` and runs `scripts/setup.py`.
    4. `setup.py` reads the container's `openclaw.json`, lists available agents, and prompts for selection — simulate/automate this input with a pre-seeded agent config.
    5. Assert: `.env` is populated with correct gateway URL, token, and `OPENCLAW_AGENT_ID`; venv and model files are present; `agent.py start` exits cleanly.
  - **What it catches:** broken setup script, missing asset files, env patching regressions, incompatible `openclaw.json` schema changes.
  - **Credentials needed in CI:** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY` (or stubs for install-only verification).

- [ ] 24. Remove old POC frontend (`web/` directory)
  - `web/frontend/` and `web/backend/` are a standalone POC that pre-dates the hub.
  - The canonical frontend now lives in `voice-agent-hub/frontend/`.
  - Remove `web/`, `web-skill/`, and the Node.js prerequisite from the README once confirmed safe.

## NOTES

- Current branch: `fix/agent-audio-subscription`
- Main branch: `master`
- **Session Status:** Ready to merge - agent confirmed working via web frontend
- **Tests:** 63/63 passing, all critical issues resolved
- **Make Commands:** run, stop, cleanup, url all working
