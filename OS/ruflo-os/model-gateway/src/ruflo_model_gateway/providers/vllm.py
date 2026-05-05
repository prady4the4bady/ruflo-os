"""vLLM provider adapter — OpenAI-compatible local inference via vLLM."""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx
import structlog

from ruflo_model_gateway.providers.base import (
    BaseProvider,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ModelInfo,
    Usage,
)

logger = structlog.get_logger(__name__)


class VLLMProvider(BaseProvider):
    """Provider adapter for vLLM (OpenAI-compatible local server)."""

    name = "vllm"
    is_local = True

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Non-streaming chat via vLLM OpenAI-compatible endpoint."""
        payload = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.stop:
            payload["stop"] = request.stop

        response = await self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choices = [
            Choice(
                index=c.get("index", 0),
                message=ChatMessage(**c.get("message", {"role": "assistant", "content": ""})),
                finish_reason=c.get("finish_reason", "stop"),
            )
            for c in data.get("choices", [])
        ]

        usage_data = data.get("usage", {})
        return ChatCompletionResponse(
            id=data.get("id", ""),
            created=data.get("created", int(time.time())),
            model=data.get("model", request.model),
            choices=choices,
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Streaming chat via vLLM — proxies SSE events directly."""
        payload = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": True,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with self._client.stream(
            "POST", "/v1/chat/completions", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    chunk_data = line[6:]
                    if chunk_data.strip() == "[DONE]":
                        break
                    yield chunk_data

    async def list_models(self) -> list[ModelInfo]:
        """List available models from vLLM."""
        try:
            response = await self._client.get("/v1/models")
            response.raise_for_status()
            data = response.json()
            return [
                ModelInfo(
                    id=m["id"],
                    owned_by=m.get("owned_by", "vllm"),
                    provider="vllm",
                    display_name=m["id"],
                )
                for m in data.get("data", [])
            ]
        except Exception as exc:
            logger.warning("vllm.list_models_failed", error=str(exc))
            return []

    async def health_check(self) -> bool:
        """Check vLLM availability."""
        try:
            response = await self._client.get("/v1/models")
            return response.status_code == 200
        except Exception:
            return False
