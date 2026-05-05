"""
Models API Routes - Model management endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import httpx
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()

# Nemoclaw daemon URL
NEMOCLOW_URL = "http://localhost:8001"


class ModelPullRequest(BaseModel):
    source: str = Field(..., description="huggingface, github, ollama, or url")
    identifier: str = Field(..., description="Model ID, repo, or URL")


class ModelInfo(BaseModel):
    id: str
    name: str
    type: str
    source: str
    repo_id: Optional[str] = None
    filename: Optional[str] = None
    context_length: int = 4096
    use_cases: List[str] = Field(default_factory=list)
    loaded: bool = False
    vram_required_gb: float = 0.0


@router.get("/", response_model=List[ModelInfo])
async def list_models() -> List[Dict[str, Any]]:
    """
    List available models from registry.
    """
    try:
        resp = httpx.get(f"{NEMOCLOW_URL}/models", timeout=5.0)
        if resp.status_code == 200:
            return resp.json().get("models", [])
    except Exception as e:
        logger.error("Failed to reach Nemoclaw", error=str(e))

    # Fallback to local registry
    import json
    import os
    registry_path = "/opt/ruflo/models/registry/model_registry.json"
    if os.path.exists(registry_path):
        with open(registry_path, "r") as f:
            data = json.load(f)
            return data.get("models", [])
    return []


@router.post("/pull", status_code=status.HTTP_202_ACCEPTED)
async def pull_model(request: ModelPullRequest) -> Dict[str, Any]:
    """
    Pull a new model from HuggingFace or GitHub.
    """
    try:
        resp = httpx.post(
            f"{NEMOCLOW_URL}/models/pull",
            json={"source": request.source, "identifier": request.identifier},
            timeout=10.0
        )
        if resp.status_code in (200, 202):
            logger.info("Model pull started", source=request.source, identifier=request.identifier)
            return {"success": True, "message": f"Pulling {request.identifier} from {request.source}"}
        else:
            raise HTTPException(status_code=resp.status_code, detail="Model pull failed")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timeout")
    except Exception as e:
        logger.error("Model pull error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{model_id}", status_code=status.HTTP_200_OK)
async def delete_model(model_id: str) -> Dict[str, str]:
    """
    Remove a model from registry.
    """
    try:
        resp = httpx.delete(f"{NEMOCLOW_URL}/models/{model_id}", timeout=5.0)
        if resp.status_code == 200:
            logger.info("Model deleted", model_id=model_id)
            return {"success": "true", "message": f"Model {model_id} deleted"}
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    except Exception as e:
        logger.error("Model delete error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{model_id}/default")
async def set_default_model(model_id: str) -> Dict[str, Any]:
    """
    Set a model as the default for new tasks.
    """
    try:
        resp = httpx.post(
            f"{NEMOCLOW_URL}/models/{model_id}/default",
            timeout=5.0
        )
        if resp.status_code == 200:
            logger.info("Default model set", model_id=model_id)
            return {"success": True, "message": f"{model_id} set as default"}
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    except Exception as e:
        logger.error("Set default error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{model_id}")
async def get_model(model_id: str) -> Dict[str, Any]:
    """
    Get details of a specific model.
    """
    models = await list_models()
    for model in models:
        if model.get("id") == model_id:
            return model
    raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
