from typing import Dict, Any, Optional
import structlog
from ..tools import BaseTool

logger = structlog.get_logger(__name__)

class ToolExecutor:
    """Executes computer control tools with error handling and logging."""

    def __init__(self, tools: Optional[Dict[str, BaseTool]] = None):
        self.tools = tools or {}

    def register_tool(self, name: str, tool: BaseTool) -> None:
        self.tools[name] = tool
        logger.info("Tool registered", name=name)

    async def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name not in self.tools:
            raise ValueError(f"Tool {tool_name} not found")

        tool = self.tools[tool_name]
        logger.info("Executing tool", tool=tool_name, params=params)

        try:
            result = await tool.execute(**params)
            logger.info("Tool executed successfully", tool=tool_name, result=result)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error("Tool execution failed", tool=tool_name, error=str(e))
            return {"success": False, "error": str(e)}

    def list_tools(self) -> list:
        return list(self.tools.keys())