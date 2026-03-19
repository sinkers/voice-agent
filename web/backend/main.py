import json
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager

import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from livekit.api import AccessToken, CreateAgentDispatchRequest, LiveKitAPI, VideoGrants
from pydantic import BaseModel, field_validator, ConfigDict

load_dotenv()

_REQUIRED_ENV = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]


def _check_required_env(env: dict[str, str] | None = None) -> None:
    """Raise RuntimeError if any required environment variables are missing."""
    source = env if env is not None else os.environ
    missing = [v for v in _REQUIRED_ENV if not source.get(v)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


_check_required_env()

LIVEKIT_URL = os.environ["LIVEKIT_URL"]
LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
LIVEKIT_AGENTS: list[dict] = json.loads(os.environ.get("LIVEKIT_AGENTS", "[]"))
CONFIG_SECRET = os.environ.get("CONFIG_SECRET", "")

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
cors_origins = [o.strip() for o in _cors_origins.split(",")] if _cors_origins != "*" else ["*"]

# Input validation patterns
# Allow alphanumeric, hyphens, underscores (no special chars that could break systems)
SAFE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MAX_NAME_LENGTH = 100
MAX_ROOM_NAME_LENGTH = 64
MAX_IDENTITY_LENGTH = 64


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Voice Agent Web Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TokenRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    room_name: str
    identity: str
    agent_id: str

    @field_validator("room_name")
    @classmethod
    def validate_room_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("room_name cannot be empty")
        if len(v) > MAX_ROOM_NAME_LENGTH:
            raise ValueError(f"room_name too long (max {MAX_ROOM_NAME_LENGTH} chars)")
        if not SAFE_NAME_PATTERN.match(v):
            raise ValueError("room_name contains invalid characters (use alphanumeric, hyphens, underscores only)")
        return v

    @field_validator("identity")
    @classmethod
    def validate_identity(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("identity cannot be empty")
        if len(v) > MAX_IDENTITY_LENGTH:
            raise ValueError(f"identity too long (max {MAX_IDENTITY_LENGTH} chars)")
        if not SAFE_NAME_PATTERN.match(v):
            raise ValueError("identity contains invalid characters (use alphanumeric, hyphens, underscores only)")
        return v

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("agent_id cannot be empty")
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"agent_id too long (max {MAX_NAME_LENGTH} chars)")
        if not SAFE_NAME_PATTERN.match(v):
            raise ValueError("agent_id contains invalid characters (use alphanumeric, hyphens, underscores only)")
        return v


class DispatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    room_name: str
    agent_name: str

    @field_validator("room_name")
    @classmethod
    def validate_room_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("room_name cannot be empty")
        if len(v) > MAX_ROOM_NAME_LENGTH:
            raise ValueError(f"room_name too long (max {MAX_ROOM_NAME_LENGTH} chars)")
        if not SAFE_NAME_PATTERN.match(v):
            raise ValueError("room_name contains invalid characters (use alphanumeric, hyphens, underscores only)")
        return v

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("agent_name cannot be empty")
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"agent_name too long (max {MAX_NAME_LENGTH} chars)")
        if not SAFE_NAME_PATTERN.match(v):
            raise ValueError("agent_name contains invalid characters (use alphanumeric, hyphens, underscores only)")
        return v


@app.get("/agents")
async def list_agents():
    return LIVEKIT_AGENTS


@app.post("/token")
async def create_token(req: TokenRequest):
    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(req.identity)
        .with_name(req.identity)
        .with_grants(VideoGrants(room_join=True, room=req.room_name))
        .to_jwt()
    )
    return {"token": token, "url": LIVEKIT_URL}


@app.post("/dispatch")
async def dispatch_agent(req: DispatchRequest):
    async with LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        dispatch = await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(room=req.room_name, agent_name=req.agent_name)
        )
    return {"dispatch_id": dispatch.id, "room": dispatch.room}


class ConnectRequest(BaseModel):
    config_token: str


@app.post("/connect")
async def connect_with_token(req: ConnectRequest):
    """Verify a signed config token, issue a LiveKit room token, dispatch the agent."""
    if not CONFIG_SECRET:
        raise HTTPException(status_code=503, detail="Config tokens not enabled on this server")
    try:
        payload = jwt.decode(req.config_token, CONFIG_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Config token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid config token")

    agent_name = payload.get("agent_name")
    if not agent_name:
        raise HTTPException(status_code=400, detail="Config token missing agent_name")

    # Validate agent_name
    if not isinstance(agent_name, str) or not agent_name.strip():
        raise HTTPException(status_code=400, detail="agent_name must be a non-empty string")
    if len(agent_name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"agent_name too long (max {MAX_NAME_LENGTH} chars)")
    if not SAFE_NAME_PATTERN.match(agent_name):
        raise HTTPException(status_code=400, detail="agent_name contains invalid characters")

    # Validate display_name
    display_name = payload.get("display_name", agent_name)
    if display_name:
        if not isinstance(display_name, str):
            display_name = str(display_name)
        if len(display_name) > MAX_NAME_LENGTH:
            raise HTTPException(status_code=400, detail=f"display_name too long (max {MAX_NAME_LENGTH} chars)")

    # Use per-token LiveKit creds if provided, otherwise fall back to server defaults
    lk_url = payload.get("livekit_url") or LIVEKIT_URL
    lk_key = payload.get("livekit_api_key") or LIVEKIT_API_KEY
    lk_secret = payload.get("livekit_api_secret") or LIVEKIT_API_SECRET

    # Validate LiveKit URL format
    if not lk_url or not isinstance(lk_url, str):
        raise HTTPException(status_code=400, detail="Invalid livekit_url")
    if not (lk_url.startswith("ws://") or lk_url.startswith("wss://") or lk_url.startswith("http://") or lk_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="livekit_url must be a valid WebSocket or HTTP URL")

    # Validate API credentials are non-empty strings
    if not lk_key or not isinstance(lk_key, str) or not lk_key.strip():
        raise HTTPException(status_code=400, detail="Invalid livekit_api_key")
    if not lk_secret or not isinstance(lk_secret, str) or not lk_secret.strip():
        raise HTTPException(status_code=400, detail="Invalid livekit_api_secret")

    room_name = f"room-{uuid.uuid4().hex[:12]}"
    identity = f"user-{uuid.uuid4().hex[:8]}"

    # Issue LiveKit room token
    lk_token = (
        AccessToken(lk_key, lk_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

    # Dispatch the agent to the room
    async with LiveKitAPI(url=lk_url, api_key=lk_key, api_secret=lk_secret) as lk:
        dispatch = await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(room=room_name, agent_name=agent_name)
        )

    return {
        "agent": {"id": agent_name, "name": display_name},
        "token": lk_token,
        "url": lk_url,
        "room_name": room_name,
        "dispatch_id": dispatch.id,
    }


# Serve the React SPA — must come AFTER all API routes
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    _assets_dir = os.path.join(_static_dir, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_root():
        return FileResponse(os.path.join(_static_dir, "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file_path = os.path.join(_static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_static_dir, "index.html"))
