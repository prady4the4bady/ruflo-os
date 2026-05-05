"""
NemOS Privacy Dashboard - Privacy settings and controls.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class PrivacyDashboard(Adw.ApplicationWindow):
    """Privacy settings and controls."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Privacy Dashboard")
        self.set_default_size(700, 500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="Privacy Dashboard")
        main_box.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        main_box.append(scroll)

        prefs = Adw.PreferencesPage()
        scroll.set_child(prefs)

        # Screen recording section
        group = Adw.PreferencesGroup(title="Screen Recording")
        prefs.add(group)

        switch = Adw.SwitchRow(title="Allow Screen Capture")
        group.add(switch)

        switch2 = Adw.SwitchRow(title="Blur Sensitive Content")
        group.add(switch2)

        # Data collection section
        group2 = Adw.PreferencesGroup(title="Data Collection")
        prefs.add(group2)

        switch3 = Adw.SwitchRow(title="Send Telemetry")
        group2.add(switch3)

        switch4 = Adw.SwitchRow(title="Crash Reports")
        group2.add(switch4)

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
    app = Adw.Application(application_id="org.nemos.PrivacyDashboard")
    app.connect("activate", lambda app: PrivacyDashboard(app).present())
    app.run()
