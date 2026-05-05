"""
Nemoclaw Blueprint - System configuration as code.
Loads nemoclaw.config.yaml and validates all sections.
"""
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


class NemoclawBlueprint:
    """
    Describes full Nemoclaw system config as code.
    Loads nemoclaw.config.yaml and validates all sections.
    """

    def __init__(self, config_path: str = "nemoclaw.config.yaml"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load()
        self._validate()

    def _load(self):
        """Load config from YAML file."""
        if not self.config_path.exists():
            logger.warning("Config not found, using defaults", path=self.config_path)
            self.config = self._default_config()
            return

        try:
            with open(self.config_path, "r") as f:
                self.config = yaml.safe_load(f) or {}
            logger.info("Config loaded", path=self.config_path)
        except Exception as e:
            logger.error("Failed to load config", error=str(e))
            self.config = self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "inference_router": {
                "default_model": "hermes-3-70b-q4",
                "fallback_cloud": "nvidia-nemotron",
                "gpu_auto_detect": True,
                "routing_strategy": "task_aware"
            },
            "sandbox": {
                "default_memory_mb": 2048,
                "default_cpu_percent": 80,
                "network_whitelist": ["api.openai.com", "integrate.api.nvidia.com", "huggingface.co"],
                "filesystem_whitelist": ["/sandbox", "/tmp", "/opt/ruflo/models"]
            },
            "model_cache_dir": "/opt/ruflo/models",
            "socket_path": "/run/nemoclaw.sock",
            "health_port": 8001,
            "kernel_device": "/dev/ai_bridge"
        }

    def _validate(self):
        """Validate all sections exist."""
        required_sections = ["inference_router", "sandbox", "model_cache_dir"]
        for section in required_sections:
            if section not in self.config:
                logger.warning("Missing config section", section=section)

    def render(self) -> Dict[str, Any]:
        """
        Returns dict of full system state:
        models, sandboxes, policies, status.
        """
        return {
            "config": self.config,
            "models": self._get_models(),
            "sandboxes": self._get_sandboxes(),
            "policies": self._get_policies(),
            "status": self._get_status()
        }

    def _get_models(self) -> List[Dict]:
        """Get loaded models from registry."""
        registry_path = Path("registry/model_registry.json")
        if registry_path.exists():
            with open(registry_path, "r") as f:
                data = yaml.safe_load(f)
                return data.get("models", [])
        return []

    def _get_sandboxes(self) -> List[Dict]:
        """Get active sandboxes (placeholder)."""
        return []

    def _get_policies(self) -> Dict[str, Any]:
        """Get security policies."""
        policies = {}
        policy_dir = Path("security")
        for policy_file in ["network_policy.yaml", "filesystem_policy.yaml"]:
            path = policy_dir / policy_file
            if path.exists():
                with open(path, "r") as f:
                    policies[policy_file.replace(".yaml", "")] = yaml.safe_load(f)
        return policies

    def _get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        return {
            "health": "healthy",
            "uptime_seconds": 0.0,
            "active_tasks": 0
        }

    def to_yaml(self) -> str:
        """Serialize current state back to YAML."""
        return yaml.dump(self.render(), default_flow_style=False)

    def save(self, path: Optional[str] = None):
        """Save current config to file."""
        target = Path(path) if path else self.config_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            yaml.dump(self.config, f, default_flow_style=False)
        logger.info("Config saved", path=target)


if __name__ == "__main__":
    blueprint = NemoclawBlueprint()
    state = blueprint.render()
    print(yaml.dump(state, default_flow_style=False))
