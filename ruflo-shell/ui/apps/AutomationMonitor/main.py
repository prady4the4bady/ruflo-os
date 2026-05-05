"""
NemOS Automation Monitor - Shows running tasks, progress, and logs.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio
import structlog

logger = structlog.get_logger(__name__)


class AutomationMonitor(Adw.ApplicationWindow):
    """Monitor running automations and their progress."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Automation Monitor")
        self.set_default_size(800, 600)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="Automation Monitor")
        main_box.append(header)

        # Running tasks list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.task_list = Gtk.ListBox()
        scroll.set_child(self.task_list)
        main_box.append(scroll)

        # Refresh button
        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self._refresh)
        main_box.append(refresh_btn)

        self._load_tasks()
        self._load_css()

    def _load_tasks(self):
        """Load running tasks."""
        try:
            import httpx
            resp = httpx.get("http://localhost:8080/api/v1/tasks?status=running")
            if resp.status_code == 200:
                tasks = resp.json()
                self._populate_list(tasks)
        except Exception as e:
            logger.error("Failed to load tasks", error=str(e))

    def _populate_list(self, tasks):
        """Populate task list."""
        while child := self.task_list.get_first_child():
            self.task_list.remove(child)

        for task in tasks:
            row = Adw.ActionRow()
            row.set_title(task.get("task_id", "Unknown"))
            row.set_subtitle(task.get("task", "")[:50])
            self.task_list.append(row)

    def _refresh(self, button):
        """Refresh task list."""
        self._load_tasks()

    def _load_css(self):
        """Load CSS."""
        css = """
        window {
            background: #1a1a2e;
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


if __name__ == "__main__":
    app = Adw.Application(application_id="org.nemos.AutomationMonitor")
    app.connect("activate", lambda app: AutomationMonitor(app).present())
    app.run()
