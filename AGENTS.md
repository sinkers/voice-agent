# AGENTS.md — voice-agent

## Rules (non-negotiable)

### Branching & PRs
- **All changes must be made on a feature branch** — never commit directly to master
- **Raise a PR for every change** — no matter how small
- **Wait for Gemini Code Assist to review before merging** — address all comments first
- **Squash merge** PRs, delete the branch after merge

### Tests
- **Run all tests before pushing any branch:**
  ```bash
  # Unit tests — must be 100% green
  uv run pytest -m "not integration" -v

  # Smoke test — requires hub deployed + agent running
  make smoke-test
  ```
- **Tests must pass. No exceptions.** If a test fails, fix the code — don't skip or comment out the test
- **If you break a test, that is a bug** — stop and fix it before continuing

### Background tasks & reminders
- Any time you kick off a background task (deploy, test run, agent spawn), **immediately schedule a follow-up cron reminder** so it doesn't get lost if the session ends
- Report back when done — don't leave things hanging

## Architecture
- Agent authenticates with hub via device auth flow on startup
- Hub issues JWT; agent uses it to pull config (LiveKit/Deepgram/OpenAI keys) and register
- Hub dispatches agent to LiveKit rooms when callers connect via `/connect`
- Agent token + ID persisted in `.hub-token-voice-agent` and `.hub-agent-id-voice-agent`

## What broke (and why)
- The hub migration introduced explicit agent dispatch (`/connect` now calls LiveKit API to dispatch)
- `ctx.connect()` was added incorrectly — `session.start()` handles connection internally in livekit-agents 1.x
- Adding `ctx.connect()` before `session.start()` interferes with audio track subscription
- The old `RoomInputOptions` API still works; `RoomOptions` is the new API but behaves the same
- **Lesson:** changing agent startup code requires a full end-to-end test before merging
