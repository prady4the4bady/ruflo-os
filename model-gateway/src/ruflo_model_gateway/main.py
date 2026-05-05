"""FastAPI application entry point for the Ruflo Model Gateway."""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from ruflo_model_gateway.api.health import router as health_router
from ruflo_model_gateway.api.routes import router as api_router
from ruflo_model_gateway.config import get_settings
from ruflo_model_gateway.registry.store import ModelRegistryStore

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialize and teardown resources."""
    settings = get_settings()

    # Initialize model registry
    store = ModelRegistryStore(settings.registry_db_path)
    await store.initialize()
    app.state.registry = store
    app.state.settings = settings

    logger.info(
        "model_gateway.started",
        host=settings.host,
        port=settings.port,
        default_provider=settings.default_provider,
        prefer_local=settings.prefer_local,
    )

    yield

    # Cleanup
    await store.close()
    logger.info("model_gateway.stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Ruflo Model Gateway",
        description=(
            "Unified AI model inference gateway for Ruflo OS. "
            "Provides OpenAI-compatible REST endpoints with multi-provider routing."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Routers
    app.include_router(health_router, tags=["health"])
    app.include_router(api_router, prefix="/v1", tags=["inference"])

    return app


app = create_app()
