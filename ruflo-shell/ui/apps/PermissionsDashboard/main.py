"""
NemOS Permissions Dashboard - App permissions management.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class PermissionsDashboard(Adw.ApplicationWindow):
    """Manage app permissions."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Permissions")
        self.set_default_size(700, 500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="Permissions")
        main_box.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        main_box.append(scroll)

        prefs = Adw.PreferencesPage()
        scroll.set_child(prefs)

        # Agent permissions
        group = Adw.PreferencesGroup(title="Agent Permissions")
        prefs.add(group)

        row1 = Adw.SwitchRow(title="Screen Recording")
        group.add(row1)

        row2 = Adw.SwitchRow(title="File Access")
        group.add(row2)

        row3 = Adw.SwitchRow(title="Network Access")
        group.add(row3)

        row4 = Adw.SwitchRow(title="Keyboard Simulation")
        group.add(row4)

        # App permissions
        group2 = Adw.PreferencesGroup(title="Application Permissions")
        prefs.add(group2)

        row5 = Adw.SwitchRow(title="Camera")
        group2.add(row5)

        row6 = Adw.SwitchRow(title="Microphone")
        group2.add(row6)

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
    app = Adw.Application(application_id="org.nemos.Permissions")
    app.connect("activate", lambda app: PermissionsDashboard(app).present())
    app.run()
