"""Screenshot capture for VLM grounding — Tier D fallback."""

from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class ScreenCapture:
    """Captures screenshots for vision-based GUI grounding.

    Supports multiple backends:
    - grim (Wayland native, preferred)
    - gnome-screenshot
    - scrot (X11)
    - Pillow ImageGrab (fallback)
    """

    BACKENDS = ["grim", "gnome-screenshot", "scrot"]

    def __init__(self) -> None:
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str | None:
        for backend in self.BACKENDS:
            if shutil.which(backend):
                logger.info("screen_capture.backend", backend=backend)
                return backend
        logger.warning("screen_capture.no_backend")
        return None

    async def capture(self, output_path: str | None = None) -> bytes | None:
        """Capture a screenshot and return as PNG bytes."""
        if not self._backend:
            return await self._capture_pillow()

        path = output_path or tempfile.mktemp(suffix=".png")
        try:
            if self._backend == "grim":
                proc = await asyncio.create_subprocess_exec("grim", path)
            elif self._backend == "gnome-screenshot":
                proc = await asyncio.create_subprocess_exec("gnome-screenshot", "-f", path)
            elif self._backend == "scrot":
                proc = await asyncio.create_subprocess_exec("scrot", path)
            else:
                return None

            await asyncio.wait_for(proc.communicate(), timeout=10.0)

            p = Path(path)
            if p.exists():
                data = p.read_bytes()
                if not output_path:
                    p.unlink(missing_ok=True)
                return data
        except Exception as exc:
            logger.error("screen_capture.failed", error=str(exc))
        return None

    async def _capture_pillow(self) -> bytes | None:
        """Fallback capture using Pillow (requires display)."""
        try:
            from PIL import ImageGrab  # type: ignore
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            logger.error("screen_capture.pillow_failed", error=str(exc))
            return None

    @property
    def backend_name(self) -> str:
        return self._backend or "none"
