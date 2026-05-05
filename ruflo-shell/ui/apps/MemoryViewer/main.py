"""
NemOS Memory & Preferences Viewer - User preferences and memory.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class MemoryViewer(Adw.ApplicationWindow):
    """View and manage user preferences and memory."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Memory & Preferences")
        self.set_default_size(700, 500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar(title="Memory & Preferences")
        main_box.append(header)

        # Tabs
        stack = Gtk.Stack()
        stack.set_vexpand(True)

        # Preferences tab
        prefs_page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="User Preferences")
        row1 = Adw.EntryRow(title="Name")
        group.add(row1)
        row2 = Adw.ComboRow(title="Theme", model=Gtk.StringList.new(["Dark", "Light"]))
        group.add(row2)
        prefs_page.add(group)
        stack.add_titled(prefs_page, "prefs", "Preferences")

        # Memory tab
        memory_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow()
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.get_buffer().set_text("Memory items will appear here...")
        scroll.set_child(text_view)
        memory_page.append(scroll)
        stack.add_titled(memory_page, "memory", "Memory")

        main_box.append(stack)

        # Switcher
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(stack)
        header.set_title_widget(switcher)

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
    app = Adw.Application(application_id="org.nemos.MemoryViewer")
    app.connect("activate", lambda app: MemoryViewer(app).present())
    app.run()
