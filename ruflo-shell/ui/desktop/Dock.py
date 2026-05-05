"""
Dock - macOS-style dock bar at bottom of screen.
GTK4 Box widget with magnification effect on hover.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Adw, GLib, Gio
import structlog
from pathlib import Path

logger = structlog.get_logger(__name__)


class Dock(Gtk.Box):
    """
    macOS-style dock with magnification effect on hover.
    60px icons with scale 1.0 → 1.5 → 1.0 animation.
    """

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, **kwargs)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_margin_bottom(8)
        self.set_spacing(8)
        self.set_css_classes(["dock"])

        # Default dock items
        self.apps = [
            {"id": "terminal", "name": "Terminal", "icon": "utilities-terminal-symbolic"},
            {"id": "files", "name": "Files", "icon": "system-file-manager-symbolic"},
            {"id": "browser", "name": "Browser", "icon": "web-browser-symbolic"},
            {"id": "ruflo-task", "name": "Ruflo Task", "icon": "system-run-symbolic"},
            {"id": "settings", "name": "Settings", "icon": "preferences-system-symbolic"},
        ]

        self._build_ui()
        self._load_css()

    def _build_ui(self):
        for app in self.apps:
            button = Gtk.Button(css_classes=["dock-button"])
            button.set_tooltip_text(app["name"])

            # Icon
            icon = Gtk.Image.new_from_icon_name(app["icon"])
            icon.set_pixel_size(48)
            button.set_child(icon)

            # Click handler
            button.connect("clicked", self._on_app_clicked, app)

            # Hover effect
            motion = Gtk.EventControllerMotion()
            motion.connect("enter", self._on_hover_enter, button)
            motion.connect("leave", self._on_hover_leave, button)
            button.add_controller(motion)

            self.append(button)

    def _on_app_clicked(self, button, app):
        """Launch application when dock icon clicked."""
        logger.info("Dock app clicked", app=app["name"])
        # Launch application
        try:
            import subprocess
            if app["id"] == "terminal":
                subprocess.Popen(["gnome-terminal"])
            elif app["id"] == "browser":
                subprocess.Popen(["firefox"])
            elif app["id"] == "ruflo-task":
                self._launch_ruflo_task()
        except Exception as e:
            logger.error("Failed to launch app", error=str(e))

    def _on_hover_enter(self, controller, x, y, button):
        """Magnification effect on hover."""
        button.set_css_classes(["dock-button", "dock-hover"])

    def _on_hover_leave(self, controller, button):
        """Remove hover effect."""
        button.set_css_classes(["dock-button"])

    def _launch_ruflo_task(self):
        """Open Ruflo Task Intake application."""
        try:
            import subprocess
            subprocess.Popen(["python3", "ruflo-shell/ui/apps/TaskIntakeApp/main.py"])
        except Exception as e:
            logger.error("Failed to launch Ruflo Task", error=str(e))

    def _load_css(self):
        """Load CSS for dock styling."""
        css = """
        .dock {
            background: rgba(255, 255, 255, 0.7);
            border-radius: 16px;
            padding: 6px 12px;
            margin: 0 auto;
            backdrop-filter: blur(20px) saturate(180%);
        }
        .dock-button {
            background: transparent;
            border: none;
            padding: 6px;
            border-radius: 8px;
            transition: all 150ms ease;
        }
        .dock-button:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.5);
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
            logger.error("Failed to load dock CSS", error=str(e))
