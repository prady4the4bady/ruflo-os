"""
RufloDesktop - Main GTK4 Application for Ruflo OS Shell
Fullscreen transparent overlay with macOS-like layout.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio
import structlog
import time
import websockets
import asyncio
import json
from pathlib import Path

logger = structlog.get_logger(__name__)


class RufloDesktop(Adw.Application):
    """
    Main Ruflo OS desktop application.
    Fullscreen transparent overlay window with macOS-like layout.
    """

    def __init__(self):
        super().__init__(
            application_id="org.ruflo.Desktop",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None
        self.agent_status = "idle"  # idle, busy, error
        self.websocket = None
        self.event_loop = None

    def do_activate(self):
        """Activate the application and show the main window."""
        if not self.window:
            self.window = RufloWindow(application=self)
        self.window.present()
        self._connect_agent_websocket()
        logger.info("Ruflo Desktop activated")

    def _connect_agent_websocket(self):
        """Connect to Ruflo Agent via WebSocket."""
        asyncio.ensure_future(self._ws_connect())

    async def _ws_connect(self):
        try:
            self.websocket = await websockets.connect("ws://localhost:8080/ws/tasks")
            logger.info("Connected to Ruflo Agent WebSocket")
            # Start listening for messages
            asyncio.ensure_future(self._ws_listen())
        except Exception as e:
            logger.error("WebSocket connection failed", error=str(e))
            # Retry after 5 seconds
            await asyncio.sleep(5)
            asyncio.ensure_future(self._ws_connect())

    async def _ws_listen(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                GLib.idle_add(self._handle_ws_message, data)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket disconnected, reconnecting...")
            await asyncio.sleep(2)
            asyncio.ensure_future(self._ws_connect())
        except Exception as e:
            logger.error("WebSocket listen error", error=str(e))

    def _handle_ws_message(self, data: dict):
        """Handle incoming WebSocket messages from agent."""
        event = data.get("event")
        if event == "step":
            self.agent_status = "busy"
        elif event == "complete":
            self.agent_status = "idle"
        elif event == "error":
            self.agent_status = "error"
        # Update UI
        if self.window:
            self.window.update_agent_status(self.agent_status)


class RufloWindow(Gtk.ApplicationWindow):
    """Main Ruflo desktop window - fullscreen transparent overlay."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Ruflo OS Desktop")
        self.set_decorated(False)
        self.set_fullscreened(True)
        self.set_default_size(1920, 1080)

        # Set transparent background
        self.set_css_classes(["transparent-window"])

        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_box)

        # Top: MenuBar (24px)
        self.menu_bar = MenuBar()
        self.main_box.append(self.menu_bar)

        # Middle: Expanding spacer
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        self.main_box.append(spacer)

        # Bottom: Dock
        self.dock = Dock()
        self.main_box.append(self.dock)

        # Floating Spotlight (hidden by default)
        self.spotlight = Spotlight()
        self.spotlight.set_visible(False)
        # Overlay for spotlight
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.main_box)
        self.overlay.add_overlay(self.spotlight)
        self.set_child(self.overlay)

        # Agent status indicator (top-right)
        self.status_indicator = Gtk.DrawingArea()
        self.status_indicator.set_size_request(12, 12)
        self.status_indicator.set_draw_func(self._draw_status)
        self.overlay.add_overlay(self.status_indicator)

        # Apply CSS
        self._load_css()

        # Keyboard shortcut for Spotlight (Ctrl+Space)
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

        logger.info("Ruflo Window created")

    def _draw_status(self, area, cr, width, height):
        """Draw agent status dot."""
        import cairo
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.0)
        cr.paint()

        # Status color
        if self.get_parent().agent_status == "busy":
            cr.set_source_rgb(1.0, 0.65, 0.0)  # Orange
        elif self.get_parent().agent_status == "error":
            cr.set_source_rgb(1.0, 0.27, 0.23)  # Red
        else:
            cr.set_source_rgb(0.18, 0.78, 0.22)  # Green

        cr.arc(width/2, height/2, min(width, height)/2 - 1, 0, 2 * 3.14159)
        cr.fill()

    def update_agent_status(self, status: str):
        self.get_parent().agent_status = status
        self.status_indicator.queue_draw()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handle keyboard shortcuts."""
        # Ctrl+Space for Spotlight
        if keyval == Gdk.KEY_space and state & Gdk.ModifierType.CONTROL_MASK:
            self.spotlight.set_visible(not self.spotlight.get_visible())
            if self.spotlight.get_visible():
                self.spotlight.focus_entry()
            return True
        return False

    def _load_css(self):
        """Load CSS for the desktop."""
        css_provider = Gtk.CssProvider()
        css_path = Path(__file__).parent.parent / "themes" / "ruflo-tokens.css"
        if css_path.exists():
            css_provider.load_from_path(str(css_path))
            display = Gdk.Display.get_default()
            Gtk.StyleContext.add_provider_for_display(
                display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        logger.info("CSS loaded")


if __name__ == "__main__":
    app = RufloDesktop()
    app.run()
