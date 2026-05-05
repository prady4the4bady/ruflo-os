"""Google Gemini cloud provider adapter."""

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


class GeminiProvider(BaseProvider):
    """Cloud provider for Google Gemini models."""

    name = "gemini"
    is_local = False

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=120.0)

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        model = request.model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        contents = []
        system_instruction = None
        for m in request.messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content or ""}]}
            else:
                role = "user" if m.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.content or ""}]})

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature, "topP": request.top_p,
            },
        }
        if request.max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = request.max_tokens
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        if request.stop:
            payload["generationConfig"]["stopSequences"] = request.stop

        resp = await self._client.post(url, json=payload, params={"key": self.api_key})
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [{}])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

        usage_meta = data.get("usageMetadata", {})
        return ChatCompletionResponse(
            created=int(time.time()), model=model,
            choices=[Choice(index=0, message=ChatMessage(role="assistant", content=text), finish_reason="stop")],
            usage=Usage(
                prompt_tokens=usage_meta.get("promptTokenCount", 0),
                completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                total_tokens=usage_meta.get("totalTokenCount", 0),
            ),
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        model = request.model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"

        contents = []
        for m in request.messages:
            if m.role != "system":
                role = "user" if m.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.content or ""}]})

        payload = {"contents": contents, "generationConfig": {"temperature": request.temperature}}

        async with self._client.stream("POST", url, json=payload, params={"key": self.api_key, "alt": "sse"}) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts)
                        if text:
                            chunk = {
                                "object": "chat.completion.chunk", "model": model,
                                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                            }
                            yield json.dumps(chunk)

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="gemini-2.5-flash", provider="gemini", display_name="Gemini 2.5 Flash",
                      owned_by="google", capabilities=["planning", "coding", "vision"],
                      context_window=1048576, cost_per_1k_input=0.00015, cost_per_1k_output=0.0006),
            ModelInfo(id="gemini-2.5-pro", provider="gemini", display_name="Gemini 2.5 Pro",
                      owned_by="google", capabilities=["planning", "coding", "reasoning"],
                      context_window=1048576, cost_per_1k_input=0.00125, cost_per_1k_output=0.01),
        ]

    async def health_check(self) -> bool:
        return bool(self.api_key)
