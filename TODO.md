# Voice Agent Code Review TODO

Generated: 2026-03-19

## 🔴 CRITICAL ISSUES

- [ ] **1. Private API Access** (`agent.py:168-173`)
  - Accessing `session._room_io` to work around race condition
  - Need to find proper public API or report to livekit-agents
  - Risk: Will break with library updates

- [ ] **2. Daemon Thread with No Shutdown** (`agent.py:282-298`)
  - Infinite heartbeat loop with no shutdown mechanism
  - Token can expire but thread keeps using stale token
  - Fix: Convert to asyncio.Task with proper shutdown

- [ ] **3. Missing Resource Cleanup** (`agent.py:96-180`)
  - Event handlers never explicitly unregistered
  - No finally block for cleanup on failure
  - Fix: Add proper cleanup in finally block

- [ ] **4. Race Condition in Token File Management** (`agent.py:187-233`)
  - No file locking - concurrent processes can corrupt files
  - TOCTOU race between existence check and read
  - Fix: Add file locking with fcntl/lockf

## 🟡 MAJOR ISSUES

- [ ] **5. Timeout Configuration Inconsistency**
  - LLM: 60s, Hub: 30s, Heartbeat: 10s
  - Fix: Extract as configurable constants with documentation

- [ ] **6. Synchronous Blocking in Main Thread** (`agent.py:301-348`)
  - Device auth polling blocks main thread
  - Fix: Consider async startup pattern (lower priority)

- [ ] **7. Inadequate Hub Communication Error Handling** (`agent.py:236-252`)
  - Only handles 401, other errors raise generic HTTPError
  - No retry logic for transient failures
  - Fix: Add comprehensive error handling and retry logic

- [ ] **8. Unbounded Memory Growth in smoke_test** (`tests/smoke_test.py:145-159`)
  - `ensure_future()` creates untracked tasks
  - `agent_frames` list grows unbounded
  - Fix: Track tasks, add size limits, proper cleanup

## 🟠 MODERATE ISSUES

- [ ] **9. No Error Handling in Event Handlers** (`agent.py:99-152`)
  - All 9+ event handlers lack try/except blocks
  - Fix: Wrap all handlers in try/except

- [ ] **10. Shell Injection Risk** (`web-skill/scripts/utils.py:214`)
  - Uses `sh -c` with curl piped to sh
  - Fix: Use direct subprocess invocation, verify downloads

- [ ] **11. Missing Input Validation** (`backend/main.py`)
  - `agent_name` has no validation
  - Fix: Add comprehensive input validation

- [ ] **12. Unclear State Management with `_t` Dictionary**
  - Global mutable state, never cleared
  - Fix: Use proper class to encapsulate state

## 📋 CODE QUALITY ISSUES

- [ ] **13. Inconsistent Error Logging**
  - Fix: Standardize logging patterns

- [ ] **14. Hard-coded Magic Numbers**
  - Fix: Extract as named constants with documentation

- [ ] **15. Missing Type Hints**
  - Fix: Add complete type hints to critical functions

- [ ] **16. No Rate Limiting on Hub Requests**
  - Fix: Implement exponential backoff for polling

- [ ] **17. Security: Plaintext Token Storage**
  - Fix: Set file permissions to 0600

- [ ] **18. Deprecated asyncio.ensure_future()**
  - Fix: Replace with asyncio.create_task()

## NOTES

- Current branch: `fix/agent-audio-subscription`
- Main branch: `master`
- Priority: Fix critical issues first with small commits + tests
- System is regressing - used to work, getting progressively broken
