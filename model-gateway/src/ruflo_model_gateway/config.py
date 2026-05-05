"""Environment-based configuration for the model gateway."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Model gateway configuration loaded from environment variables."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8100
    log_level: str = "info"
    environment: str = "development"

    # Provider endpoints
    ollama_base_url: str = "http://localhost:11434"
    vllm_base_url: str = "http://localhost:8000"
    sglang_base_url: str = "http://localhost:30000"

    # Cloud provider API keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # Registry
    registry_db_path: Path = Field(default=Path("./data/model_registry.db"))

    # Routing
    default_provider: str = "ollama"
    prefer_local: bool = True
    max_cost_per_request: float = 1.00

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
