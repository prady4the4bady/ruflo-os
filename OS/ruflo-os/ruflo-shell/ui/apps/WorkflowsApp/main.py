"""
NemOS Workflows App - Create and manage automation workflows.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class WorkflowsApp(Adw.ApplicationWindow):
    """Create and manage automation workflows."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Workflows")
        self.set_default_size(900, 600)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="Workflows")
        main_box.append(header)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(8)
        toolbar.set_margin_bottom(8)

        new_btn = Gtk.Button(label="New Workflow")
        toolbar.append(new_btn)

        run_btn = Gtk.Button(label="Run")
        toolbar.append(run_btn)

        main_box.append(toolbar)

        # Workflow list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        list_box = Gtk.ListBox()
        for i in range(3):
            row = Adw.ActionRow()
            row.set_title(f"Workflow {i+1}")
            row.set_subtitle("Description here")
            list_box.append(row)

        scroll.set_child(list_box)
        main_box.append(scroll)

        self._load_css()

    def _load_css(self):
        css = "window { background: #1a1a2e; }"
        try:
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(css.encode())
            display = Gdk.Display.get_default()
            Gtk.StyleContext.add_provider_for_display(
                display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except:
            pass

if __name__ == "__main__":
    app = Adw.Application(application_id="org.nemos.Workflows")
    app.connect("activate", lambda app: WorkflowsApp(app).present())
    app.run()
