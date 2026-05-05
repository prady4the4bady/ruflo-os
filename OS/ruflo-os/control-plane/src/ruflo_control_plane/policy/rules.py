"""Default policy rules for Ruflo OS."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyRule:
    """A single policy rule."""
    name: str
    action_pattern: str  # regex pattern for matching actions
    verdict: str  # "allow", "deny", "require_approval"
    reason: str
    agent_types: list[str] = field(default_factory=lambda: ["*"])
    conditions: dict[str, Any] = field(default_factory=dict)

    def matches(self, action: str, agent_type: str, context: dict[str, Any]) -> bool:
        if not re.match(self.action_pattern, action):
            return False
        if "*" not in self.agent_types and agent_type not in self.agent_types:
            return False
        return True


DEFAULT_RULES: list[PolicyRule] = [
    # Safe reads — always allow
    PolicyRule(
        name="allow-reads",
        action_pattern=r"^(read_file|list_directory|get_.*|screenshot|query_atspi)$",
        verdict="allow",
        reason="Read-only operations are safe",
    ),
    # Destructive file ops — require approval
    PolicyRule(
        name="destructive-file-ops",
        action_pattern=r"^(delete_file|overwrite_file|move_file|chmod|chown)$",
        verdict="require_approval",
        reason="Destructive file operations need user consent",
    ),
    # Package management — require approval
    PolicyRule(
        name="package-install",
        action_pattern=r"^(apt_install|pip_install|npm_install|snap_install)$",
        verdict="require_approval",
        reason="Package installation needs user consent",
    ),
    # Shell/sudo — require approval
    PolicyRule(
        name="shell-exec",
        action_pattern=r"^(run_shell|sudo_exec|systemctl_.*)$",
        verdict="require_approval",
        reason="Shell execution and system control need approval",
    ),
    # Network to unknown — require approval
    PolicyRule(
        name="network-unknown",
        action_pattern=r"^(http_request|download_file|upload_file)$",
        verdict="require_approval",
        reason="Network requests to external hosts need approval",
    ),
    # Credential operations — always require approval
    PolicyRule(
        name="credential-ops",
        action_pattern=r"^(enter_password|submit_credentials|access_keychain)$",
        verdict="require_approval",
        reason="Credential operations always require explicit consent",
    ),
    # Browser purchases — deny by default
    PolicyRule(
        name="browser-purchase",
        action_pattern=r"^(browser_purchase|submit_payment)$",
        verdict="deny",
        reason="Financial transactions are denied by default",
    ),
    # GUI actions — allow with logging
    PolicyRule(
        name="gui-actions",
        action_pattern=r"^(click|type_text|scroll|key_press|mouse_move)$",
        verdict="allow",
        reason="GUI interactions are allowed with audit logging",
    ),
    # Write file — allow for non-sensitive paths
    PolicyRule(
        name="write-file",
        action_pattern=r"^write_file$",
        verdict="allow",
        reason="File writes to workspace paths are allowed",
    ),
]
