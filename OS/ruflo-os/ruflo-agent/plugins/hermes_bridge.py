"""
Hermes Bridge - Plugin system bridge for Ruflo Agent.
Connects Ruflo Agent to Hermes-Agent plugin architecture.
"""
import structlog
from typing import Dict, List, Any, Optional

logger = structlog.get_logger(__name__)


class HermesPlugin:
    """Base class for Hermes plugins."""

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.enabled = True

    def initialize(self) -> bool:
        """Initialize plugin. Override in subclasses."""
        return True

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute plugin action. Override in subclasses."""
        return {"success": False, "error": "Not implemented"}


class WebSearchPlugin(HermesPlugin):
    """Plugin for web search tasks."""

    def __init__(self):
        super().__init__("web_search", "1.0.0")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("query", "")
        if not query:
            return {"success": False, "error": "No query provided"}

        try:
            import httpx
            resp = httpx.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json"}
            )
            if resp.status_code == 200:
                results = resp.json().get("AbstractText", "")
                return {"success": True, "result": results}
            return {"success": False, "error": "Search failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class CodeExecutionPlugin(HermesPlugin):
    """Plugin for code execution tasks."""

    def __init__(self):
        super().__init__("code_execution", "1.0.0")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        code = context.get("code", "")
        language = context.get("language", "python")

        if not code:
            return {"success": False, "error": "No code provided"}

        try:
            if language == "python":
                import sys
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                exec(code)
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                return {"success": True, "output": output}
            else:
                return {"success": False, "error": f"Unsupported language: {language}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class HermesBridge:
    """Bridge to load and manage Hermes plugins."""

    def __init__(self):
        self.plugins: Dict[str, HermesPlugin] = {}
        self._load_default_plugins()

    def _load_default_plugins(self):
        """Load default plugins."""
        self.register(WebSearchPlugin())
        self.register(CodeExecutionPlugin())
        logger.info("Default plugins loaded", count=len(self.plugins))

    def register(self, plugin: HermesPlugin) -> None:
        """Register a plugin."""
        self.plugins[plugin.name] = plugin
        logger.info("Plugin registered", name=plugin.name, version=plugin.version)

    def unregister(self, name: str) -> bool:
        """Unregister a plugin."""
        if name in self.plugins:
            del self.plugins[name]
            logger.info("Plugin unregistered", name=name)
            return True
        return False

    def execute_plugin(self, name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a plugin by name."""
        plugin = self.plugins.get(name)
        if not plugin:
            return {"success": False, "error": f"Plugin {name} not found"}
        if not plugin.enabled:
            return {"success": False, "error": f"Plugin {name} is disabled"}

        return plugin.execute(context)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins."""
        return [
            {
                "name": p.name,
                "version": p.version,
                "enabled": p.enabled
            }
            for p in self.plugins.values()
        ]

    def enable_plugin(self, name: str) -> bool:
        if name in self.plugins:
            self.plugins[name].enabled = True
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        if name in self.plugins:
            self.plugins[name].enabled = False
            return True
        return False


if __name__ == "__main__":
    bridge = HermesBridge()
    print("Loaded plugins:", bridge.list_plugins())

    # Test web search
    result = bridge.execute_plugin("web_search", {"query": "Python programming"})
    print("Web search result:", result)

    # Test code execution
    result = bridge.execute_plugin("code_execution", {"code": "print('Hello from plugin')"})
    print("Code execution result:", result)
