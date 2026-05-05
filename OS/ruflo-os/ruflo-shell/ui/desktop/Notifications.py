"""
Notifications - GTK4 notification popup system.
Top-right corner, slide-in animation, auto-dismiss after 5s.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import structlog
import time

logger = structlog.get_logger(__name__)


class NotificationPopup(Gtk.Box):
    """Single notification popup with slide-in animation."""

    def __init__(self, title: str, message: str, icon_name: str = "dialog-information-symbolic"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_size_request(300, -1)
        self.set_css_classes(["notification-popup"])
        self.set_margin_top(8)
        self.set_margin_end(8)

        # Main content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(8)

        # Icon
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(24)
        content_box.append(icon)

        # Text box
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        title_label = Gtk.Label(label=title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_css_classes(["notification-title"])
        text_box.append(title_label)

        msg_label = Gtk.Label(label=message)
        msg_label.set_halign(Gtk.Align.START)
        msg_label.set_wrap(True)
        msg_label.set_css_classes(["notification-message"])
        text_box.append(msg_label)

        content_box.append(text_box)
        self.append(content_box)

        # Auto-dismiss after 5 seconds
        GLib.timeout_add(5000, self._dismiss)

        # Click to expand
        gesture = Gtk.GestureClick()
        gesture.connect("pressed", self._on_click)
        self.add_controller(gesture)

    def _dismiss(self):
        """Dismiss notification with slide-out animation."""
        self.set_css_classes(["notification-popup", "dismiss"])
        GLib.timeout_add(300, lambda: self.get_parent() and self.get_parent().remove(self))
        return False

    def _on_click(self, gesture, n_press, x, y):
        """Handle click to show full details."""
        logger.info("Notification clicked")
        # TODO: Show modal with full task details


class Notifications(Gtk.Box):
    """
    GTK4 notification system (top-right corner).
    Receives notifications from Ruflo Agent via WebSocket.
    """

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.START)
        self.set_css_classes(["notifications-container"])
        self.set_margin_top(32)  # Below MenuBar
        self.set_margin_end(8)
        self.notifications = []

        self._load_css()

    def add_notification(self, title: str, message: str, icon_name: str = "dialog-information-symbolic"):
        """Add a new notification."""
        popup = NotificationPopup(title, message, icon_name)
        self.append(popup)
        self.notifications.append(popup)
        logger.info("Notification added", title=title)

        # Limit to 5 visible notifications
        while len(self.notifications) > 5:
            old = self.notifications.pop(0)
            if old.get_parent():
                self.remove(old)

    def clear_all(self):
        """Clear all notifications."""
        while child := self.get_first_child():
            self.remove(child)
        self.notifications.clear()

    def _load_css(self):
        """Load CSS for notifications."""
        css = """
        .notifications-container {
            background: transparent;
        }
        .notification-popup {
            background: rgba(44, 44, 46, 0.9);
            border-radius: 12px;
            backdrop-filter: blur(20px) saturate(180%);
            animation: slide-in 300ms ease;
            transition: all 300ms ease;
        }
        @keyframes slide-in {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        .notification-popup.dismiss {
            transform: translateX(100%);
            opacity: 0;
        }
        .notification-title {
            color: #ffffff;
            font-weight: bold;
            font-size: 13px;
        }
        .notification-message {
            color: rgba(255, 255, 255, 0.6);
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
            logger.error("Failed to load notifications CSS", error=str(e))
