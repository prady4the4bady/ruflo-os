"""
Spotlight - macOS-style search bar for Ruflo OS.
Activated by Ctrl+Space, searches apps/files/tasks.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio
import structlog
import subprocess
import os

logger = structlog.get_logger(__name__)


class Spotlight(Gtk.Box):
    """
    GTK4 SearchEntry in floating centered box (width=600, border-radius=12).
    Search modes: Apps, Files, Tasks (prefix "do: " routes to Ruflo Agent).
    """

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_css_classes(["spotlight-overlay"])

        self._build_ui()
        self._load_css()

    def _build_ui(self):
        """Build spotlight UI components."""
        # Container
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.container.set_size_request(600, -1)
        self.container.set_css_classes(["spotlight-container"])

        # Search entry
        self.entry = Gtk.SearchEntry(placeholder_text="Search for apps, files, or ask Ruflo...")
        self.entry.set_size_request(600, 40)
        self.entry.connect("activate", self._on_activate)
        self.entry.connect("search-changed", self._on_search_changed)
        self.container.append(self.entry)

        # Results list
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.results_scroll = Gtk.ScrolledWindow()
        self.results_scroll.set_child(self.results_box)
        self.results_scroll.set_size_request(600, 300)
        self.container.append(self.results_scroll)

        self.append(self.container)

    def focus_entry(self):
        """Focus the search entry and show spotlight."""
        self.set_visible(True)
        self.entry.grab_focus()

    def _on_activate(self, entry):
        """Handle Enter key - submit task to Ruflo Agent."""
        text = entry.get_text().strip()
        if not text:
            return

        logger.info("Spotlight activated", text=text[:50])

        # Check if it's a task command
        if text.lower().startswith("do:"):
            task_text = text[3:].strip()
            self._submit_task(task_text)
        else:
            self._search_local(text)

    def _on_search_changed(self, entry):
        """Live search as user types."""
        text = entry.get_text().strip()
        if len(text) < 2:
            self._clear_results()
            return

        # Show live preview for task
        if text.lower().startswith("do:"):
            self._show_task_preview(text[3:].strip())
        else:
            self._search_local(text)

    def _submit_task(self, task_text: str):
        """POST to localhost:8080/tasks with task text."""
        try:
            import httpx
            resp = httpx.post(
                "http://localhost:8080/api/v1/tasks",
                json={"task": task_text, "mode": "auto"}
            )
            if resp.status_code == 200:
                task_id = resp.json().get("task_id")
                logger.info("Task submitted", task_id=task_id)
                self.set_visible(False)
                self.entry.set_text("")
            else:
                logger.error("Task submission failed", status=resp.status_code)
        except Exception as e:
            logger.error("Failed to submit task", error=str(e))

    def _search_local(self, query: str):
        """Search apps, files, tasks."""
        self._clear_results()

        # Search applications
        apps = self._search_apps(query)
        for app in apps[:5]:
            self._add_result(app["name"], app["icon"], "app")

        # Search files (using locate command)
        files = self._search_files(query)
        for file in files[:3]:
            self._add_result(file, "text-x-generic-symbolic", "file")

    def _search_apps(self, query: str) -> list:
        """Search /usr/share/applications for matching .desktop files."""
        results = []
        apps_dir = "/usr/share/applications"
        if os.path.exists(apps_dir):
            for file in os.listdir(apps_dir):
                if file.endswith(".desktop"):
                    # Simple name match
                    if query.lower() in file.lower():
                        results.append({
                            "name": file.replace(".desktop", ""),
                            "icon": "application-x-executable-symbolic"
                        })
        return results

    def _search_files(self, query: str) -> list:
        """Search files using locate command."""
        try:
            result = subprocess.run(
                ["locate", "-l", "3", query],
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip().split("\n") if result.returncode == 0 else []
        except Exception:
            return []

    def _show_task_preview(self, task_text: str):
        """Show live preview of what Ruflo will do."""
        self._clear_results()
        preview = Gtk.Label(label=f"Ruflo will: {task_text[:100]}")
        preview.set_halign(Gtk.Align.START)
        preview.set_margin_start(12)
        preview.set_css_classes(["preview-label"])
        self.results_box.append(preview)

    def _add_result(self, name: str, icon_name: str, result_type: str):
        """Add a result item to the list."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_start(8)
        row.set_margin_end(8)
        row.set_size_request(-1, 36)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        row.append(icon)

        label = Gtk.Label(label=name)
        label.set_halign(Gtk.Align.START)
        row.append(label)

        self.results_box.append(row)

    def _clear_results(self):
        """Clear all results."""
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)

    def _load_css(self):
        """Load CSS for spotlight styling."""
        css = """
        .spotlight-overlay {
            background: transparent;
        }
        .spotlight-container {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 12px;
            padding: 8px;
            backdrop-filter: blur(20px) saturate(180%);
        }
        .preview-label {
            color: rgba(0, 0, 0, 0.6);
            font-size: 12px;
        }
        searchentry {
            font-size: 16px;
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
            logger.error("Failed to load Spotlight CSS", error=str(e))
