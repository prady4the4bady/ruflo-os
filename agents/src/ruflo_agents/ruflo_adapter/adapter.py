"""Ruflo swarm adapter — coordinates multi-agent workflows."""

from __future__ import annotations

from typing import Any

import structlog
import httpx

from ruflo_agents.base import BaseAgent, AgentContext, AgentResult

logger = structlog.get_logger(__name__)


class RufloAdapter(BaseAgent):
    """Adapter for the Ruflo multi-agent swarm orchestration system.

    Ruflo coordinates specialist workers via supervisor-worker patterns.
    This adapter bridges Ruflo's swarm coordination with the Ruflo OS
    control plane and agent layer.

    When the Ruflo SDK is available, this adapter delegates to it.
    Currently provides the coordination logic directly.
    """

    name = "ruflo_swarm"
    description = "Multi-agent swarm coordinator"
    capabilities = ["planning", "decomposition", "coordination", "delegation"]

    def __init__(self, model_gateway_url: str = "http://localhost:8100") -> None:
        self.model_gateway_url = model_gateway_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def execute(self, context: AgentContext) -> AgentResult:
        """Decompose goal and coordinate specialist agents."""
        logger.info("ruflo_adapter.execute", goal=context.goal[:80])

        # Call model gateway for planning
        try:
            response = await self._client.post(
                f"{context.model_gateway_url}/v1/chat/completions",
                json={
                    "model": "planner",
                    "messages": [
                        {"role": "system", "content": (
                            "You are a task planner for Ruflo OS. Decompose the user's goal "
                            "into concrete steps. For each step, specify: description, "
                            "agent_type (gui_operator, browser, coding, file, verifier), "
                            "and any dependencies."
                        )},
                        {"role": "user", "content": context.goal},
                    ],
                    "task_type": "planning",
                    "temperature": 0.3,
                },
            )
            if response.status_code == 200:
                data = response.json()
                plan_text = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", 0)
                return AgentResult(
                    success=True, output=plan_text, tokens_used=tokens,
                    actions_taken=[{"action": "plan_generated", "goal": context.goal}],
                )
        except Exception as exc:
            logger.warning("ruflo_adapter.model_unavailable", error=str(exc))

        # Fallback: simple template-based decomposition
        return AgentResult(
            success=True,
            output=f"Plan for: {context.goal}\n1. Analyze requirements\n2. Execute\n3. Verify",
            actions_taken=[{"action": "template_plan", "goal": context.goal}],
        )

    async def can_handle(self, context: AgentContext) -> float:
        return 0.9  # Swarm coordinator handles most tasks
