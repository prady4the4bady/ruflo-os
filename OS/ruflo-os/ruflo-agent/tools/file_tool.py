import os
from typing import Optional, Dict, Any, List
from .base_tool import BaseTool
import structlog

logger = structlog.get_logger(__name__)

class FileTool(BaseTool):
    """File system operations."""

    name = "file_tool"
    description = "Read, write, list files"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        try:
            if action == "read":
                return await self.read_file(kwargs["path"])
            elif action == "write":
                return await self.write_file(kwargs["path"], kwargs["content"])
            elif action == "list":
                return await self.list_dir(kwargs.get("path", "."))
            elif action == "delete":
                return await self.delete_file(kwargs["path"])
            else:
                return {"success": False, "error": f"Unknown action {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def read_file(self, path: str) -> Dict[str, Any]:
        with open(path, "r") as f:
            content = f.read()
        return {"success": True, "content": content, "size": len(content)}

    async def write_file(self, path: str, content: str) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return {"success": True, "path": path}

    async def list_dir(self, path: str) -> Dict[str, Any]:
        entries = os.listdir(path)
        return {"success": True, "entries": entries, "count": len(entries)}

    async def delete_file(self, path: str) -> Dict[str, Any]:
        os.remove(path)
        return {"success": True}