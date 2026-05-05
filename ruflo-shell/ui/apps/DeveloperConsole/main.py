"""
NemOS Developer Console - Logs, debugging tools, and diagnostics.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib

class DeveloperConsole(Adw.ApplicationWindow):
    """Developer console for debugging and logs."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Developer Console")
        self.set_default_size(1000, 700)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="Developer Console")
        main_box.append(header)

        # Tab view
        stack = Gtk.Stack()

        # Logs tab
        logs_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        clear_btn = Gtk.Button(label="Clear")
        toolbar.append(clear_btn)
        logs_page.append(toolbar)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.get_buffer().set_text("Logs will appear here...\n")
        scroll.set_child(text_view)
        logs_page.append(scroll)
        stack.add_titled(logs_page, "logs", "Logs")

        # Console tab
        console_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        entry = Gtk.Entry(placeholder_text="Enter command...")
        console_page.append(entry)
        stack.add_titled(console_page, "console", "Console")

        main_box.append(stack)

        # Switcher
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(stack)
        header.set_title_widget(switcher)

        self._load_css()

    def _load_css(self):
        css = """
        window { background: #1a1a2e; }
        textview { background: #0d0d1a; color: #00ff00; }
        """
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
    app = Adw.Application(application_id="org.nemos.DevConsole")
    app.connect("activate", lambda app: DeveloperConsole(app).present())
    app.run()
