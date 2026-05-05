import subprocess
from typing import Optional, Dict, Any
from .base_tool import BaseTool
import structlog

logger = structlog.get_logger(__name__)

class TerminalTool(BaseTool):
    """Execute shell commands."""

    name = "terminal_tool"
    description = "Run shell commands"

    async def execute(self, command: str, timeout: Optional[int] = 30) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}