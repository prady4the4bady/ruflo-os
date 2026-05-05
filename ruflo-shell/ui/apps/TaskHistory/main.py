"""
NemOS Task History - View past tasks and their outcomes.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio
import structlog
from typing import List, Dict, Optional
import json

logger = structlog.get_logger(__name__)


class TaskHistoryView(Adw.ApplicationWindow):
    """
    Task History application for NemOS.
    Shows past tasks, their status, and allows re-running.
    """

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Task History")
        self.set_default_size(900, 600)

        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(self.main_box)

        # Header
        header = Adw.HeaderBar(title="Task History")
        self.main_box.append(header)

        # Filter bar
        self._build_filter_bar()

        # Task list (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.task_list = Gtk.ListBox()
        self.task_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.task_list.connect("row-activated", self._on_task_selected)
        scroll.set_child(self.task_list)

        self.main_box.append(scroll)

        # Details panel
        self._build_details_panel()

        # Load tasks
        self._load_tasks()

        self._load_css()

    def _build_filter_bar(self):
        """Build filter controls."""
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.set_margin_start(8)
        filter_box.set_margin_end(8)
        filter_box.set_margin_top(8)
        filter_box.set_margin_bottom(8)

        # Status filter
        status_label = Gtk.Label(label="Status:")
        filter_box.append(status_label)

        self.status_combo = Gtk.ComboBoxText()
        self.status_combo.append("all", "All")
        self.status_combo.append("completed", "Completed")
        self.status_combo.append("failed", "Failed")
        self.status_combo.append("cancelled", "Cancelled")
        self.status_combo.set_active(0)
        self.status_combo.connect("changed", self._on_filter_changed)
        filter_box.append(self.status_combo)

        # Search entry
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Search tasks...")
        search_entry.connect("search-changed", self._on_search_changed)
        filter_box.append(search_entry)

        self.main_box.append(filter_box)

    def _build_details_panel(self):
        """Build task details panel."""
        self.details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.details_box.set_margin_start(8)
        self.details_box.set_margin_end(8)
        self.details_box.set_margin_bottom(8)

        # Task ID
        self.task_id_label = Gtk.Label()
        self.task_id_label.set_halign(Gtk.Align.START)
        self.task_id_label.set_css_classes(["details-label"])
        self.details_box.append(self.task_id_label)

        # Status
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.START)
        self.details_box.append(self.status_label)

        # Task description
        self.task_label = Gtk.Label()
        self.task_label.set_halign(Gtk.Align.START)
        self.task_label.set_wrap(True)
        self.details_box.append(self.task_label)

        # Re-run button
        rerun_btn = Gtk.Button(label="Re-run Task")
        rerun_btn.connect("clicked", self._on_rerun_clicked)
        self.details_box.append(rerun_btn)

        self.main_box.append(self.details_box)

    def _load_tasks(self):
        """Load tasks from API."""
        try:
            import httpx
            resp = httpx.get("http://localhost:8080/api/v1/history")
            if resp.status_code == 200:
                tasks = resp.json()
                self._populate_list(tasks)
        except Exception as e:
            logger.error("Failed to load tasks", error=str(e))

    def _populate_list(self, tasks: List[Dict]):
        """Populate task list."""
        # Clear existing
        while child := self.task_list.get_first_child():
            self.task_list.remove(child)

        for task in tasks:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            # Status icon
            status = task.get("status", "unknown")
            icon_name = "emblem-default" if status == "completed" else "emblem-error"
            icon = Gtk.Image.new_from_icon_name(icon_name)
            row.append(icon)

            # Task text
            text = task.get("task", "")[:50] + "..."
            label = Gtk.Label(label=text)
            label.set_halign(Gtk.Align.START)
            row.append(label)

            # Store task data
            row.task_data = task

            self.task_list.append(row)

    def _on_task_selected(self, listbox, row):
        """Show task details."""
        if hasattr(row, 'task_data'):
            task = row.task_data
            self.task_id_label.set_text(f"Task ID: {task.get('task_id', '')}")
            self.status_label.set_text(f"Status: {task.get('status', '')}")
            self.task_label.set_text(f"Task: {task.get('task', '')}")

    def _on_filter_changed(self, combo):
        """Filter tasks by status."""
        # TODO: Implement filtering
        pass

    def _on_search_changed(self, entry):
        """Search tasks."""
        # TODO: Implement search
        pass

    def _on_rerun_clicked(self, button):
        """Re-run selected task."""
        # TODO: Get selected task and re-submit
        pass

    def _load_css(self):
        """Load CSS for history view."""
        css = """
        .details-label {
            color: #ffffff;
            font-weight: bold;
            font-size: 14px;
            margin-bottom: 4px;
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
    app = Adw.Application(application_id="org.nemos.TaskHistory")
    app.connect("activate", lambda app: TaskHistoryView(app).present())
    app.run()
