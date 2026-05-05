"""OpenAI cloud provider adapter."""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx
import structlog

from ruflo_model_gateway.providers.base import (
    BaseProvider, ChatCompletionRequest, ChatCompletionResponse,
    ChatMessage, Choice, ModelInfo, Usage,
)

logger = structlog.get_logger(__name__)


class OpenAIProvider(BaseProvider):
    """Cloud provider for OpenAI models."""

    name = "openai"
    is_local = False

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=120.0,
        )

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature, "top_p": request.top_p,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.stop:
            payload["stop"] = request.stop

        resp = await self._client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choices = [
            Choice(index=c["index"], message=ChatMessage(**c["message"]),
                   finish_reason=c.get("finish_reason", "stop"))
            for c in data.get("choices", [])
        ]
        u = data.get("usage", {})
        return ChatCompletionResponse(
            id=data["id"], created=data["created"], model=data["model"], choices=choices,
            usage=Usage(prompt_tokens=u.get("prompt_tokens", 0),
                        completion_tokens=u.get("completion_tokens", 0),
                        total_tokens=u.get("total_tokens", 0)),
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        payload = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature, "stream": True,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with self._client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        break
                    yield chunk

    async def list_models(self) -> list[ModelInfo]:
        try:
            resp = await self._client.get("/v1/models")
            resp.raise_for_status()
            return [
                ModelInfo(id=m["id"], owned_by=m.get("owned_by", "openai"), provider="openai",
                          display_name=m["id"])
                for m in resp.json().get("data", [])
            ]
        except Exception:
            return []

    async def health_check(self) -> bool:
        return bool(self.api_key)
