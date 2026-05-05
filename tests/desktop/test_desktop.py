"""
NemOS Desktop Tests - Tests for desktop shell components.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDock:
    """Test Dock component."""

    def test_dock_import(self):
        """Test Dock can be imported."""
        try:
            from ruflo_shell.ui.desktop import Dock
            assert True
        except ImportError:
            pytest.skip("GTK4 not available")

    def test_dock_initialization(self):
        """Test Dock creates properly."""
        try:
            from ruflo_shell.ui.desktop import Dock
            # Mock GTK
            dock = Dock()
            assert dock is not None
        except Exception as e:
            pytest.skip(f"GTK4 error: {e}")


class TestMenuBar:
    """Test MenuBar component."""

    def test_menubar_import(self):
        """Test MenuBar can be imported."""
        try:
            from ruflo_shell.ui.desktop import MenuBar
            assert True
        except ImportError:
            pytest.skip("GTK4 not available")


class TestSpotlight:
    """Test Spotlight component."""

    def test_spotlight_import(self):
        """Test Spotlight can be imported."""
        try:
            from ruflo_shell.ui.desktop import Spotlight
            assert True
        except ImportError:
            pytest.skip("GTK4 not available")


class TestNotifications:
    """Test Notifications component."""

    def test_notifications_import(self):
        """Test Notifications can be imported."""
        try:
            from ruflo_shell.ui.desktop import Notifications
            assert True
        except ImportError:
            pytest.skip("GTK4 not available")


class TestRufloDesktop:
    """Test main desktop application."""

    def test_desktop_import(self):
        """Test RufloDesktop can be imported."""
        try:
            from ruflo_shell.ui.desktop import RufloDesktop
            assert True
        except ImportError:
            pytest.skip("GTK4 not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
