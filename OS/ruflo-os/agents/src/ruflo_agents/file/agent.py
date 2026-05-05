"""File agent — filesystem operations via the file broker."""

from __future__ import annotations

import structlog
from ruflo_agents.base import BaseAgent, AgentContext, AgentResult

logger = structlog.get_logger(__name__)


class FileAgent(BaseAgent):
    """Agent for file system operations — always through the file broker.

    Never accesses files directly. Uses opaque handles from the broker.
    Requires approval for destructive operations (delete, overwrite).
    """

    name = "file"
    description = "File system operations via secure broker"
    capabilities = ["read_file", "write_file", "list_dir", "search_files", "move_file"]

    async def execute(self, context: AgentContext) -> AgentResult:
        logger.info("file_agent.execute", step=context.step_description[:80])

        is_destructive = any(
            w in context.step_description.lower()
            for w in ["delete", "remove", "overwrite", "move", "rename"]
        )

        return AgentResult(
            success=True,
            output=f"File operation: {context.step_description}",
            actions_taken=[{"action": "file_op", "description": context.step_description}],
            needs_approval=is_destructive,
            approval_description=f"Destructive file operation: {context.step_description[:100]}" if is_destructive else "",
        )

    async def can_handle(self, context: AgentContext) -> float:
        keywords = ["file", "directory", "folder", "read", "write", "copy", "move", "delete", "create"]
        desc = context.step_description.lower()
        return min(1.0, sum(0.25 for k in keywords if k in desc))
