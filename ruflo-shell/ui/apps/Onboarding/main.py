"""
NemOS Onboarding Flow - First-run experience.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class OnboardingWindow(Adw.ApplicationWindow):
    """First-run onboarding experience."""

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Welcome to NemOS")
        self.set_default_size(700, 500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Welcome header
        welcome = Gtk.Label(label="Welcome to NemOS")
        welcome.add_css_class("title-1")
        welcome.set_margin_top(40)
        main_box.append(welcome)

        # Description
        desc = Gtk.Label(label="Your AI-native desktop environment")
        desc.add_css_class("dim-label")
        desc.set_margin_top(10)
        main_box.append(desc)

        # Steps
        steps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        steps_box.set_margin_top(40)
        steps_box.set_margin_start(60)
        steps_box.set_margin_end(60)

        step1 = Adw.ActionRow(title="1. Choose AI Model", subtitle="Select local or cloud model")
        steps_box.append(step1)

        step2 = Adw.ActionRow(title="2. Privacy Settings", subtitle="Configure screen recording")
        steps_box.append(step2)

        step3 = Adw.ActionRow(title="3. Permissions", subtitle="Grant necessary permissions")
        steps_box.append(step3)

        main_box.append(steps_box)

        # Get Started button
        btn_box = Gtk.Box(halign=Gtk.Align.CENTER)
        btn_box.set_margin_top(40)
        btn_box.set_margin_bottom(40)

        start_btn = Gtk.Button(label="Get Started")
        start_btn.add_css_class("suggested-action")
        start_btn.connect("clicked", self._on_start)
        btn_box.append(start_btn)

        main_box.append(btn_box)

        self._load_css()

    def _on_start(self, button):
        """Start using NemOS."""
        self.close()

    def _load_css(self):
        css = """
        window { background: #1a1a2e; }
        label { color: white; }
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
    app = Adw.Application(application_id="org.nemos.Onboarding")
    app.connect("activate", lambda app: OnboardingWindow(app).present())
    app.run()
