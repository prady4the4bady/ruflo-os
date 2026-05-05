"""
AgentMonitor - Real-time agent activity viewer.
Live screenshot preview, step log, and agent controls.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio
import structlog
import httpx
import base64
from pathlib import Path
import io
from PIL import ImageGrab

logger = structlog.get_logger(__name__)


class AgentMonitorApp(Adw.Application):
    """Main application for Agent Monitor."""

    def __init__(self):
        super().__init__(
            application_id="org.ruflo.AgentMonitor",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None
        self.api_base = "http://localhost:8080"
        self.websocket = None

    def do_activate(self):
        if not self.window:
            self.window = AgentMonitorWindow(application=self)
        self.window.present()


class AgentMonitorWindow(Gtk.ApplicationWindow):
    """Main window showing real-time agent activity."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Ruflo Agent Monitor")
        self.set_default_size(1400, 900)
        self.set_css_classes(["agent-monitor-window"])

        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_box)

        # Top: Screenshot preview (left) + Step log (right)
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(8)
        content_box.set_margin_start(8)
        content_box.set_margin_end(8)
        content_box.set_vexpand(True)

        # Left: Live screenshot
        self._build_screenshot_panel(content_box)

        # Right: Step log
        self._build_step_log_panel(content_box)

        self.main_box.append(content_box)

        # Bottom: Control buttons
        self._build_controls()

        # Load CSS
        self._load_css()

        # Start updates
        GLib.timeout_add(2000, self._update_screenshot)
        GLib.timeout_add(1000, self._update_agent_status)
        GLib.timeout_add(500, self._update_step_log)

    def _build_screenshot_panel(self, parent):
        """Build screenshot preview panel."""
        left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        label = Gtk.Label(label="Live Screen Preview")
        label.set_css_classes(["panel-title"])
        left_panel.append(label)

        # Screenshot image
        self.screenshot_img = Gtk.Image()
        self.screenshot_img.set_size_request(640, 360)
        self.screenshot_img.set_css_classes(["screenshot-preview"])

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.screenshot_img)
        scroll.set_vexpand(True)
        left_panel.append(scroll)

        parent.append(left_panel)

    def _build_step_log_panel(self, parent):
        """Build step log panel."""
        right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        label = Gtk.Label(label="Step Log")
        label.set_css_classes(["panel-title"])
        right_panel.append(label)

        # Current tool display
        self.current_tool_label = Gtk.Label(label="Idle")
        self.current_tool_label.set_css_classes(["current-tool"])
        self.current_tool_label.set_halign(Gtk.Align.START)
        right_panel.append(self.current_tool_label)

        # Step log (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.step_log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self.step_log_box)

        right_panel.append(scroll)

        # Memory/CPU usage
        self.usage_label = Gtk.Label(label="Memory: N/A | CPU: N/A")
        self.usage_label.set_css_classes(["usage-label"])
        right_panel.append(self.usage_label)

        parent.append(right_panel)

    def _build_controls(self):
        """Build Pause/Resume/Cancel buttons."""
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(8)
        btn_box.set_margin_bottom(8)

        self.pause_btn = Gtk.Button(label="Pause")
        self.pause_btn.connect("clicked", self._on_pause_clicked)
        btn_box.append(self.pause_btn)

        self.resume_btn = Gtk.Button(label="Resume")
        self.resume_btn.connect("clicked", self._on_resume_clicked)
        self.resume_btn.set_sensitive(False)
        btn_box.append(self.resume_btn)

        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.connect("clicked", self._on_cancel_clicked)
        self.cancel_btn.set_css_classes(["destructive-action"])
        btn_box.append(self.cancel_btn)

        self.main_box.append(btn_box)

    def _update_screenshot(self):
        """Update screenshot preview."""
        try:
            resp = httpx.get(f"{self.api_base}/api/v1/screen/screenshot")
            if resp.status_code == 200:
                img_data = resp.json().get("image_base64", "")
                if img_data:
                    img_bytes = base64.b64decode(img_data)
                    loader = Gdk.Texture.new_from_bytes(GLib.Bytes.new(img_bytes))
                    self.screenshot_img.set_from_paintable(loader)
        except Exception as e:
            logger.error("Screenshot update failed", error=str(e))
        return True

    def _update_agent_status(self):
        """Update agent status and usage."""
        try:
            resp = httpx.get(f"{self.api_base}/api/v1/agent/status")
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "unknown")
                self.current_tool_label.set_text(f"Agent Status: {status}")

                # Update usage
                mem = data.get("memory_usage", "N/A")
                self.usage_label.set_text(f"Memory: {mem}")
        except Exception as e:
            logger.error("Status update failed", error=str(e))
        return True

    def _update_step_log(self):
        """Update step log."""
        # TODO: Connect to WebSocket for real-time step updates
        return True

    def _on_pause_clicked(self, button):
        try:
            resp = httpx.post(f"{self.api_base}/api/v1/agent/pause")
            if resp.status_code == 200:
                self.pause_btn.set_sensitive(False)
                self.resume_btn.set_sensitive(True)
                logger.info("Agent paused")
        except Exception as e:
            logger.error("Pause failed", error=str(e))

    def _on_resume_clicked(self, button):
        try:
            resp = httpx.post(f"{self.api_base}/api/v1/agent/resume")
            if resp.status_code == 200:
                self.pause_btn.set_sensitive(True)
                self.resume_btn.set_sensitive(False)
                logger.info("Agent resumed")
        except Exception as e:
            logger.error("Resume failed", error=str(e))

    def _on_cancel_clicked(self, button):
        # TODO: Get current task_id and cancel
        logger.info("Cancel clicked")

    def _load_css(self):
        css = """
        .agent-monitor-window {
            background: #1c1c1e;
        }
        .panel-title {
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .screenshot-preview {
            border-radius: 8px;
        }
        .current-tool {
            color: #0a84ff;
            font-size: 14px;
            margin: 8px;
        }
        .usage-label {
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
            logger.error("Failed to load AgentMonitor CSS", error=str(e))


if __name__ == "__main__":
    app = AgentMonitorApp()
    app.run()
