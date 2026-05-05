"""
WebSocket endpoint for live screen streaming at configurable FPS.
Handles client commands for click and keyboard input.
"""
import asyncio
import time
import base64
import structlog
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any
from PIL import ImageGrab
import io

logger = structlog.get_logger(__name__)

# Global screen stream manager
screen_clients: List[WebSocket] = []


async def screen_stream_endpoint(ws: WebSocket, fps: int = 5):
    """
    WebSocket endpoint /ws/screen for live screen streaming.
    - Stream screenshots at configurable FPS (default 5fps)
    - Frame: base64 encoded JPEG with quality=60 for bandwidth
    - On message: {action: "click", x, y} → execute click
    - On message: {action: "type", text} → execute keyboard input
    """
    await ws.accept()
    screen_clients.append(ws)
    logger.info("Screen stream client connected", fps=fps, total=len(screen_clients))

    try:
        while True:
            # Capture and send frame
            try:
                screenshot = ImageGrab.grab()
                buffer = io.BytesIO()
                screenshot.save(buffer, format="JPEG", quality=60)
                frame_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                await ws.send_json({
                    "event": "frame",
                    "data": frame_b64,
                    "format": "jpeg",
                    "quality": 60,
                    "timestamp": time.time(),
                    "resolution": {"width": screenshot.size[0], "height": screenshot.size[1]}
                })
            except Exception as e:
                logger.error("Frame capture failed", error=str(e))
                await ws.send_json({"event": "error", "data": {"message": str(e)}})

            await asyncio.sleep(1.0 / max(1, fps))

    except WebSocketDisconnect:
        screen_clients.remove(ws)
        logger.info("Screen stream client disconnected", total=len(screen_clients))
    except Exception as e:
        logger.error("Screen stream error", error=str(e))
        if ws in screen_clients:
            screen_clients.remove(ws)


async def handle_client_message(ws: WebSocket, message: dict):
    """Handle incoming messages from screen stream clients."""
    action = message.get("action")

    if action == "click":
        x, y = message.get("x"), message.get("y")
        if x is not None and y is not None:
            try:
                import subprocess
                subprocess.run(["ydotool", "mousemove", "--absolute", str(x), str(y)], check=True)
                subprocess.run(["ydotool", "click", "1"], check=True)
                logger.info("Click executed via WebSocket", x=x, y=y)
                await ws.send_json({"event": "action_result", "data": {"action": "click", "success": True}})
            except Exception as e:
                logger.error("Click failed", error=str(e))
                await ws.send_json({"event": "action_result", "data": {"action": "click", "success": False, "error": str(e)}})

    elif action == "type":
        text = message.get("text", "")
        if text:
            try:
                import subprocess
                for char in text:
                    subprocess.run(["ydotool", "type", char], check=True)
                    await asyncio.sleep(0.05)
                logger.info("Text typed via WebSocket", length=len(text))
                await ws.send_json({"event": "action_result", "data": {"action": "type", "success": True}})
            except Exception as e:
                logger.error("Type failed", error=str(e))
                await ws.send_json({"event": "action_result", "data": {"action": "type", "success": False, "error": str(e)}})

    elif action == "set_fps":
        # Handle FPS change request
        new_fps = message.get("fps", 5)
        logger.info("FPS change requested", fps=new_fps)
        await ws.send_json({"event": "fps_changed", "data": {"fps": new_fps}})
