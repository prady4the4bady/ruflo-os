import json
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)

class SubTask(BaseModel):
    description: str
    required_tools: List[str] = Field(default_factory=list)
    estimated_steps: int = 5
    dependencies: List[str] = Field(default_factory=list)
    completed: bool = False

class TaskPlan(BaseModel):
    task_id: str
    original_task: str
    subtasks: List[SubTask]
    current_subtask_idx: int = 0
    checkpoint_path: Optional[str] = None

class TaskPlanner:
    """Breaks complex tasks into executable sub-tasks."""

    def __init__(self):
        self.plans: Dict[str, TaskPlan] = {}

    def parse_task(self, natural_language: str, task_id: str = None) -> TaskPlan:
        """Parse natural language task into TaskPlan using LLM."""
        task_id = task_id or f"task_{len(self.plans) + 1}"
        logger.info("Parsing task", task=natural_language[:50])

        # Placeholder: LLM-generated plan
        # In production, calls InferenceRouter
        subtasks = [
            SubTask(
                description=f"Analyze task: {natural_language[:30]}",
                required_tools=["screen_capture", "vision_tool"],
                estimated_steps=3
            ),
            SubTask(
                description="Execute first action",
                required_tools=["cursor_control", "keyboard_control"],
                estimated_steps=5,
                dependencies=["0"]
            ),
            SubTask(
                description="Verify result",
                required_tools=["screen_capture", "ocr_engine"],
                estimated_steps=2,
                dependencies=["1"]
            )
        ]

        plan = TaskPlan(
            task_id=task_id,
            original_task=natural_language,
            subtasks=subtasks,
            checkpoint_path=f"/var/ruflo/checkpoints/{task_id}.json"
        )
        self.plans[task_id] = plan
        logger.info("Task plan created", task_id=task_id, subtasks=len(subtasks))
        return plan

    def get_next_subtask(self, task_id: str) -> Optional[SubTask]:
        plan = self.plans.get(task_id)
        if not plan or plan.current_subtask_idx >= len(plan.subtasks):
            return None
        return plan.subtasks[plan.current_subtask_idx]

    def complete_subtask(self, task_id: str) -> None:
        plan = self.plans.get(task_id)
        if plan:
            plan.subtasks[plan.current_subtask_idx].completed = True
            plan.current_subtask_idx += 1
            self._checkpoint(plan)

    def _checkpoint(self, plan: TaskPlan) -> None:
        """Save progress to disk."""
        import os
        os.makedirs(os.path.dirname(plan.checkpoint_path), exist_ok=True)
        with open(plan.checkpoint_path, "w") as f:
            json.dump(plan.dict(), f, indent=2)
        logger.info("Checkpoint saved", task_id=plan.task_id)

    def resume_task(self, task_id: str) -> Optional[TaskPlan]:
        plan = self.plans.get(task_id)
        if plan:
            return plan
        # Load from checkpoint
        checkpoint_path = f"/var/ruflo/checkpoints/{task_id}.json"
        try:
            with open(checkpoint_path, "r") as f:
                data = json.load(f)
                plan = TaskPlan(**data)
                self.plans[task_id] = plan
                return plan
        except FileNotFoundError:
            return None