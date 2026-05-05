import subprocess
from typing import Optional, Dict, Any
from .base_tool import BaseTool
import structlog

logger = structlog.get_logger(__name__)

class WindowManager(BaseTool):
    """Window focus, minimize, maximize using wmctrl."""

    name = "window_manager"
    description = "Manage application windows"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        try:
            if action == "focus":
                return await self.focus_window(kwargs["window_title"])
            elif action == "minimize":
                return await self.minimize_window(kwargs.get("window_id"))
            elif action == "maximize":
                return await self.maximize_window(kwargs.get("window_id"))
            else:
                return {"success": False, "error": f"Unknown action {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def focus_window(self, title: str) -> Dict[str, Any]:
        subprocess.run(["wmctrl", "-a", title], check=True)
        logger.info("Window focused", title=title)
        return {"success": True}

    async def minimize_window(self, window_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["wmctrl", "-r", window_id or ":ACTIVE:", "-b", "add", "minimized"]
        subprocess.run(cmd, check=True)
        return {"success": True}

    async def maximize_window(self, window_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["wmctrl", "-r", window_id or ":ACTIVE:", "-b", "add", "maximized_vert", "maximized_horz"]
        subprocess.run(cmd, check=True)
        return {"success": True}