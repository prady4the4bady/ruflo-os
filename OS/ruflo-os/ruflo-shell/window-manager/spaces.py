import structlog
from typing import List, Dict, Optional

logger = structlog.get_logger(__name__)

class Space:
    def __init__(self, index: int, name: str = ""):
        self.index = index
        self.name = name or f"Desktop {index+1}"
        self.windows: List[str] = []  # Window IDs
        self.active = False

class SpacesManager:
    """macOS-style virtual desktops with slide animation."""

    def __init__(self, num_spaces: int = 4):
        self.spaces = [Space(i) for i in range(num_spaces)]
        self.current_space_idx = 0
        self.spaces[0].active = True

    def switch_space(self, index: int) -> None:
        if 0 <= index < len(self.spaces):
            self.spaces[self.current_space_idx].active = False
            self.current_space_idx = index
            self.spaces[index].active = True
            # Trigger slide animation
            self._trigger_animation(index)
            logger.info("Switched space", from_=self.current_space_idx, to=index)

    def _trigger_animation(self, target_idx: int) -> None:
        """Slide animation between spaces."""
        direction = "left" if target_idx > self.current_space_idx else "right"
        # Placeholder: trigger compositor animation
        logger.info("Space animation", direction=direction, duration=0.3)

    def add_window_to_space(self, window_id: str, space_idx: Optional[int] = None) -> None:
        idx = space_idx if space_idx is not None else self.current_space_idx
        if 0 <= idx < len(self.spaces):
            self.spaces[idx].windows.append(window_id)
            logger.info("Window added to space", window=window_id, space=idx)

    def remove_window(self, window_id: str) -> None:
        for space in self.spaces:
            if window_id in space.windows:
                space.windows.remove(window_id)
                logger.info("Window removed from space", window=window_id, space=space.index)

    def get_current_space(self) -> Space:
        return self.spaces[self.current_space_idx]

    def list_spaces(self) -> List[Dict]:
        return [
            {"index": s.index, "name": s.name, "active": s.active, "window_count": len(s.windows)}
            for s in self.spaces
        ]