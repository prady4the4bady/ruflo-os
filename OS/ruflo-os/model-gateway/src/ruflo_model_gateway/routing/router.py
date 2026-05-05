"""Model routing logic — selects the best provider for each request."""

from __future__ import annotations

import structlog

from ruflo_model_gateway.config import Settings
from ruflo_model_gateway.providers.base import BaseProvider
from ruflo_model_gateway.providers.ollama import OllamaProvider
from ruflo_model_gateway.providers.vllm import VLLMProvider
from ruflo_model_gateway.providers.sglang import SGLangProvider
from ruflo_model_gateway.providers.anthropic import AnthropicProvider
from ruflo_model_gateway.providers.openai_provider import OpenAIProvider
from ruflo_model_gateway.providers.gemini import GeminiProvider
from ruflo_model_gateway.registry.store import ModelRegistryStore

logger = structlog.get_logger(__name__)

# Task type → preferred capabilities mapping
TASK_CAPABILITY_MAP: dict[str, list[str]] = {
    "coding": ["coding"],
    "planning": ["planning", "reasoning"],
    "vision": ["vision"],
    "summarization": ["summarization", "planning"],
    "speech": ["speech"],
}


class ModelRouter:
    """Routes inference requests to the best available provider.

    Routing priority:
    1. Exact model match in a specific provider
    2. Task-type-based routing using capability matching
    3. Local preference (if enabled, try local providers first)
    4. Cost budget constraint
    5. Fallback to default provider
    """

    def __init__(self, settings: Settings, registry: ModelRegistryStore) -> None:
        self.settings = settings
        self.registry = registry
        self._providers: dict[str, BaseProvider] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize all configured providers."""
        # Local providers (always available)
        self._providers["ollama"] = OllamaProvider(self.settings.ollama_base_url)
        self._providers["vllm"] = VLLMProvider(self.settings.vllm_base_url)
        self._providers["sglang"] = SGLangProvider(self.settings.sglang_base_url)

        # Cloud providers (need API keys)
        if self.settings.anthropic_api_key:
            self._providers["anthropic"] = AnthropicProvider(self.settings.anthropic_api_key)
        if self.settings.openai_api_key:
            self._providers["openai"] = OpenAIProvider(self.settings.openai_api_key)
        if self.settings.google_api_key:
            self._providers["gemini"] = GeminiProvider(self.settings.google_api_key)

    async def route(
        self,
        model: str,
        task_type: str | None = None,
        prefer_local: bool = True,
        max_cost: float = 1.0,
    ) -> BaseProvider:
        """Select the best provider for the given request parameters.

        Returns the provider instance to use for inference.
        """
        # 1. Check if model specifies a provider prefix (e.g., "ollama/llama3")
        if "/" in model:
            provider_name, _ = model.split("/", 1)
            if provider_name in self._providers:
                logger.info("routing.explicit_provider", provider=provider_name, model=model)
                return self._providers[provider_name]

        # 2. Check registry for model → provider mapping
        registry_entry = await self.registry.get_model(model)
        if registry_entry and registry_entry.provider in self._providers:
            provider = self._providers[registry_entry.provider]
            # Check cost budget
            if registry_entry.cost_per_1k_input <= max_cost:
                logger.info("routing.registry_match", provider=registry_entry.provider, model=model)
                return provider

        # 3. Task-type routing with local preference
        if task_type and prefer_local:
            local_providers = [p for p in self._providers.values() if p.is_local]
            if local_providers:
                # Try first available local provider
                for provider in local_providers:
                    if await provider.health_check():
                        logger.info("routing.local_preferred", provider=provider.name, task=task_type)
                        return provider

        # 4. Local preference fallback
        if prefer_local:
            for name in ["ollama", "vllm", "sglang"]:
                if name in self._providers:
                    provider = self._providers[name]
                    if await provider.health_check():
                        logger.info("routing.local_fallback", provider=name)
                        return provider

        # 5. Cloud fallback
        for name in ["anthropic", "openai", "gemini"]:
            if name in self._providers:
                logger.info("routing.cloud_fallback", provider=name)
                return self._providers[name]

        # 6. Default provider (even if unhealthy, let the error bubble up)
        default = self.settings.default_provider
        if default in self._providers:
            logger.warning("routing.default_fallback", provider=default)
            return self._providers[default]

        # Should not happen if at least one provider is configured
        raise RuntimeError("No providers available for routing")
