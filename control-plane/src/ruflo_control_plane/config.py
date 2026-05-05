"""Environment-based configuration for the control plane."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 9000
    log_level: str = "info"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://ruflo:ruflo@localhost:5432/ruflo"
    model_gateway_url: str = "http://localhost:8100"
    max_concurrent_tasks: int = 50
    default_token_budget: int = 100000
    approval_timeout_seconds: int = 300

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    return Settings()
