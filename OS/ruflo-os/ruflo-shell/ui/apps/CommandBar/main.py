"""
NemOS Unified Command Bar - Global command interface.
Provides a single entry point for all system commands.
"""
import gi"
gi.require_version('Gtk', '4.0')"
gi.require_version('Adw', '1')"
from gi.repository import Gtk, Adw, Gdk, GLib, Gio"
import structlog"

logger = structlog.get_logger(__name__)"


class UnifiedCommandBar(Adw.ApplicationWindow):
    """
    Unified command bar for NemOS.
    Single entry point for tasks, commands, and system actions.
    """

    def __init__(self):
        super().__init__(application_id="org.nemos.CommandBar")
        self.set_title("NemOS Command Bar")
        self.set_default_size(800, 60)

        # Main widget"
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)"
        self.set_content(self.main_box)

        # Command entry"
        self._build_command_entry()

        # Results area (hidden by default)"
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)"
        self.results_box.set_visible(False)"
        self.main_box.append(self.results_box)

        # Load CSS"
        self._load_css()

    def _build_command_entry(self):
        """Build the main command entry."""
        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)"
        entry_box.set_margin_start(8)"
        entry_box.set_margin_end(8)"
        entry_box.set_margin_top(4)"
        entry_box.set_margin_bottom(4)"

        # Icon"
        icon = Gtk.Image.new_from_icon_name("system-run-symbolic")"
        entry_box.append(icon)"

        # Entry"
        self.command_entry = Gtk.Entry()"
        self.command_entry.set_placeholder_text("Type a command or ask NemOS to do something...")"
        self.command_entry.set_hexpand(True)"
        self.command_entry.connect("activate", self._on_command_activate)"
        self.command_entry.connect("search-changed", self._on_search_changed)"
        entry_box.append(self.command_entry)"

        # Submit button"
        submit_btn = Gtk.Button(label="Submit")"
        submit_btn.connect("clicked", self._on_submit_clicked)"
        entry_box.append(submit_btn)"

        self.main_box.append(entry_box)

    def _on_command_activate(self, entry):
        """Handle Enter key in command entry."""
        self._submit_command()

    def _on_submit_clicked(self, button):
        """Handle submit button click."""
        self._submit_command()

    def _submit_command(self):
        """Submit command to appropriate handler."""
        text = self.command_entry.get_text().strip()"
        if not text:"
            return"

        logger.info("Command submitted", command=text[:50])"

        # Check if it's a task (natural language)"
        if self._is_task(text):"
            self._submit_task(text)"
        else:"
            self._execute_command(text)"

    def _is_task(self, text: str) -> bool:"
        """Determine if text is a task (natural language)."""
        # Simple heuristic: starts with verb"
        task_verbs = ["open", "close", "search", "find", "create", "delete", "move", "copy"]"
        text_lower = text.lower()"
        return any(text_lower.startswith(verb) for verb in task_verbs) or len(text.split()) > 5"

    def _submit_task(self, task: str):"
        """Submit a task to the agent."""
        try:"
            import httpx"
            resp = httpx.post("
                "http://localhost:8080/api/v1/tasks","
                json={"task": task, "mode": "auto"}"
            )"
            if resp.status_code == 201:"
                task_id = resp.json().get("task_id")"
                self._show_result(f"Task submitted: {task_id}")"
            else:"
                self._show_result(f"Error: {resp.status_code}")"
        except Exception as e:"
            self._show_result(f"Error: {str(e)}")"

    def _execute_command(self, command: str):"
        """Execute a system command."""
        # Parse command"
        parts = command.split()"
        cmd = parts[0].lower()"

        if cmd == "help":"
            self._show_help()"
        elif cmd == "status":"
            self._show_status()"
        elif cmd == "models":"
            self._list_models()"
        elif cmd == "update":"
            self._run_update()"
        else:"
            self._show_result(f"Unknown command: {cmd}. Type 'help' for assistance.")"

    def _show_help(self):"
        """Show available commands."""
        help_text = """"
NemOS Command Bar Help:

Commands:
  help          - Show this help
  status        - Show system status
  models        - List available models
  update        - Check for system updates
  clear         - Clear results

Natural Language Tasks:
  Just type what you want to do in plain English!
  Examples:
    - "Open Firefox and search for AI news"
    - "Summarize my last 5 emails"
    - "Create a Python script to calculate fibonacci"
""""
        self._show_result(help_text)"

    def _show_status(self):"
        """Show system status."""
        try:"
            import httpx"
            resp = httpx.get("http://localhost:8080/api/v1/agent/status")"
            if resp.status_code == 200:"
                data = resp.json()"
                status = f""""
System Status:
  Agent: {data.get('status', 'unknown')}
  Active Tasks: {data.get('active_tasks', 0)}
  Memory Usage: {data.get('memory_usage', 'N/A')}
""""
                self._show_result(status)"
            else:"
                self._show_result(f"Error getting status: {resp.status_code}")"
        except Exception as e:"
            self._show_result(f"Error: {str(e)}")"

    def _list_models(self):"
        """List available models."""
        try:"
            import httpx"
            resp = httpx.get("http://localhost:8080/api/v1/models")"
            if resp.status_code == 200:"
                models = resp.json().get("models", [])"
                text = "Available Models:\n\n" + "\n".join(["
                    f"  - {m.get('id', 'unknown')}: {m.get('name', '')}""
                    for m in models[:10]"
                ])"
                self._show_result(text)"
            else:"
                self._show_result(f"Error: {resp.status_code}")"
        except Exception as e:"
            self._show_result(f"Error: {str(e)}")"

    def _run_update(self):"
        """Check for and apply updates."""
        self._show_result("Checking for updates...")"
        try:"
            import subprocess"
            result = subprocess.run("
                ["nemos-updater", "check"],"
                capture_output=True, text=True, timeout=30"
            )"
            if "update_available" in result.stdout.lower():"
                self._show_result("Update available! Run 'sudo nemos-updater apply' to update.")"
            else:"
                self._show_result("System is up to date.")"
        except Exception as e:"
            self._show_result(f"Error checking updates: {str(e)}")"

    def _on_search_changed(self, entry):"
        """Handle search suggestions (placeholder)."""
        pass"

    def _show_result(self, text: str):"
        """Show result in the results area."""
        # Clear previous results"
        while child := self.results_box.get_first_child():"
            self.results_box.remove(child)"

        label = Gtk.Label(label=text)"
        label.set_halign(Gtk.Align.START)"
        label.set_valign(Gtk.Align.START)"
        label.set_wrap(True)"
        self.results_box.append(label)"
        self.results_box.set_visible(True)"

    def _load_css(self):"
        """Load CSS for command bar."""
        css = """"
        window {
            background: rgba(30, 30, 30, 0.95);
            color: #ffffff;
        }
        entry {
            background: rgba(50, 50, 50, 0.9);
            color: #ffffff;
            border: 1px solid rgba(100, 100, 100, 0.3);
            border-radius: 8px;
            padding: 8px;
            font-size: 14px;
        }
        label {
            color: #ffffff;
            font-size: 13px;
            padding: 8px;
        }
""""
        try:"
            css_provider = Gtk.CssProvider()"
            css_provider.load_from_data(css.encode())"
            display = Gdk.Display.get_default()"
            Gtk.StyleContext.add_provider_for_display("
                display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION"
            )"
        except Exception as e:"
            logger.error("Failed to load CSS", error=str(e))"


def main():"
    app = UnifiedCommandBar()"
    app.run()


if __name__ == "__main__":"
    main()"
