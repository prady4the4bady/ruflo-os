"""
Ruflo OS API Server - Production FastAPI Application
Provides REST and WebSocket endpoints for Ruflo Agent control.
"""
import os
import sys"
import json"
import time"
import asyncio"
import structlog"
from contextlib import asynccontextmanager"
from typing import Dict, List, Optional, Any"
from datetime import datetime, timedelta"

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status"
from fastapi.middleware.cors import CORSMiddleware"
from fastapi.responses import JSONResponse"
from fastapi.security import HTTPBearer"
from pydantic import BaseModel, Field"
import uvicorn"

# JWT Auth
from jose import jwt, JWTError"
from jose.utils import base64url_decode"

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)
logger = structlog.get_logger(__name__)

# Security
security = HTTPBearer()

# In-memory stores (replace with proper DB in production)
tasks_store: Dict[str, dict] = {}
history_store: List[dict] = []
websocket_connections: Dict[str, List[WebSocket]] = {"tasks": [], "screen": []}
start_time = time.time()

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "ruflo-os-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"


def create_jwt_token(data: dict, expires_delta: timedelta = None) -> str:
    """Create JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and verify JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid token")


async def verify_jwt(token: str = Depends(security)) -> dict:
    """Verify JWT token for protected endpoints."""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_jwt_token(token.credentials)


# ─── WebSocket Broadcast Manager ──────────────────────────────────────
class BroadcastManager:
    def __init__(self, channel: str):
        self.channel = channel
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket, task_id: Optional[str] = None):
        await ws.accept()
        self.connections.append(ws)
        logger.info("WebSocket connected", channel=self.channel, total=len(self.connections))

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
            logger.info("WebSocket disconnected", channel=self.channel, total=len(self.connections))

    async def broadcast(self, message: dict):
        disconnected = []
        for conn in self.connections:
            try:
                await conn.send_json(message)
            except Exception as e:
                logger.error("Broadcast failed", error=str(e))
                disconnected.append(conn)
        for conn in disconnected:
            self.disconnect(conn)


task_broadcaster = BroadcastManager("tasks")
screen_broadcaster = BroadcastManager("screen")


# ─── Lifespan Events ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ruflo API Server starting up")
    yield
    logger.info("Ruflo API Server shutting down")
    # Save history to disk
    history_path = "/var/ruflo/history.json"
    try:
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        with open(history_path, "w") as f:
            json.dump(history_store, f, indent=2)
        logger.info("History saved", path=history_path)
    except Exception as e:
        logger.error("Failed to save history", error=str(e))


# ─── FastAPI App ────────────────────────────────────────────────
app = FastAPI(
    title="Ruflo OS API Server",
    description="REST + WebSocket API for Ruflo AI-Native Operating System",
    version="1.0.0-production",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health Endpoint ─────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0-production",
        "uptime_seconds": round(time.time() - start_time, 2)
    }


# ─── JWT Token Endpoint ──────────────────────────────────────────
@app.post("/token", tags=["Authentication"])
async def login():
    """Get JWT token for API access."""
    token = create_jwt_token({"sub": "ruflo-agent", "role": "agent"})
    return {"access_token": token, "token_type": "bearer"}


# ─── Mount REST Routers ─────────────────────────────────────────
from api.routes import tasks, agent, models, screen, history

app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
app.include_router(agent.router, prefix="/api/v1/agent", tags=["Agent"])
app.include_router(models.router, prefix="/api/v1/models", tags=["Models"])
app.include_router(screen.router, prefix="/api/v1/screen", tags=["Screen"])
app.include_router(history.router, prefix="/api/v1", tags=["History"])


# ─── WebSocket Endpoints ──────────────────────────────────────
@app.websocket("/ws/tasks")
async def websocket_task_stream(ws: WebSocket):
    """WebSocket for real-time task progress streaming."""
    await task_broadcaster.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            # Handle client messages
            logger.debug("WS message received", data=data)
    except WebSocketDisconnect:
        task_broadcaster.disconnect(ws)
    except Exception as e:
        logger.error("Task stream error", error=str(e))
        task_broadcaster.disconnect(ws)


@app.websocket("/ws/screen")
async def websocket_screen_stream(ws: WebSocket):
    """WebSocket for live screen streaming at configurable FPS."""
    await screen_broadcaster.connect(ws)
    fps = 5
    try:
        while True:
            # Send screen frame
            frame_data = await capture_screen_frame()
            await ws.send_json({
                "event": "frame",
                "data": frame_data,
                "timestamp": time.time()
            })
            await asyncio.sleep(1.0 / fps)
    except WebSocketDisconnect:
        screen_broadcaster.disconnect(ws)
    except Exception as e:
        logger.error("Screen stream error", error=str(e))
        screen_broadcaster.disconnect(ws)


# ─── Screen Capture Helper ──────────────────────────────────────────
async def capture_screen_frame(quality: int = 60) -> str:
    """Capture screen and return base64 JPEG."""
    try:
        import subprocess
        import base64
        from PIL import ImageGrab
        import io

        screenshot = ImageGrab.grab()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=quality)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error("Screen capture failed", error=str(e))
        return ""


# ─── Main Entrypoint ──────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info("Starting Ruflo API Server", host=host, port=port)
    uvicorn.run(app, host=host, port=port)
