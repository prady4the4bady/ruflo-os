"""Anthropic cloud provider adapter."""

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

ANTHROPIC_MODELS = [
    ModelInfo(id="claude-sonnet-4-20250514", provider="anthropic", display_name="Claude Sonnet 4",
             owned_by="anthropic", capabilities=["coding", "planning", "reasoning"],
             context_window=200000, cost_per_1k_input=0.003, cost_per_1k_output=0.015),
    ModelInfo(id="claude-opus-4-20250514", provider="anthropic", display_name="Claude Opus 4",
             owned_by="anthropic", capabilities=["coding", "planning", "reasoning"],
             context_window=200000, cost_per_1k_input=0.015, cost_per_1k_output=0.075),
]


class AnthropicProvider(BaseProvider):
    """Cloud provider for Anthropic Claude models."""

    name = "anthropic"
    is_local = False

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=120.0,
        )

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        system_msg = ""
        messages = []
        for m in request.messages:
            if m.role == "system":
                system_msg = m.content or ""
            else:
                messages.append({"role": m.role, "content": m.content or ""})

        payload: dict = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }
        if system_msg:
            payload["system"] = system_msg
        if request.stop:
            payload["stop_sequences"] = request.stop

        response = await self._client.post("/v1/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        usage_data = data.get("usage", {})
        return ChatCompletionResponse(
            id=data.get("id", ""), created=int(time.time()), model=data.get("model", request.model),
            choices=[Choice(index=0, message=ChatMessage(role="assistant", content=content), finish_reason="stop")],
            usage=Usage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            ),
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        system_msg = ""
        messages = []
        for m in request.messages:
            if m.role == "system":
                system_msg = m.content or ""
            else:
                messages.append({"role": m.role, "content": m.content or ""})

        payload: dict = {
            "model": request.model, "messages": messages,
            "max_tokens": request.max_tokens or 4096, "stream": True,
            "temperature": request.temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        async with self._client.stream("POST", "/v1/messages", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            chunk = {
                                "object": "chat.completion.chunk", "model": request.model,
                                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                            }
                            yield json.dumps(chunk)

    async def list_models(self) -> list[ModelInfo]:
        return ANTHROPIC_MODELS

    async def health_check(self) -> bool:
        return bool(self.api_key)
