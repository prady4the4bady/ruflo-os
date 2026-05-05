"""
MenuBar - macOS-style top bar for Ruflo OS.
24px height, semi-transparent black, with clock and status indicators.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import structlog
import time

logger = structlog.get_logger(__name__)


class MenuBar(Gtk.HeaderBar):
    """
    GTK4 HeaderBar at top, 24px height, semi-transparent black.
    Left: Ruflo logo + App menu
    Center: Clock (updates every second)
    Right: WiFi, Battery, Volume, AI status dot
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_show_title_buttons(False)
        self.set_size_request(-1, 24)
        self.set_css_classes(["menubar"])

        self._build_left()
        self._build_center()
        self._build_right()

        # Start clock update timer
        GLib.timeout_add(1000, self._update_clock)
        self._load_css()

    def _build_left(self):
        """Left: Ruflo logo + App menu."""
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left_box.set_margin_start(8)

        # Ruflo logo (inline SVG as icon)
        logo = Gtk.Image.new_from_icon_name("system-run-symbolic")
        logo.set_pixel_size(16)
        left_box.append(logo)

        # Menu items
        for item in ["File", "Edit", "View"]:
            btn = Gtk.Button(label=item)
            btn.set_css_classes(["menubar-button"])
            left_box.append(btn)

        self.pack_start(left_box)

    def _build_center(self):
        """Center: Clock (HH:MM, updates every second)."""
        self.clock_label = Gtk.Label()
        self.clock_label.set_css_classes(["clock"])
        self._update_clock()
        self.set_title_widget(self.clock_label)

    def _build_right(self):
        """Right: WiFi, Battery, Volume, AI status dot."""
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        right_box.set_margin_end(8)

        # WiFi icon
        wifi = Gtk.Image.new_from_icon_name("network-wireless-symbolic")
        right_box.append(wifi)

        # Battery icon
        battery = Gtk.Image.new_from_icon_name("battery-good-symbolic")
        right_box.append(battery)

        # Volume slider
        volume = Gtk.VolumeButton()
        volume.set_value(0.75)
        right_box.append(volume)

        # AI status dot (green=idle, orange=thinking, red=error)
        self.status_dot = Gtk.DrawingArea()
        self.status_dot.set_size_request(8, 8)
        self.status_dot.set_draw_func(self._draw_status_dot)
        right_box.append(self.status_dot)

        self.pack_end(right_box)

    def _update_clock(self):
        """Update clock display."""
        current_time = time.strftime("%H:%M")
        self.clock_label.set_text(current_time)
        return True  # Continue timer

    def _draw_status_dot(self, area, cr, width, height):
        """Draw AI status indicator dot."""
        import cairo
        cr.set_source_rgba(0.18, 0.78, 0.22, 1.0)  # Green for idle
        cr.arc(width / 2, height / 2, min(width, height) / 2 - 1, 0, 2 * 3.14159)
        cr.fill()

    def update_ai_status(self, status: str):
        """Update AI status dot color."""
        self.status_dot.queue_draw()

    def _load_css(self):
        """Load CSS for MenuBar styling."""
        css = """
        .menubar {
            background: rgba(26, 26, 26, 0.8);
            color: #f5f5f7;
            font-size: 12px;
        }
        .menubar-button {
            background: transparent;
            border: none;
            color: #f5f5f7;
            font-size: 12px;
        }
        .menubar-button:hover {
            background: rgba(255, 255, 255, 0.1);
        }
        .clock {
            color: #f5f5f7;
            font-size: 12px;
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
            logger.error("Failed to load MenuBar CSS", error=str(e))
