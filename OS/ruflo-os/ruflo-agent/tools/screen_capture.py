from PIL import ImageGrab
from typing import Tuple, Optional
import structlog
from .base_tool import BaseTool

logger = structlog.get_logger(__name__)

class ScreenCapture(BaseTool):
    """Capture screen content for agent perception."""

    name = "screen_capture"
    description = "Capture full screen or region as PIL Image"

    async def execute(self, region: Optional[Tuple[int, int, int, int]] = None) -> dict:
        try:
            if region:
                x, y, w, h = region
                screenshot = ImageGrab.grab(bbox=(x, y, x+w, y+h))
                logger.info("Region captured", region=region)
            else:
                screenshot = ImageGrab.grab()
                logger.info("Full screen captured", size=screenshot.size)

            return {
                "success": True,
                "image": screenshot,
                "size": screenshot.size,
                "mode": screenshot.mode
            }
        except Exception as e:
            logger.error("Screen capture failed", error=str(e))
            return {"success": False, "error": str(e)}

    def capture_full(self) -> "PIL.Image":
        return ImageGrab.grab()

    def capture_region(self, x: int, y: int, w: int, h: int) -> "PIL.Image":
        return ImageGrab.grab(bbox=(x, y, x+w, y+h))

    def get_screen_resolution(self) -> Tuple[int, int]:
        img = ImageGrab.grab()
        return img.size