"""
Tasks API Routes - Core task submission and management.
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
import time
import structlog
import json
import os

logger = structlog.get_logger(__name__)

router = APIRouter()

# In-memory task store (loaded from disk)
tasks_store: Dict[str, dict] = {}
tasks_path = "/var/ruflo/tasks.json"


class TaskRequest(BaseModel):
    task: str = Field(..., description="Natural language task description")
    mode: str = Field(default="auto", description="Execution mode: auto or manual")
    model_override: Optional[str] = Field(default=None, description="Override default model")


class TaskResponse(BaseModel):
    task_id: str
    status: str
    estimated_steps: int = 10


class TaskStatusResponse(BaseModel):
    task_id: str
    task: str
    status: str
    progress: int = 0
    current_action: str = ""
    result: Optional[str] = None
    created_at: float
    updated_at: float


# Load tasks from disk on startup
def _load_tasks():
    global tasks_store
    try:
        if os.path.exists(tasks_path):
            with open(tasks_path, "r") as f:
                tasks_store = json.load(f)
            logger.info("Tasks loaded from disk", count=len(tasks_store))
    except Exception as e:
        logger.error("Failed to load tasks", error=str(e))


_load_tasks()


def _save_tasks():
    try:
        os.makedirs(os.path.dirname(tasks_path), exist_ok=True)
        with open(tasks_path, "w") as f:
            json.dump(tasks_store, f, indent=2)
    except Exception as e:
        logger.error("Failed to save tasks", error=str(e))


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(request: TaskRequest) -> Dict[str, Any]:
    """
    Submit a new task to the Ruflo Agent.
    Returns task_id and initial status.
    """
    task_id = str(uuid.uuid4())
    now = time.time()

    tasks_store[task_id] = {
        "task_id": task_id,
        "task": request.task,
        "mode": request.mode,
        "model_override": request.model_override,
        "status": "queued",
        "progress": 0,
        "current_action": "",
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "steps": [],
        "estimated_steps": 10
    }
    _save_tasks()

    logger.info("Task created", task_id=task_id, task=request.task[:50])

    # TODO: Trigger agent to start processing

    return {
        "task_id": task_id,
        "status": "queued",
        "estimated_steps": 10
    }


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str) -> Dict[str, Any]:
    """
    Get task status and progress.
    """
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return tasks_store[task_id]


@router.delete("/{task_id}")
async def cancel_task(task_id: str) -> Dict[str, str]:
    """
    Cancel a running task.
    """
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task = tasks_store[task_id]
    if task["status"] in ["completed", "failed", "cancelled"]:
        return {"success": "true", "message": "Task already finished"}

    task["status"] = "cancelled"
    task["updated_at"] = time.time()
    _save_tasks()

    logger.info("Task cancelled", task_id=task_id)
    return {"success": "true", "message": f"Task {task_id} cancelled"}


@router.get("/")
async def list_tasks(
    status_filter: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100)
) -> List[Dict[str, Any]]:
    """
    List tasks with optional status filter.
    """
    tasks = list(tasks_store.values())

    if status_filter:
        tasks = [t for t in tasks if t["status"] == status_filter]

    # Sort by created_at descending
    tasks.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return tasks[:limit]
