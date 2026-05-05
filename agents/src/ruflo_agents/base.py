"""Base agent interface — all agents implement this contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentContext:
    """Shared context passed to agents during execution."""
    task_id: str = ""
    goal: str = ""
    step_description: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    tools_available: list[str] = field(default_factory=list)
    model_gateway_url: str = "http://localhost:8100"
    control_plane_url: str = "http://localhost:9000"


@dataclass
class AgentResult:
    """Result returned by an agent after execution."""
    success: bool = False
    output: str = ""
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    error: str | None = None
    should_retry: bool = False
    needs_approval: bool = False
    approval_description: str = ""


class BaseAgent(ABC):
    """Abstract base for all Ruflo OS agents."""

    name: str = "base"
    description: str = ""
    capabilities: list[str] = []

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent's task given the context."""
        ...

    @abstractmethod
    async def can_handle(self, context: AgentContext) -> float:
        """Return confidence (0.0-1.0) that this agent can handle the task."""
        ...

    async def recover(self, context: AgentContext, error: str) -> AgentResult:
        """Attempt to recover from a failed execution."""
        return AgentResult(success=False, error=f"No recovery implemented: {error}")
