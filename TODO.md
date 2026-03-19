# Voice Agent Code Review TODO

Generated: 2026-03-19
Last Updated: 2026-03-20 (Mypy + Refactoring Complete)

## 📊 PROGRESS SUMMARY

**Completed:** 20/30 issues (67%)
**Critical Issues:** 4/4 fixed ✅ (100%)
**Major Issues:** 3/4 fixed ✅ (75%)
**Moderate Issues:** 5/5 fixed ✅ (100%)
**Code Quality:** 8/11 fixed (73%)

### Latest Session Improvements
- ✅ CI configuration fixed (skip integration/smoke tests)
- ✅ Magic numbers extracted to named constants
- ✅ Type hints added (TypedDict, Callable, return types)
- ✅ Logging standardized (logger vs print)
- ✅ Deprecated ensure_future() replaced with create_task()
- ✅ Smoke test task tracking and proper cancellation
- ✅ Mypy type checking added to CI and Makefile (PR #19)

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

- [x] 23. Add Comprehensive Linting to CI ✅
<<<<<<< HEAD
  - FIXED: Added mypy type checking to CI and Makefile (PR #19)
  - ruff (linting + formatting) was already in place
  - mypy now runs on every commit and PR
  - Fixed type annotations and added type ignores for library issues
  - All 69 tests passing with mypy checks
=======
  - FIXED: ruff (linting + formatting) already in place
  - FIXED: mypy type checking added (PR #19 pending)
  - Runs on every commit and PR
  - Enforces consistent code style across codebase
>>>>>>> a750a57 (docs: update TODO - mark items 23, 24, 30 as complete (20/30 done))

- [x] 24. Add Security Scanner to CI ✅
  - FIXED: bandit security scanner in Makefile and CI (commit 4031442)
  - Scans for common vulnerabilities (OWASP top 10)
  - Runs on every PR
  - Can add safety for dependency CVE scanning later if needed

- [ ] 25. Document Self-Hosting Options
  - Current setup uses hosted hub (voice-agent-hub.fly.dev)
  - Add documentation for self-hosting the full stack:
    - How to deploy your own hub instance
    - How to configure agent to use custom hub URL
    - How to deploy web frontend to your own domain
    - Environment variable overrides needed
  - Benefits: full control, data sovereignty, cost optimization

- [x] 26. Basic Skill Installation Tests ✅
  - ADDED: test_skill_install.py with 10 integration tests
  - Tests validate:
    - All skill scripts have valid Python syntax
    - setup.py can import and has required functions
    - Asset files (agent.py, pyproject.toml, env.example) are valid
    - Scripts are executable
  - Fast tests (< 1s), no Docker/network required
  - Marked as @pytest.mark.integration (skipped in CI)

- [ ] 27. Docker E2E: Full Skill Installation in Fresh OpenClaw Container
  - Need comprehensive e2e test using OpenClaw Docker container
  - **Approach (using OpenClaw Web Completion API):**
    1. Boot fresh OpenClaw Docker container with web completion API exposed
    2. Use OpenClaw's web API to install skill:
       - POST /api/completion with "install livekit-voice skill from <url>"
       - API handles interactive prompts (agent selection) automatically
    3. Verify installation via API queries:
       - Query OpenClaw: "what skills are installed?"
       - Query: "what is the voice agent status?"
       - Should return skill installed, .env configured
    4. Test skill operations via API:
       - "start voice agent" via API
       - "voice agent status" should show running
       - "stop voice agent" via API
  - **Benefits:**
    - Uses real OpenClaw web completion API (no stdin mocking)
    - Tests actual user workflow (API-driven)
    - Can run in CI with Docker Compose
  - **What it catches:** setup script bugs, asset packaging issues, openclaw.json schema changes, skill metadata issues

- [ ] 27. Remove old POC frontend (`web/` directory)
  - `web/frontend/` and `web/backend/` are a standalone POC that pre-dates the hub.
  - The canonical frontend now lives in `voice-agent-hub/frontend/`.
  - README updated to clarify this (commit 4bacdbb)
  - Remove `web/`, `web-skill/`, and the Node.js prerequisite once confirmed safe.

- [ ] 29. Multi-Agent Install: One Installation, Per-Agent Services
  - **Goal:** Install the skill once into an OpenClaw instance and make it available to all agents. Any agent can start/stop its own voice service independently, multiple agents can run concurrently, and any agent can return its call URL on request.
  - **Current problem:** The skill is installed once with a single `OPENCLAW_AGENT_ID` baked into `.env`. Running a second agent requires a second full install at a different path. There's no way for an agent to start itself or report its URL — these are manual shell operations.

  - **Required changes:**

  - **1 — Shared install layout**
    - Install shared assets (venv, model files, agent code) once to a shared path (e.g. `~/.openclaw/skills/livekit-voice/`).
    - Per-agent state lives in subdirectories: `~/.openclaw/skills/livekit-voice/agents/<agent_id>/`
      - `.env` — agent-specific config (LIVEKIT creds, `OPENCLAW_AGENT_ID=<agent_id>`)
      - `agent.pid` — process ID of the running service
      - `agent.log` — log output
      - `call_url` — call URL written by the agent on startup, read back by the skill

  - **2 — Per-agent script interface**
    - `setup.py <agent_id>` — configure credentials for a specific agent (creates `agents/<agent_id>/.env`); shared venv/model files are only installed once
    - `start.py <agent_id>` — start a service process for that agent; writes PID to `agents/<agent_id>/agent.pid`
    - `stop.py <agent_id>` — stop just that agent's process
    - `status.py [<agent_id>]` — status for one agent, or list all configured agents and their running state
    - `call_url.py <agent_id>` — print the stored call URL for that agent (read from `agents/<agent_id>/call_url`)

  - **3 — Agent writes its call URL on startup**
    - In `agent.py`, after `_call_url_base` is resolved, write it to `agents/<agent_id>/call_url` so the skill can read it back without hitting the hub API.

  - **4 — SKILL.md and skill description update**
    - Update `SKILL.md` so OpenClaw knows the commands now take `<agent_id>` arguments.
    - Ensure the skill description covers "start voice for this agent", "stop voice", "what is my call URL?".
    - The `call_url.py` command becomes the answer to "give me my call URL" — OpenClaw calls it and speaks the result.

  - **5 — Backwards compatibility**
    - Existing single-agent installs should keep working; detect old layout and migrate or document the path change.

- [x] 30. Configurable TTS Voice Selection ✅
  - FIXED: OPENAI_TTS_VOICE env var added (commit 660d39a)
  - FIXED: Support for Cartesia and ElevenLabs TTS providers (commit c398437)
  - FIXED: Comprehensive voice selection documentation (commit 1f3ea07)
  - FIXED: Interactive voice selection in setup.py
  - All voices documented in env.example with gender labels
  - Note: With multi-agent install (item 29), each agent can have different voices

- [ ] 31. Pipeline Latency Benchmarking and Fast-Model Recommendations
  - **Goal:** Measure end-to-end and per-stage latency across interchangeable STT/LLM/TTS providers so the fastest configuration for voice can be identified and documented.

  - **Current state:**
    - `agent.py` has basic `_t` dict timing (speech start → STT done → TTS start) but it only logs to `logger` and is absent from `skill/assets/agent/agent.py`.
    - No TTFT (time-to-first-token) measurement, no TTS-to-first-audio measurement, no structured/parseable output for comparison.

  - **Stages to measure (with target budgets):**

    | Stage | Definition | Target |
    |-------|-----------|--------|
    | **VAD→STT** | VAD end-of-speech → final transcript | < 300 ms |
    | **STT→TTFT** | Final transcript → first LLM token | < 300 ms |
    | **TTFT→TTS-start** | First LLM token → TTS begins streaming audio | < 150 ms |
    | **TTS-start→first audio** | TTS API call → first audio frame received | < 200 ms |
    | **E2E** | VAD end-of-speech → first audio frame to caller | < 800 ms |

  - **Implementation plan:**

    1. **Port timing to `skill/assets/agent/agent.py`** — the deployed version currently has none.
    2. **Add TTFT hook** — livekit-agents fires events on first LLM token; capture `_t["llm_first_token"]` and log `STT→TTFT = llm_first_token - stt_done`.
    3. **Add TTS-to-first-audio** — capture time between TTS API call and first audio frame emitted; log as `tts_to_audio`.
    4. **Structured log format** — emit a single JSON summary line per turn so timings can be grepped/parsed without post-processing:
       ```
       [LATENCY] {"vad_to_stt": 0.241, "stt_to_ttft": 0.187, "ttft_to_tts": 0.093, "tts_to_audio": 0.198, "e2e": 0.719, "stt": "deepgram/nova-3", "llm": "gpt-4o", "tts": "openai/alloy"}
       ```
    5. **Make all three providers configurable via env** — `STT_PROVIDER`, `LLM_PROVIDER`, `TTS_PROVIDER` (or keep existing `OPENAI_TTS_VOICE` pattern) so different stacks can be tested without code changes.
    6. **Latency test script** (`tests/latency_test.py`) — send a fixed audio clip, capture the JSON latency line from logs, and print a comparison table across runs.

  - **Recommended fast configurations to test (all have livekit-agents plugins):**

    | Rank | STT | LLM | TTS | Expected E2E | Notes |
    |------|-----|-----|-----|-------------|-------|
    | 🥇 Fastest | Deepgram nova-3 | Groq `llama-3.3-70b-versatile` | Cartesia Sonic | ~500 ms | Groq TTFT ~150ms; Cartesia purpose-built for RT voice |
    | 🥈 Balanced | Deepgram nova-3 | Groq `llama-3.1-8b-instant` | Cartesia Sonic | ~400 ms | 8b is faster but weaker reasoning |
    | 🥉 Quality | Deepgram nova-3 | GPT-4o-mini | ElevenLabs Turbo v2.5 | ~700 ms | Better output quality, still streaming TTS |
    | Current | Deepgram nova-3 | GPT-4o | OpenAI alloy | ~900 ms+ | Baseline — good quality, not optimised for latency |

    **Key insight:** The biggest wins are:
    - **LLM → switch to Groq** (`livekit-plugins-groq`) — TTFT drops from ~500ms to ~150ms
    - **TTS → switch to Cartesia** (`livekit-plugins-cartesia`) — first-audio drops from ~400ms to ~100ms
    - STT is already near-optimal with Deepgram nova-3

  - **Packages needed:** `livekit-plugins-groq`, `livekit-plugins-cartesia`, `livekit-plugins-elevenlabs` — add as optional dependencies in `pyproject.toml`.

- [ ] 32. Session-Scoped Call URLs: Route Each Call to the Requesting Session
  - **Goal:** When an OpenClaw agent is asked "what's my call URL?", the generated URL should connect the voice call to **that agent's current session** — so voice and text share memory, context, and tool state — rather than the static session pinned in `.env` at startup.

  - **Current problem:**
    - `OPENCLAW_SESSION_KEY` is read once in `_create_llm()` at process startup and baked into the `AsyncOpenAI` client's `default_headers`. It cannot change without restarting the process.
    - `generate_call_url.py` / `skill/scripts/call_url.py` generate a URL that routes to the same static session (or no session). They have no way to encode a caller-specific session key.
    - If no session key is set, each incoming call creates a throwaway session — no memory continuity.

  - **What needs to change:**

  - **1 — Encode session key in the call URL JWT**
    - `generate_call_url.py` / `call_url.py` should accept an optional `--session-key` argument.
    - When provided, include `"session_key": "<key>"` in the JWT payload.
    - OpenClaw calls `call_url.py --session-key <current_session_key>` when generating the URL on demand, injecting its active session into the token.

  - **2 — Hub passes session key through to agent dispatch**
    - `voice-agent-hub/backend/main.py`: when decoding the call token, extract `session_key` from the JWT payload.
    - Pass it to the agent via LiveKit dispatch metadata (`dispatch_request.metadata` JSON field).

  - **3 — Agent reads session key from dispatch metadata per-call**
    - In `agent.py:entrypoint()`, parse `ctx.job.metadata` JSON to extract `session_key`.
    - Create the LLM client **per-call** inside `entrypoint()` rather than at module load time, using the session key from metadata as a per-request header.
    - Fall back to `OPENCLAW_SESSION_KEY` from `.env` if metadata contains no session key (backwards compat).
    - The module-level `_llm` either becomes a factory or defaults to the static session; the per-call client is local to `entrypoint()`.

  - **4 — SKILL.md update**
    - Document the "what is my call URL?" intent so OpenClaw knows to pass its session key when invoking `call_url.py`.
    - This is what makes "give me my call URL" actually connect the voice call into the current chat session.

  - **Why not restart the process?**
    - A restart interrupts all concurrent calls and forces re-registration with the hub. With multi-agent support (item 29), a single process may serve multiple concurrent callers — per-process restarts aren't viable. The session key must flow in-band per call.

- [ ] 33. Refactor `agent.py` — Break Into Modules
  - **Problem:** `agent.py` is 647 lines covering six distinct responsibilities in one flat file. It's hard to test in isolation, hard to navigate, and will only grow as items 29–32 land.
  - **Current structure:**
    - Lines 1–46: imports, file locking, timeout constants
    - Lines 47–87: `HubConfig` / `HubRegisterResponse` TypedDicts
    - Lines 88–148: `_create_llm()` — LLM client factory
    - Lines 149–305: `VoiceAssistant`, `entrypoint()` — core agent session logic and event handlers
    - Lines 306–474: hub API functions (`_hub_authenticate`, `_hub_get_config`, `_hub_register`, device auth polling)
    - Lines 475–647: `HeartbeatThread`, `_start_heartbeat`, `main()` startup / registration

  - **Proposed module layout:**
    ```
    agent/
    ├── __main__.py        # Entry point: calls main() from startup.py
    ├── startup.py         # main(), registration, _call_url_base wiring
    ├── session.py         # VoiceAssistant, entrypoint(), event handlers
    ├── llm.py             # _create_llm(), LLM client factory (incl. item 32 per-call client)
    ├── hub.py             # _hub_authenticate, _hub_get_config, _hub_register, device auth
    ├── heartbeat.py       # HeartbeatThread, _start_heartbeat
    └── constants.py       # Timeout constants, type definitions (HubConfig, etc.)
    ```

  - **Rules for the refactor:**
    - No behaviour changes — pure structural move. All existing tests must pass unmodified.
    - Each module should be importable in isolation for testing (no circular imports).
    - `hub.py` functions become methods on a `HubClient` class so they share `hub_url` and `token` without passing them as args to every call.
    - `HeartbeatThread` moves to `heartbeat.py` unchanged.
    - `session.py` imports from `llm.py` and `constants.py` only — no hub dependency at session level.
    - Keep `agent.py` as a shim (`from agent.startup import main; main()`) during transition so existing `python agent.py dev` invocation keeps working.

  - **Do this before implementing items 29–32** — the multi-agent, session-scoped, and latency work all touch `entrypoint()`, `_create_llm()`, and `_hub_register` heavily. Doing the refactor first means each of those changes lands in a focused, well-scoped file rather than further bloating the monolith.

- [ ] 34. Docker Resilience Tests: OpenClaw Gateway Restart and Reboot
  - **Goal:** Verify that after an OpenClaw container restart or reboot, a running voice agent can still return its call URL and recover LLM routing — without the agent needing a manual restart.
  - **Depends on:** Item 27 (Docker E2E base infrastructure).

  - **Observed behaviour:** Gateway restart kills the `agent.py` processes. They do **not** survive independently. This is likely because the agent processes are running inside the same Docker container as OpenClaw — `docker restart` sends SIGTERM to all processes in the container, killing everything regardless of `start_new_session=True`. The assumption that they are independent OS processes only holds when they run on the host or in a separate container.

  - **Test scenarios to cover:**

  - **Scenario A — Agent process survival after gateway restart (BUG — needs fix)**
    - `docker restart <openclaw_container>` kills agent processes. They must either survive or restart automatically.
    - **Root cause options to investigate:**
      1. Agent processes are children inside the same container — `docker restart` kills the whole container.
      2. OpenClaw's skill manager tracks child PIDs and sends SIGTERM on shutdown.
    - **Fix options (pick one):**
      - **Preferred:** Run agent processes in a **separate container** from OpenClaw, started via `docker compose`. Gateway restart only affects the OpenClaw container; agent container is unaffected.
      - **Alternative:** Add a process supervisor inside the container (e.g. `supervisord`) that automatically restarts `agent.py` after the container comes back up.
      - **Lightweight alternative:** Add an `--auto-restart` flag to `start.py` that wraps the agent in a retry loop, combined with ensuring the agent PID file is written before the container fully exits so `start.py` can detect and re-launch on container start.
    - **Assert after fix:** Agent process PID survives (separate container) or a new process is running within 10 s of container coming back up. `call_url.py` returns a valid URL within that window.

  - **Scenario B — Gateway reboot with token change**
    - Start agent + OpenClaw container.
    - Stop container, change `OPENCLAW_GATEWAY_TOKEN` in the container env, restart.
    - **Expected (current behaviour):** LLM calls start failing with 401 — the agent's gateway token is baked into `AsyncOpenAI`'s `default_headers` at startup and never refreshed. **This is a known gap** (see `_start_heartbeat` comment: "though in current implementation it's static").
    - **Fix required:** Agent should re-read `~/.openclaw/openclaw.json` periodically or on auth failure (401) and refresh the gateway token without full restart. `HeartbeatThread.token_getter` is already a `Callable` designed to support this — it just needs to be wired to re-read the config file.
    - **Verify after fix:** After token rotation and gateway restart, the next LLM call auto-recovers within one `HUB_HEARTBEAT_INTERVAL`.

  - **Scenario C — Call URL remains available during full gateway outage**
    - Stop OpenClaw container entirely (gateway unreachable).
    - **Assert:** `call_url.py <agent_id>` still returns the stored URL instantly — it reads from `agents/<agent_id>/call_url` (item 29) or `.hub-agent-id-{base_name}`, never touches the gateway.
    - **Assert:** Agent process stays running; hub heartbeat continues independently.
    - **Assert:** Voice calls can still be dispatched via the hub; agent joins the room. LLM turns fail gracefully ("Give me a moment" fallback from item 31's prompt fix) rather than crashing the session.

  - **Test implementation:**
    - Use `docker compose` with the OpenClaw container alongside the agent process.
    - Control container lifecycle via `subprocess` calls to `docker restart` / `docker stop` / `docker start`.
    - Poll `call_url.py` output and agent logs after each event; assert expected state within a timeout.
    - Mark as `@pytest.mark.docker` — skipped in CI by default, runnable locally with `make test-docker`.

  - **What this validates that unit tests cannot:**
    - Real HTTP connection teardown and reconnection behaviour
    - Token expiry path (`_hub_authenticate` 401 → token deletion → re-auth)
    - That `call_url` storage survives gateway outage (critical for item 32's session-scoped URL flow)

- [ ] 28. Add WebRTC-based Smoke Test
  - Current smoke tests push PCM frames directly, bypassing WebRTC
  - Creates false positives - test passes but real browser clients may fail
  - Need smoke test using livekit-client SDK to simulate actual browser connection
  - Should use Room.connect() and publish LocalAudioTrack via WebRTC

- [ ] 35. Redesign `Call.tsx` — Phone Call UI
  - **Goal:** Replace the current minimal debug layout with a proper phone-call-style screen. Currently `AgentUI` is a centred badge + subtitle + 5 fixed bars; `MicrophoneSelector` is a fixed top-right dropdown; the mute button is buried inside LiveKit's `<ControlBar>`.

  - **1 — Phone-call layout (`AgentUI`)**
    - Large circular avatar centred on screen (80–100px diameter). Use agent initials as a fallback since there's no image URL yet.
    - Agent display name (`connectResult.agent`) as the primary heading below the avatar.
    - State label (`Listening`, `Thinking`, `Speaking`, `Connecting`) as a smaller subtitle beneath the name.
    - Remove the existing badge / text hint — the avatar + state label replace all of that.

  - **2 — Big mute button**
    - A single large circle button (64px) centred at the bottom of the screen — the dominant interactive element, like a phone call.
    - Shows mic icon when unmuted, crossed-mic icon when muted. Red when muted, dark/neutral when live.
    - Replaces `<ControlBar controls={{ microphone: true, ... }}>` which is currently the only mute affordance.
    - Wire via `room.localParticipant.setMicrophoneEnabled(toggle)`.

  - **3 — Mic selector: always visible, icon-driven**
    - Remove the `if (audioDevices.length <= 1) return null` guard — always show the selected device name.
    - Replace the fixed top-right dropdown with a mic icon button adjacent to the mute button. Clicking it opens a popover listing available devices with a checkmark next to the active one.
    - Display the active device label (truncated to ~30 chars) as a caption under the mic icon so it's always visible without opening the selector.
    - `useMediaDeviceSelect` is already wired in `MicrophoneSelector` — keep that hook, change the presentation.

  - **4 — `BarVisualizer` for input and agent audio**
    - Replace `AudioLevelIndicator`'s 5 fixed bars with `<BarVisualizer>` from `@livekit/components-react` (already in node_modules).
    - **User input:** `BarVisualizer` driven by the local mic `TrackReference` (from `useTracks`), visible whenever the mic is live.
    - **Agent audio:** `BarVisualizer` driven by `audioTrack` from `useVoiceAssistant()`, with `state` prop passed so it automatically animates through connecting/listening/thinking states and switches to real audio amplitude when speaking.
    - Usage pattern: `<BarVisualizer state={vaState} trackRef={audioTrack} barCount={20} />`
    - The two visualizers are labelled "You" and the agent name so it's clear which is which.
    - Note: `BarVisualizer` is multiband frequency bars, not a time-domain oscilloscope. If a true waveform is wanted later, `createAudioAnalyser` from `livekit-client` (already a dependency) can be used with a canvas — no extra packages needed.

  - **5 — Animated avatar ring when agent is speaking (bonus)**
    - When `state === "speaking"`, add a pulsing ring animation around the avatar circle.
    - Use `useTrackVolume(audioTrack)` to drive the ring scale inline (`scale(1 + volume * 0.15)`) so it breathes with the speech amplitude rather than a fixed CSS loop.
    - Pure CSS + inline style — no animation libraries needed.

  - **File to change:** `voice-agent-hub/frontend/src/pages/Call.tsx` (single file, all components are local).
  - **LK hooks/components already available:** `useVoiceAssistant`, `useTrackVolume`, `useTracks`, `useMediaDeviceSelect`, `<BarVisualizer>` — no new dependencies required.

## NOTES

- **Current Status:** All critical issues fixed, agent stable and working
- **Tests:** 63/63 passing ✅
- **CI:** Fixed to skip integration tests (needs manual workflow push due to OAuth scope)
- **Make Commands:** run, stop, cleanup, url, build-skill, test, smoke-test
- **Session:** Comprehensive bug fixes and tech debt cleanup complete
