"""GUI operator agent — desktop GUI control via accessibility layer."""

from __future__ import annotations

import httpx
import structlog

from ruflo_agents.base import BaseAgent, AgentContext, AgentResult

logger = structlog.get_logger(__name__)


class GuiOperatorAgent(BaseAgent):
    """Agent that controls desktop GUI via the accessibility service."""

    name = "gui_operator"
    description = "Desktop GUI automation via AT-SPI, ydotool, and VLM grounding"
    capabilities = ["gui_control", "click", "type", "navigate", "screenshot"]

    def __init__(self, accessibility_url: str = "http://localhost:8200") -> None:
        self.accessibility_url = accessibility_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def execute(self, context: AgentContext) -> AgentResult:
        logger.info("gui_agent.execute", step=context.step_description[:80])
        actions = []

        # Parse the step description to determine GUI actions
        # In production: LLM-driven action planning
        step = context.step_description.lower()

        if "click" in step:
            target = context.step_description.split("click")[-1].strip().strip('"\'')
            try:
                resp = await self._client.post(
                    f"{self.accessibility_url}/api/v1/click",
                    json={"target": target},
                )
                result = resp.json()
                actions.append({"action": "click", "target": target, "result": result})
            except Exception as exc:
                return AgentResult(success=False, error=str(exc), should_retry=True)

        elif "type" in step:
            text = context.step_description.split("type")[-1].strip().strip('"\'')
            try:
                resp = await self._client.post(
                    f"{self.accessibility_url}/api/v1/type",
                    json={"text": text},
                )
                actions.append({"action": "type", "text": text})
            except Exception as exc:
                return AgentResult(success=False, error=str(exc), should_retry=True)

        return AgentResult(
            success=True,
            output=f"GUI action completed: {context.step_description}",
            actions_taken=actions,
        )

    async def can_handle(self, context: AgentContext) -> float:
        keywords = ["click", "type", "open", "close", "window", "button", "menu", "gui"]
        desc = context.step_description.lower()
        matches = sum(1 for k in keywords if k in desc)
        return min(1.0, matches * 0.25)
