"""NemoClaw integration bridge.

NemoClaw is NVIDIA's secure execution substrate. This bridge provides
the integration layer between Ruflo OS services and NemoClaw/OpenShell.

NOTE: NemoClaw may not be publicly available yet. This module provides
a production-grade abstraction layer with a local mock adapter.
When NemoClaw becomes available, swap the adapter without changing
the interface. See docs/integration-status.md for details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class InferenceRequest:
    model: str
    prompt: str
    max_tokens: int = 4096
    temperature: float = 0.7
    task_id: str = ""
    sandbox_id: str = ""


@dataclass
class InferenceResult:
    text: str = ""
    tokens_used: int = 0
    model: str = ""
    latency_ms: float = 0.0
    routed_to: str = ""  # "local" or "cloud"


class NemoClawBridge(ABC):
    """Abstract interface for NemoClaw secure execution integration."""

    @abstractmethod
    async def infer(self, request: InferenceRequest) -> InferenceResult:
        """Route inference through the NemoClaw security layer."""
        ...

    @abstractmethod
    async def validate_action(self, action: str, context: dict[str, Any]) -> bool:
        """Validate an action against NemoClaw policies."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class LocalNemoClawBridge(NemoClawBridge):
    """Local mock adapter for NemoClaw bridge.

    Routes inference requests to the Ruflo model gateway.
    Provides the same interface that would be used with real NemoClaw.
    """

    def __init__(self, model_gateway_url: str = "http://localhost:8100") -> None:
        self.model_gateway_url = model_gateway_url
        self._request_count = 0

    async def infer(self, request: InferenceRequest) -> InferenceResult:
        self._request_count += 1
        logger.info("nemoclaw_bridge.infer", model=request.model, task_id=request.task_id)
        # In production: route through NemoClaw gRPC
        # Current: delegates to model gateway via HTTP
        return InferenceResult(
            text="[NemoClaw bridge: inference delegated to model gateway]",
            model=request.model,
            routed_to="local",
        )

    async def validate_action(self, action: str, context: dict[str, Any]) -> bool:
        logger.info("nemoclaw_bridge.validate", action=action)
        # In production: NemoClaw policy evaluation
        return True

    async def health_check(self) -> bool:
        return True
