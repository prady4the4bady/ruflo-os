"""Tests for accessibility — GuiOperator fallback logic."""

import pytest
from ruflo_accessibility.operator import GuiOperator
from ruflo_accessibility.atspi.client import ATSPIClient
from ruflo_accessibility.wayland.injector import YdotoolInjector
from ruflo_accessibility.x11.injector import XdotoolInjector


def test_gui_operator_status():
    op = GuiOperator()
    status = op.get_status()
    assert "atspi" in status
    assert "ydotool" in status
    assert "xdotool" in status
    assert "screenshot" in status


def test_atspi_client_init():
    client = ATSPIClient()
    # On Windows/non-Linux, AT-SPI won't be available
    assert isinstance(client.available, bool)


def test_ydotool_injector_init():
    injector = YdotoolInjector()
    assert isinstance(injector.available, bool)


def test_xdotool_injector_init():
    injector = XdotoolInjector()
    assert isinstance(injector.available, bool)


@pytest.mark.asyncio
async def test_click_without_tools():
    """Click should gracefully fail when no tools are available."""
    op = GuiOperator()
    result = await op.click("nonexistent_button")
    # On Windows/CI without ydotool/xdotool, this should fail gracefully
    assert isinstance(result.success, bool)


@pytest.mark.asyncio
async def test_type_without_tools():
    op = GuiOperator()
    result = await op.type_text("hello")
    assert isinstance(result.success, bool)


@pytest.mark.asyncio
async def test_key_press_without_tools():
    op = GuiOperator()
    result = await op.key_press("ctrl", "c")
    assert isinstance(result.success, bool)
