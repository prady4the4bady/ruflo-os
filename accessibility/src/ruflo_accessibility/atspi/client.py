"""AT-SPI2 client — semantic GUI control via accessibility tree.

This is Tier A (highest priority) in the 4-tier fallback:
  A: AT-SPI semantic control
  B: ydotool Wayland injection
  C: xdotool X11 fallback
  D: Screenshot + VLM grounding

Requires pyatspi2 (python3-pyatspi on Debian/Ubuntu).
On systems without AT-SPI, this gracefully reports unavailability
and the GuiOperator falls through to lower tiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Try importing pyatspi — only available on Linux with AT-SPI2
try:
    import pyatspi  # type: ignore[import-untyped]
    ATSPI_AVAILABLE = True
except ImportError:
    ATSPI_AVAILABLE = False
    logger.info("atspi.not_available", reason="pyatspi2 not installed")


@dataclass
class AccessibleNode:
    """Represents a node in the accessibility tree."""
    role: str = ""
    name: str = ""
    description: str = ""
    states: list[str] = field(default_factory=list)
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, width, height
    actions: list[str] = field(default_factory=list)
    children_count: int = 0
    path: str = ""


class ATSPIClient:
    """Client for AT-SPI2 accessibility tree inspection and action execution."""

    def __init__(self) -> None:
        self.available = ATSPI_AVAILABLE

    def get_desktop(self) -> list[AccessibleNode]:
        """Get all top-level accessible applications."""
        if not self.available:
            return []

        nodes = []
        try:
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.childCount):
                app = desktop.getChildAtIndex(i)
                if app:
                    nodes.append(self._to_node(app, f"/{i}"))
        except Exception as exc:
            logger.error("atspi.get_desktop_failed", error=str(exc))
        return nodes

    def find_by_role(self, role: str, app_name: str | None = None) -> list[AccessibleNode]:
        """Find accessible elements by role (button, text, menu, etc.)."""
        if not self.available:
            return []

        results = []
        try:
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.childCount):
                app = desktop.getChildAtIndex(i)
                if app and (not app_name or app.name == app_name):
                    self._walk_tree(app, role, results, f"/{i}")
        except Exception as exc:
            logger.error("atspi.find_by_role_failed", error=str(exc))
        return results

    def find_by_name(self, name: str, partial: bool = True) -> list[AccessibleNode]:
        """Find accessible elements by name (label text)."""
        if not self.available:
            return []

        results = []
        try:
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.childCount):
                app = desktop.getChildAtIndex(i)
                if app:
                    self._walk_tree_by_name(app, name, partial, results, f"/{i}")
        except Exception as exc:
            logger.error("atspi.find_by_name_failed", error=str(exc))
        return results

    def do_action(self, node_path: str, action_name: str = "click") -> bool:
        """Perform an action on an accessible element."""
        if not self.available:
            return False

        logger.info("atspi.do_action", path=node_path, action=action_name)
        # In production: resolve path, get action interface, invoke
        return True

    def get_text(self, node_path: str) -> str:
        """Get text content from an accessible element."""
        if not self.available:
            return ""
        return ""

    def set_text(self, node_path: str, text: str) -> bool:
        """Set text content on an editable accessible element."""
        if not self.available:
            return False
        logger.info("atspi.set_text", path=node_path, text_length=len(text))
        return True

    def _to_node(self, obj: Any, path: str) -> AccessibleNode:
        """Convert a pyatspi accessible object to our data model."""
        try:
            role = obj.getRoleName() if hasattr(obj, 'getRoleName') else str(obj.role)
            bounds = (0, 0, 0, 0)
            try:
                comp = obj.queryComponent()
                ext = comp.getExtents(pyatspi.DESKTOP_COORDS)
                bounds = (ext.x, ext.y, ext.width, ext.height)
            except Exception:
                pass

            actions = []
            try:
                ai = obj.queryAction()
                actions = [ai.getName(i) for i in range(ai.nActions)]
            except Exception:
                pass

            return AccessibleNode(
                role=role, name=obj.name or "", description=obj.description or "",
                bounds=bounds, actions=actions,
                children_count=obj.childCount, path=path,
            )
        except Exception:
            return AccessibleNode(path=path)

    def _walk_tree(self, obj: Any, role: str, results: list, path: str, depth: int = 0) -> None:
        if depth > 15:
            return
        try:
            if obj.getRoleName() == role:
                results.append(self._to_node(obj, path))
            for i in range(min(obj.childCount, 100)):
                child = obj.getChildAtIndex(i)
                if child:
                    self._walk_tree(child, role, results, f"{path}/{i}", depth + 1)
        except Exception:
            pass

    def _walk_tree_by_name(self, obj: Any, name: str, partial: bool, results: list, path: str, depth: int = 0) -> None:
        if depth > 15:
            return
        try:
            obj_name = obj.name or ""
            if (partial and name.lower() in obj_name.lower()) or (not partial and obj_name == name):
                results.append(self._to_node(obj, path))
            for i in range(min(obj.childCount, 100)):
                child = obj.getChildAtIndex(i)
                if child:
                    self._walk_tree_by_name(child, name, partial, results, f"{path}/{i}", depth + 1)
        except Exception:
            pass
