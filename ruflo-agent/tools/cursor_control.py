import time
from typing import Tuple, Optional
import structlog
from .base_tool import BaseTool

logger = structlog.get_logger(__name__)

class CursorControl(BaseTool):
    """Mouse movement and click control with humanlike bezier curves."""

    name = "cursor_control"
    description = "Move cursor, click, drag, scroll"

    async def execute(self, action: str, **kwargs) -> dict:
        if action == "move":
            return await self.move_to(kwargs.get("x", 0), kwargs.get("y", 0), kwargs.get("duration", 0.3))
        elif action == "click":
            return await self.click(kwargs.get("button", "left"), kwargs.get("double", False))
        elif action == "right_click":
            return await self.right_click()
        elif action == "drag":
            return await self.drag_from_to(kwargs["x1"], kwargs["y1"], kwargs["x2"], kwargs["y2"])
        elif action == "scroll":
            return await self.scroll(kwargs.get("direction", "down"), kwargs.get("amount", 3))
        else:
            return {"success": False, "error": f"Unknown action {action}"}

    async def move_to(self, x: int, y: int, duration: float = 0.3) -> dict:
        """Smooth bezier curve movement to target coordinates."""
        try:
            # Placeholder for bezier movement (ydotool/kernel device)
            # ydotool mousemove --sync --absolute x y
            import subprocess
            subprocess.run(["ydotool", "mousemove", "--absolute", str(x), str(y)], check=True)
            time.sleep(duration)
            logger.info("Cursor moved", x=x, y=y)
            return {"success": True, "x": x, "y": y}
        except Exception as e:
            logger.error("Cursor move failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def click(self, button: str = "left", double: bool = False) -> dict:
        btn_map = {"left": "1", "right": "2", "middle": "3"}
        btn = btn_map.get(button, "1")
        try:
            import subprocess
            if double:
                subprocess.run(["ydotool", "click", btn], check=True)
                time.sleep(0.1)
            subprocess.run(["ydotool", "click", btn], check=True)
            logger.info("Click executed", button=button, double=double)
            return {"success": True, "button": button}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def right_click(self) -> dict:
        return await self.click("right")

    async def drag_from_to(self, x1: int, y1: int, x2: int, y2: int) -> dict:
        try:
            await self.move_to(x1, y1, 0.1)
            import subprocess
            subprocess.run(["ydotool", "mousemove", "--absolute", str(x2), str(y2)], check=True)
            logger.info("Drag completed", from=(x1,y1), to=(x2,y2))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 3) -> dict:
        scroll_map = {"up": "4", "down": "5", "left": "6", "right": "7"}
        btn = scroll_map.get(direction, "5")
        try:
            import subprocess
            for _ in range(amount):
                subprocess.run(["ydotool", "click", btn], check=True)
                time.sleep(0.05)
            logger.info("Scroll executed", direction=direction, amount=amount)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}