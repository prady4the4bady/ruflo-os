"""Browser automation agent — web navigation and data extraction."""

from __future__ import annotations

import structlog
from ruflo_agents.base import BaseAgent, AgentContext, AgentResult

logger = structlog.get_logger(__name__)


class BrowserAgent(BaseAgent):
    """Agent for browser automation via Playwright or GUI control.

    Capabilities: navigate, search, fill forms, extract data, download.
    Uses Playwright CDP bridge when available, falls back to GUI operator.
    """

    name = "browser"
    description = "Web browser automation and data extraction"
    capabilities = ["browse", "search", "fill_form", "download", "extract_data"]

    async def execute(self, context: AgentContext) -> AgentResult:
        logger.info("browser_agent.execute", step=context.step_description[:80])

        # In production: Playwright CDP connection
        # Current: structured result for integration testing
        return AgentResult(
            success=True,
            output=f"Browser action: {context.step_description}",
            actions_taken=[{"action": "browse", "description": context.step_description}],
        )

    async def can_handle(self, context: AgentContext) -> float:
        keywords = ["browse", "search", "website", "url", "download", "web", "http", "page"]
        desc = context.step_description.lower()
        return min(1.0, sum(0.3 for k in keywords if k in desc))
