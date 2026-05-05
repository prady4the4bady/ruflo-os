"""
Screen API Routes - Screen capture, state, and annotation endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import subprocess
import base64
import structlog
from PIL import ImageGrab
import io

logger = structlog.get_logger(__name__)

router = APIRouter()


class ScreenAnnotateRequest(BaseModel):
    x: int
    y: int
    label: str


class ScreenStateResponse(BaseModel):
    resolution: Dict[str, int]
    active_window_title: Optional[str] = None
    timestamp: float


@router.get("/capture")
async def capture_screen() -> Dict[str, Any]:
    """
    Capture current screen and return as base64 PNG.
    Uses mss for fast screen capture.
    """
    try:
        screenshot = ImageGrab.grab()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.info("Screen captured", size=screenshot.size)
        return {
            "success": True,
            "image_base64": img_str,
            "format": "png",
            "resolution": {"width": screenshot.size[0], "height": screenshot.size[1]},
            "timestamp": __import__("time").time()
        }
    except Exception as e:
        logger.error("Screen capture failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Screen capture failed: {str(e)}")


@router.get("/state")
async def get_screen_state() -> ScreenStateResponse:
    """
    Get current screen state: resolution, active window title.
    """
    import time
    try:
        screenshot = ImageGrab.grab()
        # Get active window title (Linux: xdotool, Windows: pygetwindow)
        active_title = None
        try:
            import subprocess
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                active_title = result.stdout.strip()
        except Exception:
            pass

        return ScreenStateResponse(
            resolution={"width": screenshot.size[0], "height": screenshot.size[1]},
            active_window_title=active_title,
            timestamp=time.time()
        )
    except Exception as e:
        logger.error("Failed to get screen state", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotate")
async def annotate_screen(request: ScreenAnnotateRequest) -> Dict[str, Any]:
    """
    Accept {x, y, label} and draw overlay dot on screen.
    Creates an annotation overlay for debugging agent actions.
    """
    try:
        # Capture screen
        screenshot = ImageGrab.grab()
        # Draw red dot at (x, y)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(screenshot)
        r = 5
        draw.ellipse([request.x - r, request.y - r, request.x + r, request.y + r], fill="red")
        # Draw label
        draw.text((request.x + r + 2, request.y - r), request.label, fill="red")

        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.info("Screen annotated", x=request.x, y=request.y, label=request.label)
        return {
            "success": True,
            "image_base64": img_str,
            "annotation": {"x": request.x, "y": request.y, "label": request.label}
        }
    except Exception as e:
        logger.error("Screen annotation failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
