"""Task orchestration engine — decomposition, scheduling, dependency tracking."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class StepStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskStep:
    """A single step in a decomposed task plan."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    agent_type: str = "general"
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    retries: int = 0
    max_retries: int = 3


@dataclass
class TaskPlan:
    """A decomposed task plan with ordered steps and dependencies."""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    current_step_index: int = 0


class OrchestratorEngine:
    """Task orchestration engine.

    Responsibilities:
    - Decompose high-level goals into step plans
    - Track dependencies between steps
    - Schedule steps to appropriate agents
    - Manage token budgets
    - Handle retries and recovery
    """

    def __init__(self, model_gateway_url: str = "http://localhost:8100") -> None:
        self.model_gateway_url = model_gateway_url
        self._plans: dict[str, TaskPlan] = {}

    async def decompose(self, task_id: str, goal: str) -> TaskPlan:
        """Decompose a high-level goal into executable steps.

        In production, this calls the model gateway to generate a plan.
        Currently uses a template-based decomposition.
        """
        steps = [
            TaskStep(description=f"Analyze goal: {goal[:100]}", agent_type="planner"),
            TaskStep(description="Identify required tools and permissions", agent_type="planner"),
            TaskStep(description="Execute primary action", agent_type="executor"),
            TaskStep(description="Verify result", agent_type="verifier"),
        ]
        # Set up dependencies (linear chain for now)
        for i in range(1, len(steps)):
            steps[i].depends_on = [steps[i - 1].step_id]

        plan = TaskPlan(task_id=task_id, steps=steps)
        self._plans[plan.plan_id] = plan
        logger.info("orchestrator.plan_created", plan_id=plan.plan_id, steps=len(steps))
        return plan

    def get_ready_steps(self, plan_id: str) -> list[TaskStep]:
        """Get steps that are ready to execute (all dependencies met)."""
        plan = self._plans.get(plan_id)
        if not plan:
            return []

        completed_ids = {s.step_id for s in plan.steps if s.status == StepStatus.COMPLETED}
        ready = []
        for step in plan.steps:
            if step.status != StepStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in step.depends_on):
                ready.append(step)
        return ready

    async def complete_step(self, plan_id: str, step_id: str, result: dict[str, Any]) -> None:
        """Mark a step as completed with its result."""
        plan = self._plans.get(plan_id)
        if not plan:
            return
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = StepStatus.COMPLETED
                step.result = result
                logger.info("orchestrator.step_completed", plan_id=plan_id, step_id=step_id)
                break

    async def fail_step(self, plan_id: str, step_id: str, error: str) -> bool:
        """Mark a step as failed. Returns True if retries remain."""
        plan = self._plans.get(plan_id)
        if not plan:
            return False
        for step in plan.steps:
            if step.step_id == step_id:
                step.retries += 1
                if step.retries < step.max_retries:
                    step.status = StepStatus.PENDING
                    logger.warning("orchestrator.step_retry", step_id=step_id, retry=step.retries)
                    return True
                step.status = StepStatus.FAILED
                logger.error("orchestrator.step_failed", step_id=step_id, error=error)
                return False
        return False
