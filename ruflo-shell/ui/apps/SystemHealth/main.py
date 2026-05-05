"""
NemOS System Health Dashboard - System metrics and health.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class SystemHealthDashboard(Adw.ApplicationWindow):
    """System health metrics and monitoring."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("System Health")
        self.set_default_size(800, 600)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="System Health")
        main_box.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        main_box.append(scroll)

        prefs = Adw.PreferencesPage()
        scroll.set_child(prefs)

        # CPU
        group = Adw.PreferencesGroup(title="System Metrics")
        prefs.add(group)

        row1 = Adw.ActionRow(title="CPU Usage", subtitle="45%")
        group.add(row1)

        row2 = Adw.ActionRow(title="Memory", subtitle="8.2 GB / 16 GB")
        group.add(row2)

        row3 = Adw.ActionRow(title="Disk", subtitle="256 GB / 512 GB")
        group.add(row3)

        # Services
        group2 = Adw.PreferencesGroup(title="Services")
        prefs.add(group2)

        row4 = Adw.ActionRow(title="Model Gateway", subtitle="Running")
        group2.add(row4)

        row5 = Adw.ActionRow(title="Agent Orchestrator", subtitle="Running")
        group2.add(row5)

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
    app = Adw.Application(application_id="org.nemos.SystemHealth")
    app.connect("activate", lambda app: SystemHealthDashboard(app).present())
    app.run()
