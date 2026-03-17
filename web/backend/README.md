# Voice Agent Web — Backend

FastAPI backend that handles LiveKit token generation and agent dispatch.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/agents` | Returns the list of available agents from `LIVEKIT_AGENTS` env var |
| `POST` | `/token` | Issues a LiveKit room access token |
| `POST` | `/dispatch` | Dispatches a named agent worker into the room |

### `GET /agents`

Returns:
```json
[{"id": "openclaw-alex", "name": "Alex"}, ...]
```

### `POST /token`

Request:
```json
{"room_name": "room-uuid", "identity": "user-uuid", "agent_id": "openclaw-alex"}
```

Response:
```json
{"token": "<jwt>", "url": "wss://..."}
```

### `POST /dispatch`

Request:
```json
{"room_name": "room-uuid", "agent_name": "openclaw-alex"}
```

Response:
```json
{"dispatch_id": "...", "room": "room-uuid"}
```

## Development

```bash
cp .env.example .env
# fill in your values

pip install -e .
uvicorn main:app --reload --port 8000
```

## Deployment (Fly.io)

```bash
fly launch --no-deploy  # if first time
fly secrets set LIVEKIT_URL=wss://... LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=... LIVEKIT_AGENTS='[...]'
fly deploy
```
