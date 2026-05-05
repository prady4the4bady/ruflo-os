"""Recovery hooks — handles agent failures and retries."""

from __future__ import annotations

from typing import Any
import structlog

from ruflo_agents.base import AgentContext, AgentResult

logger = structlog.get_logger(__name__)


async def attempt_recovery(
    agent_name: str,
    context: AgentContext,
    error: str,
    attempt: int = 1,
    max_attempts: int = 3,
) -> AgentResult:
    """Generic recovery hook for failed agent executions.

    Strategies:
    1. Retry with same parameters (transient failures)
    2. Retry with modified context (e.g., different model, simpler prompt)
    3. Escalate to different agent type
    4. Request human intervention
    """
    logger.warning("recovery.attempting", agent=agent_name, attempt=attempt, error=error[:100])

    if attempt >= max_attempts:
        return AgentResult(
            success=False,
            error=f"Recovery exhausted after {attempt} attempts: {error}",
            needs_approval=True,
            approval_description=f"Agent {agent_name} failed after {attempt} retries. Manual intervention needed.",
        )

    # Strategy 1: Simple retry (handles transient network/model errors)
    return AgentResult(
        success=False,
        error=error,
        should_retry=True,
    )
