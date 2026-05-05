"""Health endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "control-plane"}


@router.get("/readyz")
async def readiness() -> dict[str, str]:
    return {"status": "ready"}
