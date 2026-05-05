"""Abstract base provider interface for model inference backends."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field


# ── Shared Data Models ─────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: str = Field(description="Message role: system, user, assistant, tool")
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    """Internal chat completion request (provider-agnostic)."""

    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float = 1.0
    stream: bool = False
    stop: list[str] | None = None


class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    """A single completion choice."""

    index: int = 0
    message: ChatMessage
    finish_reason: str | None = "stop"


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: list[Choice] = Field(default_factory=list)
    usage: Usage | None = None


class ModelInfo(BaseModel):
    """Model metadata for the registry."""

    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = ""
    provider: str = ""
    display_name: str = ""
    capabilities: list[str] = Field(default_factory=list)
    context_window: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    source_url: str | None = None


# ── Abstract Provider ──────────────────────────────────────────


class BaseProvider(ABC):
    """Abstract provider interface — all providers must implement this."""

    name: str = "base"
    is_local: bool = False

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute a non-streaming chat completion."""
        ...

    @abstractmethod
    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Execute a streaming chat completion, yielding JSON chunks."""
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models from this provider."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is reachable and healthy."""
        ...
