#!/usr/bin/env python3
"""Ruflo Spotlight — KRunner DBus plugin for AI-powered launcher.

Provides a Spotlight-style search experience:
- Application launching
- File search
- AI command input (prefix with '>')
- System settings search
- Calculator
"""

from __future__ import annotations

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib  # type: ignore


class RufloSpotlight(dbus.service.Object):
    """DBus service for KRunner integration."""

    def __init__(self) -> None:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName("com.ruflo.spotlight", bus)
        super().__init__(bus_name, "/runner")

    @dbus.service.method(
        "org.kde.krunner1",
        in_signature="s",
        out_signature="a(sssida{sv})",
    )
    def Match(self, query: str) -> list:
        """Return matches for a KRunner query."""
        results = []

        if not query or len(query) < 2:
            return results

        # AI command mode
        if query.startswith(">"):
            ai_query = query[1:].strip()
            if ai_query:
                results.append((
                    f"ai-{hash(ai_query)}",    # id
                    ai_query,                    # text
                    "Ask Ruflo AI",             # subtext
                    "ruflo-ai",                 # icon
                    100,                        # relevance
                    1.0,                        # type (ExactMatch)
                    {},                         # properties
                ))

        # Quick calculations
        if query.replace(".", "").replace("+", "").replace("-", "").replace("*", "").replace("/", "").replace(" ", "").isdigit() or (
            any(op in query for op in ["+", "-", "*", "/"])
        ):
            try:
                result = eval(query, {"__builtins__": {}})  # noqa: S307
                results.append((
                    f"calc-{hash(query)}",
                    f"= {result}",
                    f"Calculate: {query}",
                    "accessories-calculator",
                    90,
                    1.0,
                    {},
                ))
            except Exception:
                pass

        return results

    @dbus.service.method("org.kde.krunner1", in_signature="ss")
    def Run(self, match_id: str, action_id: str) -> None:
        """Execute a matched result."""
        if match_id.startswith("ai-"):
            # Send to control plane for AI processing
            import subprocess
            subprocess.Popen([
                "curl", "-s", "-X", "POST",
                "http://localhost:9000/api/v1/tasks",
                "-H", "Content-Type: application/json",
                "-d", f'{{"goal": "{match_id[3:]}", "requires_approval": true}}',
            ])


def main() -> None:
    """Start the Ruflo Spotlight KRunner service."""
    RufloSpotlight()
    loop = GLib.MainLoop()
    loop.run()


if __name__ == "__main__":
    main()
