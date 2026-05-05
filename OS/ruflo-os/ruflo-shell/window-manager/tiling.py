import asyncio
from typing import List, Optional, Dict
import structlog

logger = structlog.get_logger(__name__)

class TilingManager:
    """Tiling window management for Ruflo Shell."""

    def __init__(self):
        self.windows: List[Dict] = []
        self.layout: str = "master-stack"  # or "grid", "column"

    def add_window(self, window_id: str, title: str, x: int, y: int, w: int, h: int) -> None:
        self.windows.append({
            "id": window_id,
            "title": title,
            "x": x, "y": y, "w": w, "h": h,
            "tiled": False
        })
        self.tile_windows()

    def remove_window(self, window_id: str) -> None:
        self.windows = [w for w in self.windows if w["id"] != window_id]
        self.tile_windows()

    def tile_windows(self) -> None:
        if not self.windows:
            return

        screen_w, screen_h = 1920, 1080  # Default resolution
        if self.layout == "master-stack":
            master = self.windows[0]
            master["x"], master["y"] = 0, 0
            master["w"], master["h"] = screen_w // 2, screen_h
            master["tiled"] = True

            stack_width = screen_w // 2
            stack_height = screen_h // (len(self.windows) - 1) if len(self.windows) > 1 else screen_h
            for i, win in enumerate(self.windows[1:], 1):
                win["x"], win["y"] = screen_w // 2, (i-1) * stack_height
                win["w"], win["h"] = stack_width, stack_height
                win["tiled"] = True

        logger.info("Windows tiled", count=len(self.windows), layout=self.layout)

    def set_layout(self, layout: str) -> None:
        self.layout = layout
        self.tile_windows()

    def get_window_geometry(self, window_id: str) -> Optional[Dict]:
        return next((w for w in self.windows if w["id"] == window_id), None)