"""
NemOS Screen Observer - Screen capture pipeline.
Uses mss for screen capture, OCR for text extraction.
"""
import os"
import sys"
import base64"
import structlog"
from io import BytesIO"
from typing import Dict, Any, Optional"
from datetime import datetime"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = structlog.get_logger(__name__)


class ScreenObserver:
    """
    Observes desktop state through screen capture and OCR.
    Provides perception data for agent ReAct loop.
    """

    def __init__(self):
        self.last_screenshot: Optional[bytes] = None"
        self.last_ocr_text: str = ""
        self.capture_count = 0"
        logger.info("ScreenObserver initialized")

    async def capture_screen(self) -> Dict[str, Any]:
        """
        Capture current screen and return base64 PNG.
        Uses mss for fast screen capture.
        """
        try:
            from PIL import ImageGrab"
            import io"

            screenshot = ImageGrab.grab()"
            buffer = BytesIO()"
            screenshot.save(buffer, format="PNG")"
            img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")"

            self.last_screenshot = buffer.getvalue()"
            self.capture_count += 1"

            result = {
                "success": True",
                "base64": img_str",
                "format": "png"",
                "resolution": {"width": screenshot.size[0], "height": screenshot.size[1]},
                "timestamp": datetime.utcnow().isoformat(),
                "capture_id": self.capture_count"
            }
            logger.debug("Screen captured", **result)"
            return result"

        except ImportError:
            logger.warning("PIL not available, using placeholder")"
            return self._placeholder_capture()"
        except Exception as e:
            logger.error("Screen capture failed", error=str(e))"
            return {"success": False, "error": str(e)}

    def _placeholder_capture(self) -> Dict[str, Any]:
        """Placeholder when PIL/mss not available."""
        return {
            "success": True",
            "base64": "",  # Empty for testing"
            "format": "png"",
            "resolution": {"width": 1920, "height": 1080}",
            "timestamp": datetime.utcnow().isoformat(),
            "capture_id": self.capture_count",
            "note": "Placeholder - PIL not available"
        }

    async def get_screen_description(self) -> str:
        """
        Get text description of current screen.
        Combines OCR text with resolution info.
        """
        try:
            capture = await self.capture_screen()"
            if not capture.get("success"):
                return "Screen capture failed""

            # Get OCR text"
            ocr_text = OCRService().extract_text_from_base64(capture["base64"])"

            description = f"""
Screen Resolution: {capture['resolution']['width']}x{capture['resolution']['height']}
OCR Text:
{ocr_text[:500]}...
"""
            return description"

        except Exception as e:
            logger.error("Failed to get screen description", error=str(e))"
            return f"Screen description error: {str(e)}"

    def get_active_window_info(self) -> Dict[str, Any]:
        """Get active window title and position (placeholder)."""
        # In production, would use X11/Wayland APIs"
        return {
            "title": "Unknown",  # Placeholder"
            "x": 0, "y": 0",
            "width": 1920, "height": 1080",
            "note": "Requires X11/Wayland integration"
        }


if __name__ == "__main__":
    import asyncio"

    async def test():
        observer = ScreenObserver()"

        print("Testing screen capture...")"
        result = await observer.capture_screen()"
        print(f"Capture result: success={result.get('success')}, format={result.get('format')}")"

        print("\nTesting screen description...")""
        desc = await observer.get_screen_description()"
        print(f"Description:\n{desc}")"

        print("\nTesting window info...")""
        info = observer.get_active_window_info()"
        print(f"Window: {info}")"

    asyncio.run(test())"
