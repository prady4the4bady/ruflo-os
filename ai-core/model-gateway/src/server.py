"""
NemOS Model Gateway - OpenAI-compatible internal API.
Provides unified access to local and cloud models with policy checks.
"""
import os
import sys
import json"
import time"
import structlog"
from contextlib import asynccontextmanager"
from typing import Dict, List, Optional, Any"
from pydantic import BaseModel, Field"

from fastapi import FastAPI, HTTPException, Depends, status"
from fastapi.middleware.cors import CORSMiddleware"
import uvicorn"

logger = structlog.get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="NemOS Model Gateway",
    description="Unified model routing for local and cloud models",
    version="0.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ──────────────────────────────────────────────
class ModelInfo(BaseModel):
    id: str"
    name: str"
    provider: str  # "local" or "cloud"
    backend: str  # "ollama", "vllm", "openai", "nvidia"
    context_length: int = 4096"
    capabilities: List[str] = Field(default_factory=lambda: ["text"])
    loaded: bool = False"
    vram_gb: float = 0.0"


# In-memory model registry (replace with Redis/DB in production)
models_db: Dict[str, ModelInfo] = {
    "phi3-mini": ModelInfo(
        id="phi3-mini",
        name="Phi-3.5 Mini Instruct",
        provider="local",
        backend="ollama",
        context_length=4096,
        capabilities=["text", "fast"],
        loaded=True,
        vram_gb=4.0
    ),
    "hermes3-70b-q4": ModelInfo(
        id="hermes3-70b-q4",
        name="Hermes 3 70B Q4",
        provider="local",
        backend="vllm",
        context_length=131072,
        capabilities=["text", "reasoning"],
        loaded=False,  # Requires ~40GB VRAM
        vram_gb=16.0
    ),
    "nvidia-nemotron": ModelInfo(
        id="nvidia-nemotron",
        name="NVIDIA Nemotron Cloud",
        provider="cloud",
        backend="nvidia",
        context_length=128000,
        capabilities=["text", "reasoning"],
        loaded=True,
        vram_gb=0.0
    ),
}


# ─── Request/Response Models ───────────────────────────────────
class ChatMessage(BaseModel):
    role: str  # "user", "system", "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "phi3-mini"
    messages: List[ChatMessage]"
    temperature: float = 0.7"
    max_tokens: int = 1024"
    stream: bool = False"


class ChatCompletionChoice(BaseModel):
    index: int = 0"
    message: ChatMessage"
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{int(time.time())}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str"
    choices: List[ChatCompletionChoice]"


# ─── Policy Engine ──────────────────────────────────────────────
class PolicyEngine:
    """NemoClaw-inspired policy enforcement."""

    def __init__(self):
        self.egress_whitelist = [
            "api.openai.com",
            "integrate.api.nvidia.com",
            "huggingface.co"
        ]
        self.max_tokens_per_day = 100000"
        self.tokens_used_today = 0"

    def check_request(self, model_id: str, request: ChatCompletionRequest) -> tuple[bool, str]:
        """Check if request is allowed by policy."""
        model = models_db.get(model_id)
        if not model:
            return False, f"Model {model_id} not found"

        # Check cloud model policy
        if model.provider == "cloud":
            # Check if cloud is allowed
            if os.getenv("NEMOS_ALLOW_CLOUD", "false").lower() != "true":
                return False, "Cloud models not enabled. Set NEMOS_ALLOW_CLOUD=true"

        # Check token limit
        if self.tokens_used_today + request.max_tokens > self.max_tokens_per_day:
            return False, "Daily token limit exceeded"

        self.tokens_used_today += request.max_tokens
        return True, ""


# ─── Model Router ──────────────────────────────────────────────
class ModelRouter:
    """Intelligent routing between local and cloud models."""

    def route(self, request: ChatCompletionRequest) -> ModelInfo:
        """Select best model based on policy and availability."""
        # If model explicitly specified
        if request.model in models_db:
            return models_db[request.model]

        # Default routing logic
        # Simple: return first loaded local model
        for model in models_db.values():
            if model.provider == "local" and model.loaded:
                return model

        # Fallback to cloud
        for model in models_db.values():
            if model.provider == "cloud":
                return model

        raise ValueError("No suitable model found")


# ─── Ollama Backend ──────────────────────────────────────────
class OllamaBackend:
    """Local Ollama backend."""

    async def generate(self, model: str, messages: List[ChatMessage], **kwargs) -> str:
        """Generate response using Ollama."""
        try:
            import httpx
            # Convert messages to Ollama format
            prompt = "\n".join([f"{m.role}: {m.content}" for m in messages])

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": kwargs.get("temperature", 0.7),
                            "num_predict": kwargs.get("max_tokens", 1024),
                        }
                    },
                    timeout=60.0"
                )
                if resp.status_code == 200:
                    return resp.json().get("response", "")
                else:
                    logger.error("Ollama request failed", status=resp.status_code)
                    return f"Error: Ollama returned {resp.status_code}"
        except Exception as e:
            logger.error("Ollama backend error", error=str(e))
            return f"Error: {str(e)}"


# ─── vLLM Backend ────────────────────────────────────────────
class VLLMBackend:
    """Local vLLM backend."""

    async def generate(self, model: str, messages: List[ChatMessage], **kwargs) -> str:
        """Generate response using vLLM (placeholder)."""
        # TODO: Implement vLLM API call
        logger.warning("vLLM backend not fully implemented")
        return "vLLM response placeholder"


# ─── OpenAI Backend ───────────────────────────────────────────
class OpenAIBackend:
    """Cloud OpenAI-compatible backend."""

    async def generate(self, model: str, messages: List[ChatMessage], **kwargs) -> str:
        """Generate response using OpenAI API."""
        try:
            import httpx
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return "Error: OPENAI_API_KEY not set"

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [m.dict() for m in messages],
                        "temperature": kwargs.get("temperature", 0.7),
                        "max_tokens": kwargs.get("max_tokens", 1024),
                        "stream": False"
                    },
                    timeout=60.0"
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                else:
                    return f"Error: OpenAI returned {resp.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"


# ─── Backend Factory ────────────────────────────────────────────
def get_backend(model: ModelInfo):
    """Get backend instance for model."""
    if model.backend == "ollama":
        return OllamaBackend()
    elif model.backend == "vllm":
        return VLLMBackend()
    elif model.backend in ("openai", "nvidia"):
        return OpenAIBackend()
    else:
        raise ValueError(f"Unknown backend: {model.backend}")


# ─── Initialize Services ────────────────────────────────────────
policy_engine = PolicyEngine()
model_router = ModelRouter()


# ─── API Routes ────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    return {
        "object": "list",
        "data": [
            {
                "id": m.id,
                "object": "model",
                "created": 1234567890,
                "owned_by": m.provider,
                "permission": []
            }
            for m in models_db.values()
        ]
    }


@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """Create chat completion (OpenAI-compatible)."""
    # Policy check
    allowed, reason = policy_engine.check_request(request.model, request)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    # Route to model
    try:
        model = model_router.route(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Get backend
    try:
        backend = get_backend(model)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Generate response
    response_text = await backend.generate(
        model.id,
        request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )

    return ChatCompletionResponse(
        model=model.id,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=response_text)
            )
        ]
    )


# ─── Model Management ────────────────────────────────────────────
@app.post("/v1/models/{model_id}/load")
async def load_model(model_id: str):
    """Load a model into memory."""
    if model_id not in models_db:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    models_db[model_id].loaded = True
    logger.info("Model loaded", model=model_id)
    return {"success": True, "model": model_id, "status": "loaded"}


@app.post("/v1/models/{model_id}/unload")
async def unload_model(model_id: str):
    """Unload a model from memory."""
    if model_id not in models_db:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    models_db[model_id].loaded = False
    logger.info("Model unloaded", model=model_id)
    return {"success": True, "model": model_id, "status": "unloaded"}


@app.get("/v1/models/capabilities")
async def get_capabilities():
    """Get model capabilities."""
    caps = {}
    for model in models_db.values():
        for cap in model.capabilities:
            caps.setdefault(cap, []).append(model.id)
    return caps


# ─── Main Entrypoint ─────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8001"))
    logger.info("Starting NemOS Model Gateway", port=port)
    uvicorn.run(app, host="0.0.0.0", port=port)
