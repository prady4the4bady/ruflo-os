"""FastAPI wrapper for the accessibility service."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from ruflo_accessibility.operator import GuiOperator

router = APIRouter()
_operator: GuiOperator | None = None


def get_operator() -> GuiOperator:
    global _operator
    if _operator is None:
        _operator = GuiOperator()
    return _operator


class ClickRequest(BaseModel):
    target: str = ""
    x: int | None = None
    y: int | None = None


class TypeRequest(BaseModel):
    text: str


class KeyRequest(BaseModel):
    keys: list[str]


@router.get("/healthz")
async def health():
    return {"status": "ok", "service": "accessibility"}


@router.get("/status")
async def status():
    op = get_operator()
    return op.get_status()


@router.post("/click")
async def click(body: ClickRequest):
    op = get_operator()
    result = await op.click(body.target, body.x, body.y)
    return {"success": result.success, "tier": result.tier_used, "method": result.method, "error": result.error}


@router.post("/type")
async def type_text(body: TypeRequest):
    op = get_operator()
    result = await op.type_text(body.text)
    return {"success": result.success, "tier": result.tier_used, "method": result.method}


@router.post("/key")
async def key_press(body: KeyRequest):
    op = get_operator()
    result = await op.key_press(*body.keys)
    return {"success": result.success, "tier": result.tier_used, "method": result.method}


@router.post("/screenshot")
async def screenshot():
    op = get_operator()
    data = await op.screenshot()
    if data:
        import base64
        return {"success": True, "image_b64": base64.b64encode(data).decode()[:100] + "..."}
    return {"success": False, "error": "Screenshot capture failed"}


def create_app() -> FastAPI:
    app = FastAPI(title="Ruflo Accessibility Service", version="0.1.0")
    app.include_router(router, prefix="/api/v1")
    return app
