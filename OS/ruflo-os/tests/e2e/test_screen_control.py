import pytest
from ruflo-agent.tools.screen_capture import ScreenCapture

def test_screen_capture():
    tool = ScreenCapture()
    result = tool.execute(action="capture_full")
    assert "success" in result

def test_cursor_control():
    from ruflo-agent.tools.cursor_control import CursorControl
    tool = CursorControl()
    result = tool.execute(action="move", x=100, y=100)
    assert "success" in result

def test_keyboard_control():
    from ruflo-agent.tools.keyboard_control import KeyboardControl
    tool = KeyboardControl()
    result = tool.execute(action="press", key="enter")
    assert "success" in result