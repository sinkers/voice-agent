# Self-Hosting Guide

This guide explains how to deploy and run the complete voice agent stack on your own infrastructure instead of using the hosted hub at `voice-agent-hub.fly.dev`.

## Why Self-Host?

- **Full control**: Own your infrastructure and deployment
- **Data sovereignty**: All data stays on your servers
- **Cost optimization**: Pay only for what you use
- **Customization**: Modify the hub, frontend, or agent to fit your needs
- **Privacy**: No data passes through third-party hosted services

---

## Architecture Overview

The voice agent stack has three components:

```
┌─────────────────┐
│  Voice Agent    │  ← This repo: LiveKit worker that handles voice calls
│  (Python)       │     Connects to hub for auth, dispatches to LiveKit rooms
└────────┬────────┘
         │
         │ (WebSocket + HTTP)
         │
┌────────▼────────┐
│  Hub (Backend)  │  ← Central service: agent registry, auth, call routing
│  (FastAPI)      │     Issues JWTs, dispatches agents to LiveKit rooms
└────────┬────────┘
         │
         │ (HTTP API)
         │
┌────────▼────────┐
│  Frontend       │  ← Web UI: users visit /call?agent_id=... to start calls
│  (React + TS)   │     Connects to LiveKit room via WebRTC
└─────────────────┘
```

---

## Prerequisites

To self-host, you'll need:

1. **LiveKit Cloud account** (or self-hosted LiveKit server)
   - Get credentials from https://cloud.livekit.io
   - Or deploy LiveKit server: https://docs.livekit.io/home/self-hosting/deployment/

2. **Deepgram API key** (STT provider)
   - Sign up at https://console.deepgram.com
   - $200 free credit included

3. **OpenAI API key** (LLM + TTS provider)
   - Sign up at https://platform.openai.com
   - Billing required for GPT-4o and TTS

4. **A server** to run the hub and frontend
   - Options: Fly.io, Railway, Render, Vercel, your own VPS
   - Requirements: Python 3.11+, Node.js 20+, 512MB RAM minimum

---

## Part 1: Deploy the Hub

The hub is a FastAPI backend that handles agent authentication, registration, and call routing.

### Hub Repository

The hub code lives in a separate repository (if you have access):
```bash
git clone https://github.com/your-org/voice-agent-hub.git
cd voice-agent-hub/backend
```

### Hub Environment Variables

Create a `.env` file in the hub backend:

```bash
# Required: Encryption key for storing agent API keys in database
HUB_ENCRYPTION_KEY=your_fernet_key  # Generate with: python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

# Required: JWT secret for signing session tokens
HUB_SECRET=your_random_secret_here  # Generate with: openssl rand -hex 32

# Required: Base URL where hub is deployed
BASE_URL=https://your-hub-name.fly.dev

# Required: LiveKit credentials for the hub to manage agents
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret

# Optional: Database URL (defaults to /data/hub.db)
DATABASE_URL=sqlite+aiosqlite:////data/hub.db

# Optional: CORS origins (defaults to allow all with *)
CORS_ORIGINS=https://your-frontend-domain.com,http://localhost:5173

# Optional: Pre-registered agent names (comma-separated)
LIVEKIT_AGENTS=voice-agent,support-agent
```

> **Important:** Agents store their API keys (LiveKit, Deepgram, OpenAI) in the hub database, encrypted with `HUB_ENCRYPTION_KEY`. If you lose this key, stored credentials cannot be decrypted.

### Deploy Hub to Fly.io

```bash
cd voice-agent-hub/backend

# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Create app
fly launch --name your-hub-name --region sjc

# Set secrets
fly secrets set HUB_SECRET=$(openssl rand -hex 32)
fly secrets set HUB_ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
fly secrets set BASE_URL=https://your-hub-name.fly.dev
fly secrets set LIVEKIT_URL=wss://your-project.livekit.cloud
fly secrets set LIVEKIT_API_KEY=your_key
fly secrets set LIVEKIT_API_SECRET=your_secret

# Deploy
fly deploy
```

Your hub will be available at: `https://your-hub-name.fly.dev`

### Deploy Hub to Other Platforms

**Railway / Render:**
1. Connect your git repo
2. Set environment variables in the dashboard
3. Deploy with `uvicorn main:app --host 0.0.0.0 --port $PORT`

**Your own VPS:**
```bash
# Install dependencies
cd voice-agent-hub/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run with gunicorn
gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## Part 2: Deploy the Frontend

The frontend is a React + TypeScript app that provides the `/call` web interface.

### Frontend Environment Variables

Create a `.env` file in `voice-agent-hub/frontend`:

```bash
# Point to your self-hosted hub
VITE_HUB_URL=https://your-hub-name.fly.dev
```

### Build Frontend

```bash
cd voice-agent-hub/frontend
npm install
npm run build
```

The build output is in `dist/` and can be deployed anywhere that serves static files.

### Deploy Frontend to Fly.io (Static Site)

```bash
cd voice-agent-hub/frontend

# Create fly.toml for static hosting
cat > fly.toml <<EOF
app = "your-hub-frontend"
primary_region = "sjc"

[http_service]
  internal_port = 80
  force_https = true
  auto_start_machines = true
  auto_stop_machines = true
EOF

# Create Dockerfile for static hosting
cat > Dockerfile <<EOF
FROM nginx:alpine
COPY dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EOF

# Deploy
npm run build
fly launch --dockerfile
fly deploy
```

Your frontend will be available at: `https://your-hub-frontend.fly.dev`

### Deploy Frontend to Vercel / Netlify

Both platforms auto-detect Vite projects:

**Vercel:**
```bash
npm install -g vercel
vercel --prod
```

**Netlify:**
```bash
npm install -g netlify-cli
netlify deploy --prod --dir=dist
```

Set `VITE_HUB_URL` in the platform's environment variable dashboard.

---

## Part 3: Configure the Voice Agent

Point your voice agent to your self-hosted hub.

### Agent Environment Variables

Update `.env` in the voice agent repo:

```bash
# Point to your self-hosted hub instead of the hosted one
HUB_URL=https://your-hub-name.fly.dev

# Optional: If your hub doesn't provide credentials via /agent/config,
# set them directly in the agent .env:
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
DEEPGRAM_API_KEY=your_key
OPENAI_API_KEY=your_key

# Optional: Configure TTS voice
OPENAI_TTS_VOICE=alloy  # or: echo, fable, onyx, nova, shimmer

# Optional: OpenClaw integration
OPENCLAW_GATEWAY_TOKEN=your_gateway_token
OPENCLAW_AGENT_ID=main
```

### Run the Agent

```bash
make run
```

The agent will:
1. Authenticate with **your hub** instead of the hosted one
2. Register and get a call URL pointing to **your frontend**
3. Be ready to handle calls routed through **your infrastructure**

---

## Part 4: Full Stack Self-Hosted Example

**Scenario:** Deploy everything to Fly.io

```bash
# 1. Deploy hub backend
cd voice-agent-hub/backend
fly launch --name mycompany-voice-hub
fly secrets set HUB_JWT_SECRET=$(openssl rand -hex 32)
fly secrets set LIVEKIT_URL=...  # Add all credentials
fly deploy

# 2. Deploy frontend
cd ../frontend
echo "VITE_HUB_URL=https://mycompany-voice-hub.fly.dev" >> .env
npm run build
fly launch --name mycompany-voice-frontend
fly deploy

# 3. Configure agent
cd ../../voice-agent
echo "HUB_URL=https://mycompany-voice-hub.fly.dev" >> .env
make run
```

Now:
- Hub API: `https://mycompany-voice-hub.fly.dev`
- Frontend: `https://mycompany-voice-frontend.fly.dev/call?agent_id=...`
- Agent: Running locally or deployed to your own worker server

---

## Security Considerations

When self-hosting:

1. **HUB_SECRET** must be a strong random secret (32+ bytes)
   ```bash
   openssl rand -hex 32
   ```

2. **HUB_ENCRYPTION_KEY** must be a Fernet key for encrypting stored API keys
   ```bash
   python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```
   **⚠️ Critical:** Backup this key securely. If lost, agent credentials in the database cannot be decrypted.

3. **HTTPS required** for WebRTC (browser requirement)
   - Fly.io, Vercel, Netlify provide this automatically
   - For custom domains, use Let's Encrypt

4. **CORS configuration** must allow your frontend domain
   ```bash
   CORS_ORIGINS=https://your-frontend.com,https://www.your-frontend.com
   ```

5. **API keys** should be set as secrets, never committed to git
   - Use platform secret management (Fly secrets, Vercel env vars, etc.)
   - Agent API keys are stored encrypted in the hub database

6. **Rate limiting** is built into the agent (exponential backoff)
   - The hub currently has no rate limiting - consider adding for production
   - Or use a reverse proxy (nginx, Caddy) with rate limiting rules

---

## Monitoring

For production self-hosted deployments:

**Hub health check:** `GET /health`
```bash
curl https://your-hub.fly.dev/health
# Should return: {"status": "healthy"}
```

**Agent registration check:** `GET /agent/config` (with auth token)
```bash
curl -H "Authorization: Bearer $TOKEN" https://your-hub.fly.dev/agent/config
# Returns agent config if registered
```

**Hub logs** (on Fly.io):
```bash
fly logs -a your-hub-name
```

---

## Cost Estimation

**Hosted hub (default):** Free tier
**Self-hosted on Fly.io:**
- Hub backend: ~$2-5/month (shared CPU, 256MB)
- Frontend: ~$0-2/month (static site)
- **Total: $2-7/month** (excluding LiveKit/Deepgram/OpenAI usage)

**Self-hosted on VPS:**
- Single $5/month VPS can run hub + frontend + agent worker
- Nginx reverse proxy for frontend static files

---

## Troubleshooting

**Agent can't connect to hub:**
- Check `HUB_URL` in agent `.env` matches your deployed hub URL
- Verify hub is accessible: `curl https://your-hub.fly.dev/health`
- Check hub logs for errors

**Browser can't connect to call:**
- Verify frontend `VITE_HUB_URL` points to your hub
- Check CORS: `CORS_ORIGINS` must include your frontend domain
- Ensure HTTPS (required for WebRTC)

**Agent registration fails:**
- Verify hub has valid `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- Check hub logs for detailed error messages
- Confirm agent can reach hub (no firewall blocking)

---

## Next Steps

Once self-hosting works:

1. **Custom domain**: Point your domain to the frontend
   ```bash
   fly certs add your-domain.com
   ```

2. **Production deployment**: Deploy agent worker to a dedicated server
   - Run as systemd service on Linux
   - Use supervisor/pm2 for process management
   - Set up log rotation

3. **Monitoring**: Add health checks and alerting
   - Hub uptime monitoring
   - Agent heartbeat tracking
   - LiveKit room metrics

4. **Scaling**: Run multiple agent workers for high availability
   - Each agent registers independently with the hub
   - Hub dispatches to available agents round-robin

For more details, see the `voice-agent-hub` repository README.
