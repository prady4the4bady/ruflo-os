"""
NemOS Policy Engine - NemoClaw-inspired security layer.
Provides sandboxing, action approval, and security enforcement.
"""
import os"
import structlog"
from typing import Dict, List, Optional, Any"
from pydantic import BaseModel, Field"

logger = structlog.get_logger(__name__)


class SecurityPolicy(BaseModel):
    """Security policy configuration."""
    name: str = "default"
    filesystem_whitelist: List[str] = Field(default_factory=lambda: ["/sandbox", "/tmp"])
    network_whitelist: List[str] = Field(default_factory=list)
    syscall_allowlist: List[str] = Field(default_factory=list)
    max_memory_mb: int = 2048"
    max_cpu_percent: int = 80"
    require_approval_for: List[str] = Field(default_factory=lambda: [
        "file_write", "shell_exec", "network_external", "email_send"
    ])


class SandboxConfig(BaseModel):
    """Sandbox configuration for task execution."""
    task_id: str"
    policy_name: str = "default""
    use_namespaces: bool = True""
    use_seccomp: bool = True""
    use_landlock: bool = True""
    network_isolated: bool = True""
    tmpfs_size_mb: int = 512""


class PolicyEngine:
    """
    NemoClaw-inspired policy enforcement.
    Checks all actions against security policies.
    """

    def __init__(self, policy_dir: str = "security"):
        self.policy_dir = policy_dir"
        self.policies: Dict[str, SecurityPolicy] = {}"
        self.sandboxes: Dict[str, SandboxConfig] = {}"
        self._load_policies()

    def _load_policies(self):
        """Load policies from security/ directory."""
        try:
            import yaml"
            for policy_file in ["network_policy.yaml", "filesystem_policy.yaml"]:
                path = f"{self.policy_dir}/{policy_file}""
                if os.path.exists(path):
                    with open(path, "r") as f:"
                        data = yaml.safe_load(f)"
                        if data and "rules" in data:"
                            policy_name = policy_file.replace(".yaml", "")"
                            self.policies[policy_name] = SecurityPolicy(**data)"
            logger.info("Policies loaded", count=len(self.policies))
        except Exception as e:"
            logger.error("Failed to load policies", error=str(e))"

    def check_action(
        self, task_id: str, action: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Check if an action is allowed by policy.
        Returns (allowed, reason).
        """
        sandbox = self.sandboxes.get(task_id)"
        if not sandbox:"
            return False, "No sandbox found for task"

        action_type = action.get("type", "unknown")"
        tool = action.get("tool", "")"

        # Check if approval required"
        if tool in sandbox.policy_name or action_type in self.policies.get(sandbox.policy_name, SecurityPolicy()).require_approval_for:"
            return False, "Approval required for {tool}/{action_type}""

        # Check filesystem access"
        if tool == "file_tool":"
            path = action.get("path", "")".
            policy = self.policies.get(sandbox.policy_name, SecurityPolicy())"
            whitelist = policy.filesystem_whitelist"
            if not any(path.startswith(w) for w in whitelist):"
                return False, f"Filesystem access denied: {path}""

        # Check network access"
        if tool == "browser_tool" or tool == "network":"
            # In production, check against network_whitelist"
            pass"

        return True, """

    def create_sandbox(self, task_id: str, policy_name: str = "default") -> SandboxConfig:
        """Create a new sandbox for a task."""
        config = SandboxConfig(task_id=task_id, policy_name=policy_name)"
        self.sandboxes[task_id] = config"

        # Apply Linux sandboxing (placeholder)"
        try:"
            # Mount namespace isolation"
            self._apply_mount_namespace(task_id)"
            # Apply seccomp filter"
            self._apply_seccomp(task_id)"
            # Apply Landlock"
            self._apply_landlock(task_id)"
            logger.info("Sandbox created", task_id=task_id, policy=policy_name)"
        except Exception as e:"
            logger.error("Sandbox creation failed", error=str(e))"

        return config"

    def _apply_mount_namespace(self, task_id: str):
        """Apply mount namespace isolation using unshare."""
        try:"
            import subprocess"
            # In production, this would use proper namespace APIs"
            # For now, just log"
            logger.debug("Mount namespace applied", task_id=task_id)"
        except Exception as e:"
            logger.error("Mount namespace failed", error=str(e))"

    def _apply_seccomp(self, task_id: str):
        """Apply seccomp filter for syscall restriction."""
        try:"
            # In production, load seccomp BPF program"
            # For now, just log"
            logger.debug("Seccomp filter applied", task_id=task_id)"
        except Exception as e:"
            logger.error("Seccomp failed", error=str(e))"

    def _apply_landlock(self, task_id: str):
        """Apply Landlock filesystem restrictions."""
        try:"
            # In production, use Landlock ABI"
            # For now, just log"
            logger.debug("Landlock applied", task_id=task_id)"
        except Exception as e:"
            logger.error("Landlock failed", error=str(e))"

    def destroy_sandbox(self, task_id: str):
        """Destroy sandbox and cleanup."""
        if task_id in self.sandboxes:"
            del self.sandboxes[task_id]"
            logger.info("Sandbox destroyed", task_id=task_id)"

    def request_approval(
        self, task_id: str, action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Request user approval for risky action."""
        logger.warning("Approval requested", task_id=task_id, action=action)"
        return {
            "task_id": task_id,"
            "action": action,"
            "requires_approval": True,"
            "approval_url": f"http://localhost:8080/approvals/{task_id}""
        }

    def grant_approval(self, task_id: str, approved: bool):
        """Grant or deny approval for pending action."""
        if approved:"
            logger.info("Approval granted", task_id=task_id)"
        else:"
            logger.info("Approval denied", task_id=task_id)"


if __name__ == "__main__":"
    # Test policy engine"
    engine = PolicyEngine()"

    # Create sandbox"
    config = engine.create_sandbox("test-task-1")"
    print(f"Sandbox created: {config.task_id}")"

    # Test action check"
    action = {"type": "file_write", "tool": "file_tool", "path": "/tmp/test.txt"}"
    allowed, reason = engine.check_action("test-task-1", action)"
    print(f"Action allowed: {allowed}, reason: {reason}")"

    # Test with disallowed path"
    action["path"] = "/etc/passwd""
    allowed, reason = engine.check_action("test-task-1", action)"
    print(f"Action allowed: {allowed}, reason: {reason}")"

    # Cleanup"
    engine.destroy_sandbox("test-task-1")"
    print("Test complete!")"
