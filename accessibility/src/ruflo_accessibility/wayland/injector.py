"""ydotool Wayland input injector — Tier B in fallback chain."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class InputResult:
    success: bool = False
    method: str = "ydotool"
    error: str | None = None


class YdotoolInjector:
    """Wayland-safe input injection via ydotool.

    ydotool operates through /dev/uinput and works regardless of
    display server (Wayland or X11). Requires ydotoold daemon running.
    """

    def __init__(self) -> None:
        self.available = shutil.which("ydotool") is not None
        if not self.available:
            logger.info("ydotool.not_available", reason="ydotool not found in PATH")

    async def _run(self, *args: str) -> InputResult:
        if not self.available:
            return InputResult(success=False, error="ydotool not available")
        try:
            proc = await asyncio.create_subprocess_exec(
                "ydotool", *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode == 0:
                return InputResult(success=True)
            return InputResult(success=False, error=stderr.decode().strip())
        except asyncio.TimeoutError:
            return InputResult(success=False, error="ydotool command timed out")
        except Exception as exc:
            return InputResult(success=False, error=str(exc))

    async def click(self, x: int, y: int, button: str = "left") -> InputResult:
        btn_code = {"left": "0x00", "right": "0x01", "middle": "0x02"}.get(button, "0x00")
        await self._run("mousemove", "--absolute", "-x", str(x), "-y", str(y))
        return await self._run("click", btn_code)

    async def type_text(self, text: str, delay_ms: int = 12) -> InputResult:
        return await self._run("type", "--delay", str(delay_ms), "--", text)

    async def key(self, *keys: str) -> InputResult:
        key_str = "+".join(keys)
        return await self._run("key", key_str)

    async def mouse_move(self, x: int, y: int, absolute: bool = True) -> InputResult:
        args = ["mousemove"]
        if absolute:
            args.extend(["--absolute", "-x", str(x), "-y", str(y)])
        else:
            args.extend(["-x", str(x), "-y", str(y)])
        return await self._run(*args)

    async def scroll(self, amount: int, direction: str = "down") -> InputResult:
        val = str(-amount if direction == "up" else amount)
        return await self._run("mousemove", "-w", val)
