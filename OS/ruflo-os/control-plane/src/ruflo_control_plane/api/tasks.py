"""Task lifecycle API — create, get, approve, cancel, replay."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter()


class TaskStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class CreateTaskRequest(BaseModel):
    """Request to create a new task."""
    goal: str = Field(description="Natural language task description")
    priority: TaskPriority = TaskPriority.NORMAL
    token_budget: int | None = None
    requires_approval: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_task_id: str | None = None


class TaskResponse(BaseModel):
    """Task state representation."""
    task_id: str
    goal: str
    status: TaskStatus
    priority: TaskPriority
    token_budget: int
    tokens_used: int = 0
    requires_approval: bool
    created_at: str
    updated_at: str
    parent_task_id: str | None = None
    subtask_ids: list[str] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApproveRequest(BaseModel):
    approved: bool = True
    reason: str | None = None


# In-memory task store (production uses PostgreSQL)
_tasks: dict[str, TaskResponse] = {}


@router.post("/tasks", response_model=TaskResponse)
async def create_task(body: CreateTaskRequest) -> TaskResponse:
    """Create a new task and enqueue it for orchestration."""
    now = datetime.now(timezone.utc).isoformat()
    task = TaskResponse(
        task_id=str(uuid.uuid4()),
        goal=body.goal,
        status=TaskStatus.AWAITING_APPROVAL if body.requires_approval else TaskStatus.PENDING,
        priority=body.priority,
        token_budget=body.token_budget or 100000,
        requires_approval=body.requires_approval,
        created_at=now,
        updated_at=now,
        parent_task_id=body.parent_task_id,
        metadata=body.metadata,
    )
    _tasks[task.task_id] = task
    logger.info("task.created", task_id=task.task_id, goal=body.goal[:80], status=task.status)
    return task


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    """Get task by ID."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: TaskStatus | None = None,
    limit: int = 50,
) -> list[TaskResponse]:
    """List tasks with optional status filter."""
    tasks = list(_tasks.values())
    if status:
        tasks = [t for t in tasks if t.status == status]
    return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]


@router.post("/tasks/{task_id}/approve", response_model=TaskResponse)
async def approve_task(task_id: str, body: ApproveRequest) -> TaskResponse:
    """Approve or reject a task awaiting approval."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if task.status != TaskStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"Task is {task.status}, not awaiting approval")

    now = datetime.now(timezone.utc).isoformat()
    if body.approved:
        task.status = TaskStatus.APPROVED
        logger.info("task.approved", task_id=task_id)
    else:
        task.status = TaskStatus.CANCELLED
        task.error = body.reason or "Rejected by user"
        logger.info("task.rejected", task_id=task_id, reason=body.reason)
    task.updated_at = now
    return task


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str) -> TaskResponse:
    """Cancel a running or pending task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
        raise HTTPException(status_code=409, detail=f"Task already {task.status}")

    task.status = TaskStatus.CANCELLED
    task.updated_at = datetime.now(timezone.utc).isoformat()
    logger.info("task.cancelled", task_id=task_id)
    return task


@router.post("/tasks/{task_id}/replay", response_model=TaskResponse)
async def replay_task(task_id: str) -> TaskResponse:
    """Replay a completed or failed task — creates a new task with the same goal."""
    original = _tasks.get(task_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    now = datetime.now(timezone.utc).isoformat()
    new_task = TaskResponse(
        task_id=str(uuid.uuid4()),
        goal=original.goal,
        status=TaskStatus.PENDING,
        priority=original.priority,
        token_budget=original.token_budget,
        requires_approval=original.requires_approval,
        created_at=now,
        updated_at=now,
        metadata={**original.metadata, "replayed_from": task_id},
    )
    _tasks[new_task.task_id] = new_task
    logger.info("task.replayed", original_id=task_id, new_id=new_task.task_id)
    return new_task
