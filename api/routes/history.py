"""
History API Routes - Task history management with pagination.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import os
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()

# In-memory history store (loaded from disk on startup)
history_store: List[Dict[str, Any]] = []
history_path = "/var/ruflo/history.json"


class TaskHistoryItem(BaseModel):
    task_id: str
    task: str
    status: str
    created_at: float
    completed_at: Optional[float] = None
    steps: List[Dict] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    result: Optional[str] = None


# Load history from disk on startup
def _load_history():
    global history_store
    try:
        if os.path.exists(history_path):
            with open(history_path, "r") as f:
                history_store = json.load(f)
            logger.info("History loaded from disk", count=len(history_store))
    except Exception as e:
        logger.error("Failed to load history", error=str(e))


_load_history()


def _save_history():
    try:
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        with open(history_path, "w") as f:
            json.dump(history_store, f, indent=2)
    except Exception as e:
        logger.error("Failed to save history", error=str(e))


@router.get("/history")
async def get_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    """
    Get paginated list of past task runs with status and timestamps.
    """
    filtered = history_store
    if status_filter:
        filtered = [h for h in filtered if h.get("status") == status_filter]

    # Sort by created_at descending
    sorted_history = sorted(filtered, key=lambda x: x.get("created_at", 0), reverse=True)

    total = len(sorted_history)
    start = (page - 1) * limit
    end = start + limit
    items = sorted_history[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@router.get("/history/{task_id}")
async def get_task_history(task_id: str) -> Dict[str, Any]:
    """
    Get full task log including steps, screenshots, errors.
    """
    for item in history_store:
        if item.get("task_id") == task_id:
            return item

    raise HTTPException(status_code=404, detail=f"Task {task_id} not found in history")


@router.delete("/history/{task_id}")
async def delete_task_history(task_id: str) -> Dict[str, str]:
    """
    Remove task from history.
    """
    global history_store
    original_count = len(history_store)
    history_store = [h for h in history_store if h.get("task_id") != task_id]

    if len(history_store) < original_count:
        _save_history()
        logger.info("Task deleted from history", task_id=task_id)
        return {"success": "true", "message": f"Task {task_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
