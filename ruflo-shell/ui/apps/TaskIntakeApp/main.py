"""
TaskIntakeApp - Main task intake UI for Ruflo OS.
Large centered text input with voice input and live agent monitor.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio
import structlog
import httpx
import base64
import time
from pathlib import Path

logger = structlog.get_logger(__name__)


class TaskIntakeApp(Adw.Application):
    """Main application for task intake."""

    def __init__(self):
        super().__init__(
            application_id="org.ruflo.TaskIntake",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None
        self.api_base = "http://localhost:8080"

    def do_activate(self):
        if not self.window:
            self.window = TaskIntakeWindow(application=self)
        self.window.present()


class TaskIntakeWindow(Gtk.ApplicationWindow):
    """Main window for task intake."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Ruflo Task Intake")
        self.set_default_size(1200, 800)
        self.set_css_classes(["task-intake-window"])

        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_box)

        # Left: History panel (past 10 tasks)
        self._build_history_panel()

        # Center: Main task input
        self._build_main_input()

        # Right: Live agent monitor
        self._build_agent_monitor()

        self._load_css()

    def _build_history_panel(self):
        """Left sidebar with past 10 tasks."""
        left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_panel.set_size_request(250, -1)
        left_panel.set_margin_start(16)
        left_panel.set_margin_top(16)

        label = Gtk.Label(label="Recent Tasks")
        label.set_css_classes(["panel-title"])
        left_panel.append(label)

        # Scrollable task list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.task_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self.task_list)

        left_panel.append(scroll)
        self.main_box.append(left_panel)

        # Load history
        self._load_history()

    def _build_main_input(self):
        """Center: Large centered text input."""
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        center_box.set_vexpand(True)
        center_box.set_margin_top(100)

        # Prompt label
        prompt = Gtk.Label(label="What would you like me to do?")
        prompt.set_css_classes(["prompt-label"])
        center_box.append(prompt)

        # Large text input
        self.task_entry = Gtk.TextView()
        self.task_entry.set_size_request(600, 100)
        self.task_entry.set_wrap_mode(Gtk.WrapMode.WORD)
        self.task_entry.set_css_classes(["task-entry"])

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.task_entry)
        center_box.append(scroll)

        # Buttons row
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)

        # Voice input button
        voice_btn = Gtk.Button(label="🎤 Voice")
        voice_btn.connect("clicked", self._on_voice_clicked)
        btn_box.append(voice_btn)

        # Submit button
        submit_btn = Gtk.Button(label="Submit Task")
        submit_btn.set_css_classes(["suggested-action"])
        submit_btn.connect("clicked", self._on_submit_clicked)
        btn_box.append(submit_btn)

        center_box.append(btn_box)
        self.main_box.append(center_box)

    def _build_agent_monitor(self):
        """Right sidebar: Live agent monitor."""
        right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_panel.set_size_request(300, -1)
        right_panel.set_margin_end(16)
        right_panel.set_margin_top(16)

        label = Gtk.Label(label="Agent Monitor")
        label.set_css_classes(["panel-title"])
        right_panel.append(label)

        # Current tool display
        self.current_tool_label = Gtk.Label(label="Idle")
        self.current_tool_label.set_css_classes(["tool-label"])
        right_panel.append(self.current_tool_label)

        # Step log (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.step_log = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self.step_log)

        right_panel.append(scroll)

        # Screenshot thumbnail
        self.screenshot_img = Gtk.Image()
        self.screenshot_img.set_size_request(280, 180)
        self.screenshot_img.set_css_classes(["screenshot-thumb"])
        right_panel.append(self.screenshot_img)

        self.main_box.append(right_panel)

        # Start monitor update
        GLib.timeout_add(2000, self._update_monitor)

    def _on_submit_clicked(self, button):
        """Submit task to API."""
        buffer = self.task_entry.get_buffer()
        task_text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

        if not task_text.strip():
            return

        try:
            resp = httpx.post(
                f"{self.api_base}/api/v1/tasks",
                json={"task": task_text, "mode": "auto"}
            )
            if resp.status_code == 200:
                task_id = resp.json().get("task_id")
                logger.info("Task submitted", task_id=task_id)

                # Clear entry
                buffer.set_text("", -1)

                # Add to history
                self._add_history_item(task_text, task_id)
            else:
                logger.error("Task submission failed", status=resp.status_code)
        except Exception as e:
            logger.error("Failed to submit task", error=str(e))

    def _on_voice_clicked(self, button):
        """Start voice input (placeholder for SpeechRecognition)."""
        logger.info("Voice input triggered")
        # TODO: Implement speech recognition
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as source:
                audio = r.listen(source, timeout=5)
            text = r.recognize_google(audio)
            buffer = self.task_entry.get_buffer()
            buffer.set_text(text, -1)
        except ImportError:
            logger.warning("speech_recognition not installed")
        except Exception as e:
            logger.error("Voice input failed", error=str(e))

    def _load_history(self):
        """Load past 10 tasks from API."""
        try:
            resp = httpx.get(f"{self.api_base}/api/v1/tasks/history")
            if resp.status_code == 200:
                tasks = resp.json().get("items", [])[:10]
                for task in tasks:
                    self._add_history_item(task.get("task", ""), task.get("task_id", ""))
        except Exception as e:
            logger.error("Failed to load history", error=str(e))

    def _add_history_item(self, task_text: str, task_id: str):
        """Add item to history list."""
        item = Gtk.Label(label=task_text[:50] + "..." if len(task_text) > 50 else task_text)
        item.set_halign(Gtk.Align.START)
        item.set_wrap(True)
        item.set_css_classes(["history-item"])
        self.task_list.append(item)

    def _update_monitor(self):
        """Update agent monitor with live data."""
        try:
            resp = httpx.get(f"{self.api_base}/api/v1/agent/status")
            if resp.status_code == 200:
                data = resp.json()
                self.current_tool_label.set_text(f"Status: {data.get('status', 'unknown')}")

                # Update screenshot
                img_resp = httpx.get(f"{self.api_base}/api/v1/screen/screenshot")
                if img_resp.status_code == 200:
                    img_data = img_resp.json().get("image_base64", "")
                    if img_data:
                        import base64
                        from PIL import Image
                        import io
                        img_bytes = base64.b64decode(img_data)
                        loader = Gdk.Texture.new_from_bytes(GLib.Bytes.new(img_bytes))
                        self.screenshot_img.set_from_paintable(loader)
        except Exception as e:
            logger.error("Monitor update failed", error=str(e))
        return True  # Continue timer

    def _load_css(self):
        """Load CSS for TaskIntakeApp."""
        css = """
        .task-intake-window {
            background: #1c1c1e;
        }
        .prompt-label {
            color: #ffffff;
            font-size: 24px;
            font-weight: bold;
        }
        .task-entry {
            font-size: 16px;
            background: #2c2c2e;
            color: #ffffff;
            border-radius: 8px;
            padding: 12px;
        }
        .panel-title {
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
        }
        .history-item {
            color: rgba(255, 255, 255, 0.6);
            font-size: 12px;
            padding: 4px;
        }
        .tool-label {
            color: #0a84ff;
            font-size: 14px;
        }
        .screenshot-thumb {
            border-radius: 8px;
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
            logger.error("Failed to load TaskIntake CSS", error=str(e))


if __name__ == "__main__":
    app = TaskIntakeApp()
    app.run()
