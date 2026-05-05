"""SGLang provider adapter — high-throughput local inference."""

from __future__ import annotations

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


class SGLangProvider(BaseProvider):
    """Provider adapter for SGLang (OpenAI-compatible endpoint)."""

    name = "sglang"
    is_local = True

    def __init__(self, base_url: str = "http://localhost:30000") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload = self._build_payload(request, stream=False)
        response = await self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        return self._parse_response(data, request.model)

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        payload = self._build_payload(request, stream=True)
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
                ModelInfo(id=m["id"], owned_by="sglang", provider="sglang", display_name=m["id"])
                for m in resp.json().get("data", [])
            ]
        except Exception as exc:
            logger.warning("sglang.list_models_failed", error=str(exc))
            return []

    async def health_check(self) -> bool:
        try:
            return (await self._client.get("/v1/models")).status_code == 200
        except Exception:
            return False

    def _build_payload(self, req: ChatCompletionRequest, stream: bool) -> dict:
        p = {
            "model": req.model,
            "messages": [m.model_dump(exclude_none=True) for m in req.messages],
            "temperature": req.temperature, "top_p": req.top_p, "stream": stream,
        }
        if req.max_tokens:
            p["max_tokens"] = req.max_tokens
        if req.stop:
            p["stop"] = req.stop
        return p

    def _parse_response(self, data: dict, model: str) -> ChatCompletionResponse:
        choices = [
            Choice(
                index=c.get("index", 0),
                message=ChatMessage(**c.get("message", {"role": "assistant", "content": ""})),
                finish_reason=c.get("finish_reason", "stop"),
            )
            for c in data.get("choices", [])
        ]
        u = data.get("usage", {})
        return ChatCompletionResponse(
            id=data.get("id", ""), created=data.get("created", int(time.time())),
            model=data.get("model", model), choices=choices,
            usage=Usage(
                prompt_tokens=u.get("prompt_tokens", 0),
                completion_tokens=u.get("completion_tokens", 0),
                total_tokens=u.get("total_tokens", 0),
            ),
        )
