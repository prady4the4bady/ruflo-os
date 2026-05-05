"""
NemOS Approvals Center - User approval for risky actions.
Shows pending approvals and allows grant/deny.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio
import structlog
import json
from typing import Dict, List, Optional

logger = structlog.get_logger(__name__)


class ApprovalsCenter(Adw.ApplicationWindow):
    """
    Approvals Center for NemOS.
    Shows pending approvals and allows user interaction.
    """

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Approvals Center")
        self.set_default_size(800, 600)

        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(self.main_box)

        # Header
        header = Adw.HeaderBar(title="Pending Approvals")
        self.main_box.append(header)

        # Approval list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.approval_list = Gtk.ListBox()
        self.approval_list.connect("row-activated", self._on_row_activated)
        scroll.set_child(self.approval_list)

        self.main_box.append(scroll)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(8)
        btn_box.set_margin_bottom(8)

        self.grant_btn = Gtk.Button(label="Grant")
        self.grant_btn.connect("clicked", self._on_grant_clicked)
        btn_box.append(self.grant_btn)

        self.deny_btn = Gtk.Button(label="Deny")
        self.deny_btn.connect("clicked", self._on_deny_clicked)
        btn_box.append(self.deny_btn)

        self.main_box.append(btn_box)

        # Load pending approvals
        self._load_approvals()

        self._load_css()

    def _load_approvals(self):
        """Load pending approvals from API."""
        try:
            import httpx
            resp = httpx.get("http://localhost:8080/api/v1/approvals")
            if resp.status_code == 200:
                approvals = resp.json().get("approvals", [])
                self._populate_list(approvals)
        except Exception as e:
            logger.error("Failed to load approvals", error=str(e))

    def _populate_list(self, approvals: List[Dict]):
        """Populate approval list."""
        # Clear existing
        while child := self.approval_list.get_first_child():
            self.approval_list.remove(child)

        for approval in approvals:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            # Status icon
            icon = Gtk.Image.new_from_icon_name("dialog-question-symbolic")
            row.append(icon)

            # Task info
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            task_label = Gtk.Label(label=approval.get("task_id", "Unknown"))
            task_label.set_halign(Gtk.Align.START)
            info_box.append(task_label)

            action_label = Gtk.Label(label=approval.get("action", {}).get("tool", "Unknown action"))
            action_label.set_halign(Gtk.Align.START)
            action_label.add_css_class("secondary")
            info_box.append(action_label)

            row.append(info_box)

            # Store approval data
            row.approval_data = approval

            self.approval_list.append(row)

    def _on_row_activated(self, listbox, row):
        """Handle row selection."""
        pass

    def _on_grant_clicked(self, button):
        """Grant selected approval."""
        selected_row = self.approval_list.get_selected_row()
        if not selected_row:
            return

        row = selected_row.get_child()
        if not hasattr(row, 'approval_data'):
            return

        approval = row.approval_data
        task_id = approval.get("task_id")

        try:
            import httpx
            resp = httpx.post(f"http://localhost:8080/api/v1/approvals/{task_id}/grant")
            if resp.status_code == 200:
                logger.info("Approval granted", task_id=task_id)
                self._load_approvals()  # Refresh
        except Exception as e:
            logger.error("Failed to grant approval", error=str(e))

    def _on_deny_clicked(self, button):
        """Deny selected approval."""
        selected_row = self.approval_list.get_selected_row()
        if not selected_row:
            return

        row = selected_row.get_child()
        if not hasattr(row, 'approval_data'):
            return

        approval = row.approval_data
        task_id = approval.get("task_id")

        try:
            import httpx
            resp = httpx.post(f"http://localhost:8080/api/v1/approvals/{task_id}/deny")
            if resp.status_code == 200:
                logger.info("Approval denied", task_id=task_id)
                self._load_approvals()  # Refresh
        except Exception as e:
            logger.error("Failed to deny approval", error=str(e))

    def _load_css(self):
        """Load CSS for approvals center."""
        css = """
        .secondary {
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
            logger.error("Failed to load CSS", error=str(e))


if __name__ == "__main__":
    app = Adw.Application(application_id="org.nemos.Approvals")
    app.connect("activate", lambda app: ApprovalsCenter(app).present())
    app.run()
