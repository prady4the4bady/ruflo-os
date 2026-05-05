"""Unified GUI Operator — 4-tier fallback for GUI automation.

Tier A: AT-SPI semantic control (most reliable for GTK/Qt apps)
Tier B: ydotool Wayland input injection
Tier C: xdotool X11/XWayland fallback
Tier D: Screenshot + VLM grounding (last resort)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from ruflo_accessibility.atspi.client import ATSPIClient
from ruflo_accessibility.wayland.injector import YdotoolInjector
from ruflo_accessibility.x11.injector import XdotoolInjector
from ruflo_accessibility.vision.capture import ScreenCapture
from ruflo_accessibility.vision.grounding import VLMGrounding

logger = structlog.get_logger(__name__)


@dataclass
class GuiActionResult:
    success: bool = False
    tier_used: str = ""
    method: str = ""
    details: dict[str, Any] | None = None
    error: str | None = None


class GuiOperator:
    """Unified GUI operator with 4-tier fallback.

    For each action, tries the tiers in order A→B→C→D.
    Falls through to the next tier on failure.
    """

    def __init__(self, model_gateway_url: str = "http://localhost:8100") -> None:
        self.atspi = ATSPIClient()
        self.ydotool = YdotoolInjector()
        self.xdotool = XdotoolInjector()
        self.capture = ScreenCapture()
        self.vlm = VLMGrounding(model_gateway_url)

    async def click(self, target: str, x: int | None = None, y: int | None = None) -> GuiActionResult:
        """Click on a GUI element, using tiered fallback."""
        # Tier A: AT-SPI
        if self.atspi.available:
            nodes = self.atspi.find_by_name(target)
            if nodes:
                node = nodes[0]
                if "click" in node.actions:
                    if self.atspi.do_action(node.path, "click"):
                        return GuiActionResult(success=True, tier_used="A", method="atspi")
                # Use bounds for coordinate-based click
                bx, by, bw, bh = node.bounds
                if bw > 0 and bh > 0:
                    cx, cy = bx + bw // 2, by + bh // 2
                    return await self._click_coords(cx, cy)

        # Use provided coordinates
        if x is not None and y is not None:
            return await self._click_coords(x, y)

        # Tier D: VLM grounding
        screenshot = await self.capture.capture()
        if screenshot:
            import base64
            b64 = base64.b64encode(screenshot).decode()
            result = await self.vlm.ground(b64, f"Find element: {target}")
            if result.found and result.bounds != (0, 0, 0, 0):
                bx, by, bw, bh = result.bounds
                return await self._click_coords(bx + bw // 2, by + bh // 2)

        return GuiActionResult(success=False, error=f"Could not locate target: {target}")

    async def _click_coords(self, x: int, y: int) -> GuiActionResult:
        """Click at coordinates using ydotool → xdotool fallback."""
        # Tier B: ydotool
        if self.ydotool.available:
            result = await self.ydotool.click(x, y)
            if result.success:
                return GuiActionResult(success=True, tier_used="B", method="ydotool")

        # Tier C: xdotool
        if self.xdotool.available:
            result = await self.xdotool.click(x, y)
            if result.success:
                return GuiActionResult(success=True, tier_used="C", method="xdotool")

        return GuiActionResult(success=False, error="No input injector available")

    async def type_text(self, text: str) -> GuiActionResult:
        """Type text using available input method."""
        if self.ydotool.available:
            r = await self.ydotool.type_text(text)
            if r.success:
                return GuiActionResult(success=True, tier_used="B", method="ydotool")

        if self.xdotool.available:
            r = await self.xdotool.type_text(text)
            if r.success:
                return GuiActionResult(success=True, tier_used="C", method="xdotool")

        return GuiActionResult(success=False, error="No input injector available")

    async def key_press(self, *keys: str) -> GuiActionResult:
        """Press key combination."""
        if self.ydotool.available:
            r = await self.ydotool.key(*keys)
            if r.success:
                return GuiActionResult(success=True, tier_used="B", method="ydotool")

        if self.xdotool.available:
            r = await self.xdotool.key(*keys)
            if r.success:
                return GuiActionResult(success=True, tier_used="C", method="xdotool")

        return GuiActionResult(success=False, error="No input injector available")

    async def screenshot(self) -> bytes | None:
        """Capture current screen."""
        return await self.capture.capture()

    def get_status(self) -> dict[str, bool]:
        """Get availability status of all tiers."""
        return {
            "atspi": self.atspi.available,
            "ydotool": self.ydotool.available,
            "xdotool": self.xdotool.available,
            "screenshot": self.capture.backend_name != "none",
        }
