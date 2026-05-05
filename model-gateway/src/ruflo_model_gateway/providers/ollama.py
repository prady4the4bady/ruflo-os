"""Ollama provider adapter — local model inference via Ollama REST API."""

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


class OllamaProvider(BaseProvider):
    """Provider adapter for Ollama (local inference)."""

    name = "ollama"
    is_local = True

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Non-streaming chat completion via Ollama."""
        payload = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        }
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens
        if request.stop:
            payload["options"]["stop"] = request.stop

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        message_data = data.get("message", {})
        return ChatCompletionResponse(
            created=int(time.time()),
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ChatMessage(
                        role=message_data.get("role", "assistant"),
                        content=message_data.get("content", ""),
                    ),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            ),
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Streaming chat completion via Ollama."""
        payload = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        }
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    message = data.get("message", {})
                    content = message.get("content", "")
                    if content:
                        chunk = {
                            "id": f"chatcmpl-stream",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": request.model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": content},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield json.dumps(chunk)
                    if data.get("done", False):
                        final_chunk = {
                            "id": f"chatcmpl-stream",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": request.model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "stop",
                                }
                            ],
                        }
                        yield json.dumps(final_chunk)
                except json.JSONDecodeError:
                    continue

    async def list_models(self) -> list[ModelInfo]:
        """List available models from Ollama."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [
                ModelInfo(
                    id=model["name"],
                    owned_by="ollama",
                    provider="ollama",
                    display_name=model.get("name", ""),
                    context_window=model.get("details", {}).get("parameter_size", 4096),
                )
                for model in data.get("models", [])
            ]
        except Exception as exc:
            logger.warning("ollama.list_models_failed", error=str(exc))
            return []

    async def health_check(self) -> bool:
        """Check Ollama availability."""
        try:
            response = await self._client.get("/")
            return response.status_code == 200
        except Exception:
            return False
