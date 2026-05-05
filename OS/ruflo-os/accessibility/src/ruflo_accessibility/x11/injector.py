"""xdotool X11/XWayland input injector — Tier C fallback."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class X11InputResult:
    success: bool = False
    method: str = "xdotool"
    error: str | None = None


class XdotoolInjector:
    """X11 input injection via xdotool. Only for X11/XWayland sessions."""

    def __init__(self) -> None:
        self.available = shutil.which("xdotool") is not None

    async def _run(self, *args: str) -> X11InputResult:
        if not self.available:
            return X11InputResult(success=False, error="xdotool not available")
        try:
            proc = await asyncio.create_subprocess_exec(
                "xdotool", *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode == 0:
                return X11InputResult(success=True)
            return X11InputResult(success=False, error=stderr.decode().strip())
        except Exception as exc:
            return X11InputResult(success=False, error=str(exc))

    async def click(self, x: int, y: int, button: int = 1) -> X11InputResult:
        await self._run("mousemove", str(x), str(y))
        return await self._run("click", str(button))

    async def type_text(self, text: str, delay_ms: int = 12) -> X11InputResult:
        return await self._run("type", "--delay", str(delay_ms), text)

    async def key(self, *keys: str) -> X11InputResult:
        return await self._run("key", "+".join(keys))

    async def get_active_window(self) -> str | None:
        if not self.available:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "getactivewindow",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip()
        except Exception:
            return None
