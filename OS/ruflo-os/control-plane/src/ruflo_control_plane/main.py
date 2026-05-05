"""FastAPI application for the Ruflo OS control plane."""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from ruflo_control_plane.api.health import router as health_router
from ruflo_control_plane.api.tasks import router as tasks_router
from ruflo_control_plane.api.websocket import router as ws_router
from ruflo_control_plane.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    app.state.settings = settings
    # Connection pool would be initialized here in production
    logger.info("control_plane.started", port=settings.port)
    yield
    logger.info("control_plane.stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Ruflo Control Plane",
        description="Task orchestration, policy enforcement, and audit for Ruflo OS",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else [],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    app.include_router(health_router, tags=["health"])
    app.include_router(tasks_router, prefix="/api/v1", tags=["tasks"])
    app.include_router(ws_router, prefix="/ws", tags=["websocket"])
    return app


app = create_app()
