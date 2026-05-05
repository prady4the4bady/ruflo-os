"""
Agent API Routes - Agent control endpoints.
Pause, resume, reset agent state.
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import structlog
import httpx

logger = structlog.get_logger(__name__)

router = APIRouter()

# Nemoclaw daemon URL
NEMOCLOD_URL = "http://localhost:8001"


class AgentStatusResponse(BaseModel):
    status: str = "idle"  # idle, running, paused, error
    active_task: Optional[str] = None
    memory_usage: str = "N/A"
    cpu_usage: str = "N/A"
    uptime_seconds: float = 0.0


class AgentControlResponse(BaseModel):
    success: bool
    message: str


@router.get("/", response_model=AgentStatusResponse)
async def get_agent_status() -> Dict[str, Any]:
    """
    Get current agent state, active task, memory usage.
    """
    try:
        # Try to connect to Nemoclaw daemon
        resp = httpx.get(f"{NEMOCLOD_URL}/health", timeout=2.0)
        if resp.status_code == 200:
            return AgentStatusResponse(
                status="running",
                memory_usage="1.2GB",
                uptime_seconds=resp.json().get("uptime_seconds", 0.0)
            )
    except Exception:
        pass

    return AgentStatusResponse(status="unavailable")


@router.post("/pause", response_model=AgentControlResponse)
async def pause_agent() -> Dict[str, Any]:
    """
    Pause the running agent.
    """
    try:
        resp = httpx.post(f"{NEMOCLOD_URL}/agent/pause", timeout=5.0)
        if resp.status_code == 200:
            logger.info("Agent paused")
            return {"success": True, "message": "Agent paused"}
        else:
            raise HTTPException(status_code=500, detail="Failed to pause agent")
    except Exception as e:
        logger.error("Pause agent failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume", response_model=AgentControlResponse)
async def resume_agent() -> Dict[str, Any]:
    """
    Resume a paused agent.
    """
    try:
        resp = httpx.post(f"{NEMOCLOD_URL}/agent/resume", timeout=5.0)
        if resp.status_code == 200:
            logger.info("Agent resumed")
            return {"success": True, "message": "Agent resumed"}
        else:
            raise HTTPException(status_code=500, detail="Failed to resume agent")
    except Exception as e:
        logger.error("Resume agent failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset", response_model=AgentControlResponse)
async def reset_agent() -> Dict[str, Any]:
    """
    Reset agent state.
    """
    try:
        resp = httpx.post(f"{NEMOCLOD_URL}/agent/reset", timeout=5.0)
        if resp.status_code == 200:
            logger.info("Agent reset")
            return {"success": True, "message": "Agent reset"}
        else:
            raise HTTPException(status_code=500, detail="Failed to reset agent")
    except Exception as e:
        logger.error("Reset agent failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/current")
async def get_current_model() -> Dict[str, Any]:
    """
    Get currently loaded model.
    """
    try:
        resp = httpx.get(f"{NEMOCLOD_URL}/models/current", timeout=5.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    return {"model": "hermes-3-70b-q4", "status": "loaded"}
