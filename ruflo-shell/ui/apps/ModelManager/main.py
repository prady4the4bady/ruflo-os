"""
ModelManager - GTK4 window for managing AI models.
List installed models, add new models, download progress, set defaults.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio
import structlog
import httpx
import json
from pathlib import Path

logger = structlog.get_logger(__name__)


class ModelManagerApp(Adw.Application):
    """Main application for Model Manager."""

    def __init__(self):
        super().__init__(
            application_id="org.ruflo.ModelManager",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None
        self.api_base = "http://localhost:8080"

    def do_activate(self):
        if not self.window:
            self.window = ModelManagerWindow(application=self)
        self.window.present()


class ModelManagerWindow(Gtk.ApplicationWindow):
    """Main window for managing AI models."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Ruflo Model Manager")
        self.set_default_size(1000, 700)
        self.set_css_classes(["model-manager-window"])

        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_box)

        # Header
        self._build_header()

        # Content: model list (left) + details (right)
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        content_box.set_vexpand(True)

        # Left: Model list
        self._build_model_list(content_box)

        # Right: Model details
        self._build_model_details(content_box)

        self.main_box.append(content_box)

        # Load models
        self._load_models()

        self._load_css()

    def _build_header(self):
        """Build header bar with Add Model button."""
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)

        # Add Model button
        add_btn = Gtk.Button(label="Add Model")
        add_btn.connect("clicked", self._on_add_model_clicked)
        header.pack_end(add_btn)

        # Refresh button
        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", lambda _: self._load_models())
        header.pack_end(refresh_btn)

        self.main_box.append(header)

    def _build_model_list(self, parent):
        """Build left panel with model list."""
        left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left_panel.set_size_request(350, -1)
        left_panel.set_margin_start(8)
        left_panel.set_margin_end(8)
        left_panel.set_margin_top(8)
        left_panel.set_margin_bottom(8)

        # Title
        label = Gtk.Label(label="Installed Models")
        label.set_css_classes(["panel-title"])
        left_panel.append(label)

        # Scrollable list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.model_list = Gtk.ListBox()
        self.model_list.connect("row-selected", self._on_model_selected)
        scroll.set_child(self.model_list)

        left_panel.append(scroll)
        parent.append(left_panel)

    def _build_model_details(self, parent):
        """Build right panel with model details."""
        right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        right_panel.set_vexpand(True)
        right_panel.set_margin_start(8)
        right_panel.set_margin_end(8)
        right_panel.set_margin_top(8)
        right_panel.set_margin_bottom(8)

        # Model name
        self.model_name_label = Gtk.Label(label="Select a model")
        self.model_name_label.set_css_classes(["model-name"])
        self.model_name_label.set_halign(Gtk.Align.START)
        right_panel.append(self.model_name_label)

        # Size
        self.size_label = Gtk.Label()
        self.size_label.set_halign(Gtk.Align.START)
        right_panel.append(self.size_label)

        # Type
        self.type_label = Gtk.Label()
        self.type_label.set_halign(Gtk.Align.START)
        right_panel.append(self.type_label)

        # Status
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.START)
        right_panel.append(self.status_label)

        # Progress bar (for downloads)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_visible(False)
        right_panel.append(self.progress_bar)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_margin_top(8)

        self.set_default_btn = Gtk.Button(label="Set as Default")
        self.set_default_btn.connect("clicked", self._on_set_default_clicked)
        btn_box.append(self.set_default_btn)

        self.delete_btn = Gtk.Button(label="Delete")
        self.delete_btn.set_css_classes(["destructive-action"])
        self.delete_btn.connect("clicked", self._on_delete_clicked)
        btn_box.append(self.delete_btn)

        right_panel.append(btn_box)

        parent.append(right_panel)

    def _load_models(self):
        """Load models from API."""
        try:
            resp = httpx.get(f"{self.api_base}/api/v1/models")
            if resp.status_code == 200:
                # Clear list
                while child := self.model_list.get_first_child():
                    self.model_list.remove(child)

                models = resp.json().get("models", [])
                for model in models:
                    row = Gtk.Label(label=f"{model.get('name', 'Unknown')}")
                    row.set_halign(Gtk.Align.START)
                    row.set_margin_start(8)
                    row.set_margin_end(8)
                    row.set_margin_top(4)
                    row.set_margin_bottom(4)
                    self.model_list.append(row)
        except Exception as e:
            logger.error("Failed to load models", error=str(e))

    def _on_model_selected(self, listbox, row):
        """Show model details."""
        if row:
            self.model_name_label.set_text(f"Model: {row.get_child().get_label()}")
            # TODO: Fetch full model details

    def _on_add_model_clicked(self, button):
        """Show Add Model dialog."""
        dialog = Gtk.Dialog(title="Add Model", parent=self, flags=0)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)

        content = dialog.get_content_area()

        # Source dropdown
        source_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        source_label = Gtk.Label(label="Source:")
        source_box.append(source_label)

        source_combo = Gtk.ComboBoxText()
        source_combo.append("hf", "HuggingFace")
        source_combo.append("github", "GitHub URL")
        source_combo.append("ollama", "Ollama")
        source_combo.set_active(0)
        source_box.append(source_combo)
        content.append(source_box)

        # Identifier input
        id_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        id_label = Gtk.Label(label="Identifier:")
        id_box.append(id_label)

        id_entry = Gtk.Entry()
        id_entry.set_placeholder_text("repo_id, URL, or model name")
        id_box.append(id_entry)
        content.append(id_box)

        content.show()
        dialog.show()

        # Handle response
        dialog.connect("response", self._on_add_dialog_response, dialog, source_combo, id_entry)

    def _on_add_dialog_response(self, dialog, response, source_combo, id_entry):
        """Handle Add Model dialog response."""
        if response == Gtk.ResponseType.OK:
            source = source_combo.get_active_text()
            identifier = id_entry.get_text()
            if identifier:
                self._pull_model(source, identifier)
        dialog.destroy()

    def _pull_model(self, source: str, identifier: str):
        """Pull model via API."""
        try:
            resp = httpx.post(
                f"{self.api_base}/api/v1/models/pull",
                json={"source": source, "identifier": identifier}
            )
            if resp.status_code == 200:
                logger.info("Model pull started", source=source, identifier=identifier)
                self.progress_bar.set_visible(True)
                GLib.timeout_add(500, self._check_pull_progress)
            else:
                logger.error("Model pull failed", status=resp.status_code)
        except Exception as e:
            logger.error("Model pull error", error=str(e))

    def _check_pull_progress(self):
        """Check download progress (placeholder)."""
        # TODO: Implement progress tracking
        return False  # Stop timer

    def _on_set_default_clicked(self, button):
        """Set selected model as default."""
        # TODO: Implement
        pass

    def _on_delete_clicked(self, button):
        """Delete selected model with confirmation."""
        # TODO: Implement with confirmation dialog
        pass

    def _load_css(self):
        """Load CSS for ModelManager."""
        css = """
        .model-manager-window {
            background: #1c1c1e;
        }
        .panel-title {
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .model-name {
            color: #ffffff;
            font-size: 18px;
            font-weight: bold;
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
            logger.error("Failed to load ModelManager CSS", error=str(e))


if __name__ == "__main__":
    app = ModelManagerApp()
    app.run()
