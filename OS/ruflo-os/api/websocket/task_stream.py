"""
WebSocket endpoint for real-time task progress streaming.
"""
import asyncio
import time
import structlog
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any

logger = structlog.get_logger(__name__)

# Broadcast manager for multiple clients
class TaskStreamManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket, task_id: str):
        await ws.accept()
        self.connections.append(ws)
        logger.info("Task stream client connected", task_id=task_id, total=len(self.connections))

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
            logger.info("Task stream client disconnected", total=len(self.connections))

    async def broadcast_step(self, task_id: str, step_number: int, description: str, tool_used: str):
        message = {
            "event": "step",
            "data": {
                "task_id": task_id,
                "step_number": step_number,
                "description": description,
                "tool_used": tool_used,
                "timestamp": time.time()
            }
        }
        await self._broadcast(message)

    async def broadcast_complete(self, task_id: str, success: bool, summary: str):
        message = {
            "event": "complete",
            "data": {
                "task_id": task_id,
                "success": success,
                "summary": summary,
                "timestamp": time.time()
            }
        }
        await self._broadcast(message)

    async def broadcast_error(self, task_id: str, message: str, recoverable: bool = True):
        message = {
            "event": "error",
            "data": {
                "task_id": task_id,
                "message": message,
                "recoverable": recoverable,
                "timestamp": time.time()
            }
        }
        await self._broadcast(message)

    async def _broadcast(self, message: dict):
        disconnected = []
        for conn in self.connections:
            try:
                await conn.send_json(message)
            except Exception as e:
                logger.error("Broadcast failed", error=str(e))
                disconnected.append(conn)
        for conn in disconnected:
            self.disconnect(conn)


# Global stream manager
stream_manager = TaskStreamManager()


async def task_stream_endpoint(ws: WebSocket, task_id: str):
    """
    WebSocket endpoint /ws/tasks for real-time task progress.
    Events:
    - step: {step_number, description, tool_used, timestamp}
    - complete: {task_id, success, summary}
    - error: {message, recoverable}
    """
    await stream_manager.connect(ws, task_id)
    try:
        while True:
            # Keep connection alive, wait for any client messages
            data = await ws.receive_json()
            logger.debug("Client message received", data=data)
    except WebSocketDisconnect:
        stream_manager.disconnect(ws)
    except Exception as e:
        logger.error("Task stream error", error=str(e))
        stream_manager.disconnect(ws)
