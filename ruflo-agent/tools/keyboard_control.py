import time
from typing import List, Optional
import structlog
from .base_tool import BaseTool

logger = structlog.get_logger(__name__)

class KeyboardControl(BaseTool):
    """Keyboard input injection with humanlike typing speed."""

    name = "keyboard_control"
    description = "Type text, press keys, hotkeys"

    async def execute(self, action: str, **kwargs) -> dict:
        if action == "type":
            return await self.type_text(kwargs["text"], kwargs.get("wpm", 80))
        elif action == "press":
            return await self.press_key(kwargs["key"])
        elif action == "hotkey":
            return await self.press_hotkey(*kwargs["keys"])
        elif action == "hold":
            return await self.hold_key(kwargs["key"])
        elif action == "release":
            return await self.release_key(kwargs["key"])
        else:
            return {"success": False, "error": f"Unknown action {action}"}

    async def type_text(self, text: str, wpm: int = 80) -> dict:
        """Type text at humanlike speed (words per minute)."""
        try:
            # Calculate delay per character
            chars_per_min = wpm * 5  # Avg 5 chars per word
            delay = 60.0 / chars_per_min
            import subprocess
            for char in text:
                subprocess.run(["ydotool", "type", char], check=True)
                time.sleep(delay)
            logger.info("Text typed", length=len(text), wpm=wpm)
            return {"success": True, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_key(self, key: str) -> dict:
        """Press a single key (e.g., 'enter', 'ctrl+c')."""
        try:
            import subprocess
            key_map = {
                "enter": "KEY_ENTER",
                "tab": "KEY_TAB",
                "space": "KEY_SPACE",
                "esc": "KEY_ESC",
                "backspace": "KEY_BACKSPACE",
                "ctrl+c": "ctrl+c",
                "ctrl+v": "ctrl+v",
            }
            mapped = key_map.get(key, key)
            subprocess.run(["ydotool", "key", mapped], check=True)
            logger.info("Key pressed", key=key)
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_hotkey(self, *keys: str) -> dict:
        """Press combination of keys (e.g., 'ctrl', 'shift', 't')."""
        try:
            import subprocess
            key_str = "+".join(keys)
            subprocess.run(["ydotool", "key", key_str], check=True)
            logger.info("Hotkey pressed", keys=keys)
            return {"success": True, "keys": keys}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def hold_key(self, key: str) -> dict:
        try:
            import subprocess
            subprocess.run(["ydotool", "keydown", key], check=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def release_key(self, key: str) -> dict:
        try:
            import subprocess
            subprocess.run(["ydotool", "keyup", key], check=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}