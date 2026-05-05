"""
Settings - GTK4 Preferences window for Ruflo OS.
Sections: AI Settings, Display, Privacy, Shortcuts.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio
import structlog
import json
from pathlib import Path

logger = structlog.get_logger(__name__)


class SettingsApp(Adw.Application):
    """Main Settings application."""

    def __init__(self):
        super().__init__(
            application_id="org.ruflo.Settings",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = SettingsWindow(application=self)
        self.window.present()


class SettingsWindow(Adw.PreferencesWindow):
    """Settings window with multiple pages."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Ruflo Settings")
        self.set_default_size(800, 600)

        # Load settings
        self.settings_path = Path("/var/ruflo/settings.json")
        self.settings = self._load_settings()

        # Build pages
        self._build_ai_page()
        self._build_display_page()
        self._build_privacy_page()
        self._build_shortcuts_page()

        self._load_css()

    def _load_settings(self) -> dict:
        """Load settings from disk."""
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load settings", error=str(e))
        return {
            "ai": {"default_model": "hermes-3-70b-q4", "task_timeout": 300},
            "display": {"theme": "dark", "wallpaper": "default"},
            "privacy": {"screen_recording": True, "audit_logging": True},
            "shortcuts": {"spotlight": "<Ctrl>space", "task_intake": "<Ctrl><Shift>a"}
        }

    def _save_settings(self):
        """Save settings to disk."""
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_path, "w") as f:
                json.dump(self.settings, f, indent=2)
            logger.info("Settings saved")
        except Exception as e:
            logger.error("Failed to save settings", error=str(e))

    def _build_ai_page(self):
        """AI Settings page."""
        page = Adw.PreferencesPage(title="AI Settings", icon_name="preferences-system-symbolic")

        # Default model group
        group = Adw.PreferencesGroup(title="Model Selection")
        page.add(group)

        # Default model selector
        model_row = Adw.ComboRow(title="Default Model", subtitle="Model used for new tasks")
        model_list = Gtk.StringList()
        for model in ["hermes-3-70b-q4", "qwen-coder-32b-q4", "llava-34b-q4", "deepseek-r1-32b-q4"]:
            model_list.append(model)
        model_row.set_model(model_list)
        model_row.set_selected(0)
        group.add(model_row)

        # Cloud API keys group
        cloud_group = Adw.PreferencesGroup(title="Cloud API Keys")
        page.add(cloud_group)

        # NVIDIA API key
        nvidia_row = Adw.EntryRow(title="NVIDIA API Key", subtitle="For cloud fallback")
        nvidia_row.set_text(self.settings["ai"].get("nvidia_api_key", ""))
        nvidia_row.connect("apply", self._on_nvidia_key_changed)
        cloud_group.add(nvidia_row)

        # OpenAI API key
        openai_row = Adw.EntryRow(title="OpenAI API Key", subtitle="For OpenAI-compatible endpoints")
        openai_row.set_text(self.settings["ai"].get("openai_api_key", ""))
        openai_row.connect("apply", self._on_openai_key_changed)
        cloud_group.add(openai_row)

        # Task timeout slider
        timeout_group = Adw.PreferencesGroup(title="Task Execution")
        page.add(timeout_group)

        timeout_row = Adw.SpinRow(title="Task Timeout (seconds)", subtitle="Maximum time for a single task")
        timeout_row.set_adjustment(Gtk.Adjustment(value=self.settings["ai"]["task_timeout"], lower=60, upper=3600, step_increment=60))
        timeout_group.add(timeout_row)

        self.add(page)

    def _build_display_page(self):
        """Display settings page."""
        page = Adw.PreferencesPage(title="Display", icon_name="video-display-symbolic")

        # Theme group
        theme_group = Adw.PreferencesGroup(title="Theme")
        page.add(theme_group)

        theme_row = Adw.ComboRow(title="Theme", subtitle="Choose light or dark theme")
        theme_list = Gtk.StringList()
        for theme in ["light", "dark"]:
            theme_list.append(theme)
        theme_row.set_model(theme_list)
        theme_row.set_selected(0 if self.settings["display"]["theme"] == "light" else 1)
        theme_row.connect("notify::selected", self._on_theme_changed)
        theme_group.add(theme_row)

        # Wallpaper group
        wallpaper_group = Adw.PreferencesGroup(title="Wallpaper")
        page.add(wallpaper_group)

        wallpaper_row = Adw.EntryRow(title="Wallpaper Path", subtitle="Path to wallpaper image")
        wallpaper_row.set_text(self.settings["display"].get("wallpaper", ""))
        wallpaper_row.connect("apply", self._on_wallpaper_changed)
        wallpaper_group.add(wallpaper_row)

        self.add(page)

    def _build_privacy_page(self):
        """Privacy settings page."""
        page = Adw.PreferencesPage(title="Privacy", icon_name="dialog-password-symbolic")

        # Screen recording group
        recording_group = Adw.PreferencesGroup(title="Screen Recording")
        page.add(recording_group)

        recording_row = Adw.SwitchRow(title="Allow Screen Recording", subtitle="Required for agent to see screen")
        recording_row.set_active(self.settings["privacy"]["screen_recording"])
        recording_row.connect("notify::active", self._on_recording_toggled)
        recording_group.add(recording_row)

        # Audit logging group
        audit_group = Adw.PreferencesGroup(title="Audit Logging")
        page.add(audit_group)

        audit_row = Adw.SwitchRow(title="Enable Audit Logging", subtitle="Log all agent actions")
        audit_row.set_active(self.settings["privacy"]["audit_logging"])
        audit_row.connect("notify::active", self._on_audit_toggled)
        audit_group.add(audit_row)

        self.add(page)

    def _build_shortcuts_page(self):
        """Shortcuts settings page."""
        page = Adw.PreferencesPage(title="Shortcuts", icon_name="input-keyboard-symbolic")

        # Shortcuts group
        shortcuts_group = Adw.PreferencesGroup(title="Keyboard Shortcuts")
        page.add(shortcuts_group)

        spotlight_row = Adw.EntryRow(title="Spotlight", subtitle="Open Spotlight search")
        spotlight_row.set_text(self.settings["shortcuts"]["spotlight"])
        spotlight_row.connect("apply", self._on_spotlight_shortcut_changed)
        shortcuts_group.add(spotlight_row)

        task_row = Adw.EntryRow(title="Task Intake", subtitle="Open Task Intake app")
        task_row.set_text(self.settings["shortcuts"]["task_intake"])
        task_row.connect("apply", self._on_task_shortcut_changed)
        shortcuts_group.add(task_row)

        self.add(page)

    def _on_nvidia_key_changed(self, row, *args):
        self.settings["ai"]["nvidia_api_key"] = row.get_text()
        self._save_settings()

    def _on_openai_key_changed(self, row, *args):
        self.settings["ai"]["openai_api_key"] = row.get_text()
        self._save_settings()

    def _on_theme_changed(self, row, *args):
        selected = row.get_selected()
        self.settings["display"]["theme"] = "light" if selected == 0 else "dark"
        self._save_settings()

    def _on_wallpaper_changed(self, row, *args):
        self.settings["display"]["wallpaper"] = row.get_text()
        self._save_settings()

    def _on_recording_toggled(self, row, *args):
        self.settings["privacy"]["screen_recording"] = row.get_active()
        self._save_settings()

    def _on_audit_toggled(self, row, *args):
        self.settings["privacy"]["audit_logging"] = row.get_active()
        self._save_settings()

    def _on_spotlight_shortcut_changed(self, row, *args):
        self.settings["shortcuts"]["spotlight"] = row.get_text()
        self._save_settings()

    def _on_task_shortcut_changed(self, row, *args):
        self.settings["shortcuts"]["task_intake"] = row.get_text()
        self._save_settings()

    def _load_css(self):
        """Load CSS for Settings window."""
        css = """
        preferenceswindow {
            background: #1c1c1e;
        }
        preferencesgroup {
            margin: 8px;
        }
        row {
            color: #ffffff;
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
            logger.error("Failed to load Settings CSS", error=str(e))


if __name__ == "__main__":
    app = SettingsApp()
    app.run()
