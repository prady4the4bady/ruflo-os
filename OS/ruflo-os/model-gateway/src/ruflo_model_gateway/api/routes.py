"""OpenAI-compatible REST API routes for the model gateway."""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ruflo_model_gateway.metrics import (
    ACTIVE_REQUESTS,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    TOKENS_USED,
)
from ruflo_model_gateway.providers.base import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ModelInfo,
    Usage,
)
from ruflo_model_gateway.routing.router import ModelRouter

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Request/Response Models ───────────────────────────────────


class ChatRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model: str = Field(description="Model identifier or alias")
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float = 1.0
    stream: bool = False
    stop: list[str] | str | None = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    user: str | None = None

    # Ruflo extensions
    task_type: str | None = Field(
        default=None,
        description="Hint for routing: 'coding', 'planning', 'vision', 'summarization', 'speech'",
    )
    prefer_local: bool | None = Field(
        default=None, description="Override global local preference"
    )
    max_cost: float | None = Field(
        default=None, description="Maximum cost budget for this request"
    )


class ModelListResponse(BaseModel):
    """OpenAI-compatible model list response."""

    object: str = "list"
    data: list[ModelInfo]


class RegistryAddRequest(BaseModel):
    """Request to add a model to the registry."""

    model_id: str = Field(description="Unique model identifier")
    provider: str = Field(description="Provider name: ollama, vllm, sglang, anthropic, openai, gemini")
    display_name: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    context_window: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    source_url: str | None = Field(
        default=None, description="Hugging Face or GitHub URL for model source"
    )


# ── Endpoints ─────────────────────────────────────────────────


@router.post("/chat/completions")
async def chat_completions(body: ChatRequest, request: Request) -> dict[str, Any]:
    """OpenAI-compatible chat completion endpoint with provider routing."""
    settings = request.app.state.settings
    registry = request.app.state.registry

    # Build the internal request
    completion_request = ChatCompletionRequest(
        model=body.model,
        messages=body.messages,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        top_p=body.top_p,
        stream=body.stream,
        stop=body.stop if isinstance(body.stop, list) else ([body.stop] if body.stop else None),
    )

    # Route to the best provider
    model_router = ModelRouter(settings=settings, registry=registry)
    provider = await model_router.route(
        model=body.model,
        task_type=body.task_type,
        prefer_local=body.prefer_local if body.prefer_local is not None else settings.prefer_local,
        max_cost=body.max_cost or settings.max_cost_per_request,
    )

    provider_name = provider.name

    # Track active requests
    ACTIVE_REQUESTS.labels(provider=provider_name).inc()
    start_time = time.monotonic()

    try:
        if body.stream:
            # Return SSE stream
            async def generate():
                async for chunk in provider.stream_chat(completion_request):
                    yield f"data: {chunk}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # Non-streaming completion
        response: ChatCompletionResponse = await provider.chat(completion_request)

        # Record metrics
        duration = time.monotonic() - start_time
        REQUEST_COUNT.labels(
            provider=provider_name, model=body.model, status="success"
        ).inc()
        REQUEST_LATENCY.labels(provider=provider_name, model=body.model).observe(duration)

        if response.usage:
            TOKENS_USED.labels(
                provider=provider_name, model=body.model, direction="input"
            ).inc(response.usage.prompt_tokens)
            TOKENS_USED.labels(
                provider=provider_name, model=body.model, direction="output"
            ).inc(response.usage.completion_tokens)

        logger.info(
            "inference.completed",
            provider=provider_name,
            model=body.model,
            duration_ms=round(duration * 1000),
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

        return response.model_dump()

    except Exception as exc:
        duration = time.monotonic() - start_time
        REQUEST_COUNT.labels(
            provider=provider_name, model=body.model, status="error"
        ).inc()
        REQUEST_LATENCY.labels(provider=provider_name, model=body.model).observe(duration)
        logger.error(
            "inference.failed",
            provider=provider_name,
            model=body.model,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"Provider error: {exc}") from exc

    finally:
        ACTIVE_REQUESTS.labels(provider=provider_name).dec()


@router.get("/models")
async def list_models(request: Request) -> ModelListResponse:
    """List all available models across all providers."""
    registry = request.app.state.registry
    models = await registry.list_models()
    return ModelListResponse(data=models)


@router.post("/models/register")
async def register_model(body: RegistryAddRequest, request: Request) -> dict[str, str]:
    """Register a new model in the gateway registry."""
    registry = request.app.state.registry
    await registry.add_model(
        model_id=body.model_id,
        provider=body.provider,
        display_name=body.display_name or body.model_id,
        capabilities=body.capabilities,
        context_window=body.context_window,
        cost_per_1k_input=body.cost_per_1k_input,
        cost_per_1k_output=body.cost_per_1k_output,
        source_url=body.source_url,
    )
    logger.info("model.registered", model_id=body.model_id, provider=body.provider)
    return {"status": "registered", "model_id": body.model_id}


@router.delete("/models/{model_id}")
async def deregister_model(model_id: str, request: Request) -> dict[str, str]:
    """Remove a model from the registry."""
    registry = request.app.state.registry
    await registry.remove_model(model_id)
    logger.info("model.deregistered", model_id=model_id)
    return {"status": "deregistered", "model_id": model_id}
