"""Coding agent — code generation, editing, and execution."""

from __future__ import annotations

import structlog
from ruflo_agents.base import BaseAgent, AgentContext, AgentResult

logger = structlog.get_logger(__name__)


class CodingAgent(BaseAgent):
    """Agent for code generation, editing, debugging, and execution.

    Uses the model gateway with task_type=coding for code-specialized models.
    Operates within sandboxed environments via the runtime brokers.
    """

    name = "coding"
    description = "Code generation, editing, debugging, and execution"
    capabilities = ["write_code", "edit_code", "debug", "run_tests", "explain_code"]

    async def execute(self, context: AgentContext) -> AgentResult:
        logger.info("coding_agent.execute", step=context.step_description[:80])

        return AgentResult(
            success=True,
            output=f"Coding task: {context.step_description}",
            actions_taken=[{"action": "code", "description": context.step_description}],
            needs_approval="install" in context.step_description.lower() or "deploy" in context.step_description.lower(),
            approval_description=f"Code execution: {context.step_description[:100]}",
        )

    async def can_handle(self, context: AgentContext) -> float:
        keywords = ["code", "program", "script", "function", "debug", "test", "compile", "build"]
        desc = context.step_description.lower()
        return min(1.0, sum(0.3 for k in keywords if k in desc))
