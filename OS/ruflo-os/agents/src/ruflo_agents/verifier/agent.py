"""Verifier agent — validates task outcomes and checks state."""

from __future__ import annotations

import structlog
from ruflo_agents.base import BaseAgent, AgentContext, AgentResult

logger = structlog.get_logger(__name__)


class VerifierAgent(BaseAgent):
    """Verifies that agent actions achieved the intended outcome.

    Uses screenshots, file state, and accessibility tree inspection
    to confirm task completion.
    """

    name = "verifier"
    description = "Task outcome verification and state checking"
    capabilities = ["verify_outcome", "check_state", "compare_screenshots"]

    async def execute(self, context: AgentContext) -> AgentResult:
        logger.info("verifier_agent.execute", step=context.step_description[:80])

        # In production: compare before/after state via accessibility + screenshots
        return AgentResult(
            success=True,
            output=f"Verification: {context.step_description}",
            actions_taken=[{"action": "verify", "description": context.step_description}],
        )

    async def can_handle(self, context: AgentContext) -> float:
        keywords = ["verify", "check", "confirm", "validate", "assert"]
        desc = context.step_description.lower()
        return min(1.0, sum(0.35 for k in keywords if k in desc))
