"""
NemOS Rollback & Recovery - System recovery options.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class RollbackRecovery(Adw.ApplicationWindow):
    """System rollback and recovery options."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Rollback & Recovery")
        self.set_default_size(700, 500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="Rollback & Recovery")
        main_box.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        main_box.append(scroll)

        prefs = Adw.PreferencesPage()
        scroll.set_child(prefs)

        # System restore
        group = Adw.PreferencesGroup(title="System Restore")
        prefs.add(group)

        row1 = Adw.ActionRow(title="Restore to Last Snapshot")
        btn1 = Gtk.Button(label="Restore")
        row1.add_suffix(btn1)
        group.add(row1)

        row2 = Adw.ActionRow(title="Create Snapshot")
        btn2 = Gtk.Button(label="Create")
        row2.add_suffix(btn2)
        group.add(row2)

        # Reset options
        group2 = Adw.PreferencesGroup(title="Reset Options")
        prefs.add(group2)

        row3 = Adw.ActionRow(title="Reset User Preferences")
        btn3 = Gtk.Button(label="Reset")
        row3.add_suffix(btn3)
        group2.add(row3)

        row4 = Adw.ActionRow(title="Factory Reset")
        btn4 = Gtk.Button(label="Reset")
        btn4.add_css_class("destructive-action")
        row4.add_suffix(btn4)
        group2.add(row4)

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
    app = Adw.Application(application_id="org.nemos.Recovery")
    app.connect("activate", lambda app: RollbackRecovery(app).present())
    app.run()
