# Voice Agent Web — Frontend

React + Vite + TypeScript UI for interacting with LiveKit voice agents.

## Dev

```bash
cp .env.example .env
# set VITE_API_URL to your backend URL

npm install
npm run dev
```

Runs at `http://localhost:5173` by default.

## Build

```bash
npm run build
# output in dist/
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | URL of the FastAPI backend (e.g. `http://localhost:8000`) |

## Flow

1. **Home** — fetches agents from `GET /agents`, lets you pick one, then click "Start Call".
2. **Call** — generates a UUID room name, calls `POST /token` for a LiveKit JWT, calls `POST /dispatch` to send the agent into the room, then connects with `@livekit/components-react`.
