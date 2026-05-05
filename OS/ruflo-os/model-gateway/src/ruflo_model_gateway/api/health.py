"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(request: Request) -> dict[str, str | bool]:
    """Readiness probe — checks that registry is initialized."""
    registry = getattr(request.app.state, "registry", None)
    is_ready = registry is not None
    return {"status": "ready" if is_ready else "not_ready", "registry": is_ready}
