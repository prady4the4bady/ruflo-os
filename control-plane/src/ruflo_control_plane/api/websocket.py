"""WebSocket endpoint for real-time task event streaming."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)
router = APIRouter()

# Global connection manager
_connections: set[WebSocket] = set()


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an event to all connected WebSocket clients."""
    message = json.dumps({
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    disconnected = set()
    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    _connections.difference_update(disconnected)


@router.websocket("/events")
async def task_events(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time task event streaming.

    Events:
    - task.created
    - task.status_changed
    - task.step_completed
    - task.approved / task.rejected
    - task.completed / task.failed
    - agent.action
    - approval.required
    """
    await websocket.accept()
    _connections.add(websocket)
    logger.info("websocket.connected", total=len(_connections))

    try:
        while True:
            # Keep connection alive, process incoming commands
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                cmd = msg.get("command")
                if cmd == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif cmd == "subscribe":
                    # Future: topic-based subscriptions
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "topics": msg.get("topics", ["*"]),
                    }))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
    except WebSocketDisconnect:
        _connections.discard(websocket)
        logger.info("websocket.disconnected", total=len(_connections))
