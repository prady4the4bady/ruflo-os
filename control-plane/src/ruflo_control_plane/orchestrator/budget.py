"""Token and cost budget management."""

from __future__ import annotations

from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BudgetState:
    """Budget tracking for a single task."""
    task_id: str
    token_limit: int
    tokens_used: int = 0
    cost_limit: float = 10.0
    cost_used: float = 0.0

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.token_limit - self.tokens_used)

    @property
    def cost_remaining(self) -> float:
        return max(0.0, self.cost_limit - self.cost_used)

    @property
    def is_exhausted(self) -> bool:
        return self.tokens_remaining == 0 or self.cost_remaining <= 0.0


class BudgetManager:
    """Manages token and cost budgets across tasks."""

    def __init__(self) -> None:
        self._budgets: dict[str, BudgetState] = {}

    def create_budget(self, task_id: str, token_limit: int = 100000, cost_limit: float = 10.0) -> BudgetState:
        budget = BudgetState(task_id=task_id, token_limit=token_limit, cost_limit=cost_limit)
        self._budgets[task_id] = budget
        return budget

    def consume(self, task_id: str, tokens: int, cost: float = 0.0) -> bool:
        """Consume tokens from a task's budget. Returns False if over-budget."""
        budget = self._budgets.get(task_id)
        if not budget:
            return False
        if budget.is_exhausted:
            logger.warning("budget.exhausted", task_id=task_id)
            return False
        budget.tokens_used += tokens
        budget.cost_used += cost
        if budget.is_exhausted:
            logger.warning("budget.now_exhausted", task_id=task_id,
                           tokens_used=budget.tokens_used, cost_used=budget.cost_used)
        return True

    def get_budget(self, task_id: str) -> BudgetState | None:
        return self._budgets.get(task_id)
