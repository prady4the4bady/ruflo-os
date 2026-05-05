"""
NemOS Desktop Entry Point
Launches the complete NemOS desktop environment.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio
import sys
import os
import structlog

# Add paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = structlog.get_logger(__name__)


class NemOSApplication(Adw.Application):
    """Main NemOS application."""

    def __init__(self):
        super().__init__(
            application_id="org.nemos.Desktop",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        """Activate the application."""
        # Load CSS
        self._load_css()

        # Create desktop
        from ruflo_shell.ui.desktop.main import RufloDesktop
        self.desktop = RufloDesktop(app)
        self.desktop.present()

    def _load_css(self):
        """Load global CSS."""
        css = """
        window {
            background: #1a1a2e;
            color: #ffffff;
        }
        .title-1 {
            font-size: 32px;
            font-weight: bold;
        }
        .dim-label {
            opacity: 0.6;
        }
        """
        try:
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(css.encode())
            display = Gdk.Display.get_default()
            Gtk.StyleContext.add_provider_for_display(
                display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except Exception as e:
            logger.error("Failed to load CSS", error=str(e))


def main():
    """Main entry point."""
    app = NemOSApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
