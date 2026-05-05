import os
import yaml
from typing import List, Dict
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)

class PolicyRule(BaseModel):
    id: str
    action: str  # allow, deny, audit
    resource: str
    pattern: str
    description: str

class PolicyEngine:
    """Security policy enforcement for Nemoclaw."""

    def __init__(self, policy_dir: str = "security"):
        self.policy_dir = policy_dir
        self.network_rules: List[PolicyRule] = []
        self.filesystem_rules: List[PolicyRule] = []
        self.syscall_allowlist: List[str] = []
        self._load_policies()

    def _load_policies(self) -> None:
        # Load network policy
        net_path = os.path.join(os.path.dirname(__file__), "..", self.policy_dir, "network_policy.yaml")
        if os.path.exists(net_path):
            with open(net_path, "r") as f:
                data = yaml.safe_load(f)
                self.network_rules = [PolicyRule(**r) for r in data.get("rules", [])]
            logger.info("Loaded network policy", rules=len(self.network_rules))

        # Load filesystem policy
        fs_path = os.path.join(os.path.dirname(__file__), "..", self.policy_dir, "filesystem_policy.yaml")
        if os.path.exists(fs_path):
            with open(fs_path, "r") as f:
                data = yaml.safe_load(f)
                self.filesystem_rules = [PolicyRule(**r) for r in data.get("rules", [])]
            logger.info("Loaded filesystem policy", rules=len(self.filesystem_rules))

        # Load syscall allowlist
        sc_path = os.path.join(os.path.dirname(__file__), "..", self.policy_dir, "syscall_allowlist.txt")
        if os.path.exists(sc_path):
            with open(sc_path, "r") as f:
                self.syscall_allowlist = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            logger.info("Loaded syscall allowlist", count=len(self.syscall_allowlist))

    def check_network_egress(self, host: str, port: int) -> bool:
        """Check if network egress is allowed."""
        for rule in self.network_rules:
            if rule.resource == "egress":
                # Simple pattern match (placeholder for proper CIDR/regex)
                if rule.pattern in host or rule.pattern == "*":
                    return rule.action == "allow"
        return False  # Default deny

    def check_filesystem_access(self, path: str, mode: str) -> bool:
        """Check if filesystem access is allowed."""
        for rule in self.filesystem_rules:
            if rule.resource == "filesystem":
                if rule.pattern in path:
                    return rule.action == "allow"
        return False

    def check_syscall(self, syscall_name: str) -> bool:
        """Check if syscall is in allowlist."""
        return syscall_name in self.syscall_allowlist or "__all__" in self.syscall_allowlist

    def reload_policies(self) -> None:
        """Hot-reload policies without restart."""
        self._load_policies()
        logger.info("Policies reloaded")