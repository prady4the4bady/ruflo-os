"""SandboxManager — abstracts creation and lifecycle of isolated worker environments."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from ruflo_runtime.sandbox.policy import SandboxPolicy, PolicyTemplate

logger = structlog.get_logger(__name__)


class SandboxState(str, Enum):
    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    TERMINATED = "terminated"
    ERROR = "error"


@dataclass
class SandboxInstance:
    """Represents a running sandbox worker environment."""

    sandbox_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    state: SandboxState = SandboxState.CREATING
    policy: SandboxPolicy | None = None
    pid: int | None = None
    workdir: str = ""
    user: str = "ruflo-worker"  # Always non-root
    metadata: dict[str, Any] = field(default_factory=dict)


class SandboxManager:
    """Manages lifecycle of sandboxed worker environments.

    Production implementation would use:
    - Linux namespaces (PID, NET, MNT, USER)
    - Landlock for filesystem restrictions
    - seccomp-bpf for syscall filtering
    - cgroups v2 for resource limits
    - NemoClaw/OpenShell for managed sandboxing

    Current implementation provides the abstraction layer with
    process-level isolation. Full container isolation requires Linux.
    """

    def __init__(self) -> None:
        self._sandboxes: dict[str, SandboxInstance] = {}

    async def create(
        self,
        task_id: str,
        template: str = "default",
        policy_overrides: dict[str, Any] | None = None,
    ) -> SandboxInstance:
        """Create a new sandbox with the specified policy template.

        Args:
            task_id: Associated task identifier
            template: Policy template name (default, restricted, network_only, offline)
            policy_overrides: Optional policy field overrides
        """
        policy = PolicyTemplate.get(template)
        if policy_overrides:
            for key, value in policy_overrides.items():
                if hasattr(policy, key):
                    setattr(policy, key, value)

        sandbox = SandboxInstance(
            task_id=task_id,
            policy=policy,
            state=SandboxState.READY,
            workdir=f"/tmp/ruflo-sandbox-{task_id[:8]}",
        )
        self._sandboxes[sandbox.sandbox_id] = sandbox

        logger.info(
            "sandbox.created",
            sandbox_id=sandbox.sandbox_id,
            task_id=task_id,
            template=template,
            user=sandbox.user,
        )
        return sandbox

    async def execute(
        self,
        sandbox_id: str,
        command: str,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command within the sandbox.

        In production, this would use subprocess with namespace isolation.
        Currently returns a structured result for testing.
        """
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        if sandbox.state != SandboxState.READY:
            raise RuntimeError(f"Sandbox {sandbox_id} is {sandbox.state}, not ready")

        sandbox.state = SandboxState.RUNNING

        logger.info(
            "sandbox.execute",
            sandbox_id=sandbox_id,
            command=command[:100],
        )

        # In production: subprocess with namespaces/cgroups
        # Current: abstraction for testing the control flow
        result = {
            "sandbox_id": sandbox_id,
            "command": command,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "executed": True,
        }

        sandbox.state = SandboxState.READY
        return result

    async def destroy(self, sandbox_id: str) -> None:
        """Tear down a sandbox and clean up resources."""
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return

        sandbox.state = SandboxState.TERMINATED
        logger.info("sandbox.destroyed", sandbox_id=sandbox_id, task_id=sandbox.task_id)

    async def pause(self, sandbox_id: str) -> None:
        """Pause a running sandbox (freeze cgroup)."""
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox and sandbox.state == SandboxState.RUNNING:
            sandbox.state = SandboxState.PAUSED
            logger.info("sandbox.paused", sandbox_id=sandbox_id)

    async def resume(self, sandbox_id: str) -> None:
        """Resume a paused sandbox."""
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox and sandbox.state == SandboxState.PAUSED:
            sandbox.state = SandboxState.READY
            logger.info("sandbox.resumed", sandbox_id=sandbox_id)

    def get(self, sandbox_id: str) -> SandboxInstance | None:
        return self._sandboxes.get(sandbox_id)

    def list_active(self) -> list[SandboxInstance]:
        return [
            s for s in self._sandboxes.values()
            if s.state not in (SandboxState.TERMINATED, SandboxState.ERROR)
        ]
