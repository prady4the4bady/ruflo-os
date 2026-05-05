"""File broker — opaque handle-based file access for sandboxed agents."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FileHandle:
    """Opaque file handle issued to agents — never exposes the real path directly."""

    handle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    real_path: str = ""  # Internal only — never sent to agents
    display_name: str = ""
    permissions: str = "read"  # "read", "write", "read_write"
    task_id: str = ""
    issued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str | None = None
    revoked: bool = False


class FileBroker:
    """Mediates file access between agents and the host filesystem.

    Agents never see raw file paths. They receive opaque handles that
    the broker resolves internally. This prevents path traversal,
    unauthorized access, and information leakage.
    """

    # Paths that are always denied
    DENIED_PATHS = frozenset({
        "/etc/shadow", "/etc/gshadow", "/etc/sudoers",
        "/root", "/var/run/docker.sock",
    })

    DENIED_PATTERNS = [".ssh", ".gnupg", ".aws", ".config/gcloud"]

    def __init__(self, workspace_root: str = "/tmp/ruflo-workspace") -> None:
        self.workspace_root = workspace_root
        self._handles: dict[str, FileHandle] = {}

    def issue_handle(
        self,
        real_path: str,
        task_id: str,
        permissions: str = "read",
        display_name: str | None = None,
    ) -> FileHandle:
        """Issue an opaque file handle for a real path.

        Validates the path against deny lists before issuing.
        """
        resolved = os.path.realpath(real_path)
        # For cross-platform testing (Windows), check if the resolved path ends with the denied paths
        resolved_posix = Path(resolved).as_posix()
        if any(resolved_posix.endswith(dp) for dp in self.DENIED_PATHS) or resolved_posix in self.DENIED_PATHS:
            raise PermissionError(f"Access to {resolved} is denied by policy")

        for pattern in self.DENIED_PATTERNS:
            if pattern in resolved:
                raise PermissionError(f"Access to paths containing '{pattern}' is denied")

        handle = FileHandle(
            real_path=resolved,
            display_name=display_name or Path(resolved).name,
            permissions=permissions,
            task_id=task_id,
        )
        self._handles[handle.handle_id] = handle

        logger.info(
            "file_broker.handle_issued",
            handle_id=handle.handle_id,
            display_name=handle.display_name,
            permissions=permissions,
            task_id=task_id,
        )
        return handle

    def resolve(self, handle_id: str) -> str:
        """Resolve an opaque handle to its real path. Internal use only."""
        handle = self._handles.get(handle_id)
        if not handle:
            raise ValueError(f"Unknown file handle: {handle_id}")
        if handle.revoked:
            raise PermissionError(f"File handle {handle_id} has been revoked")
        return handle.real_path

    async def read(self, handle_id: str) -> bytes:
        """Read file content via handle."""
        handle = self._handles.get(handle_id)
        if not handle:
            raise ValueError(f"Unknown file handle: {handle_id}")
        if handle.revoked:
            raise PermissionError("Handle revoked")
        if handle.permissions not in ("read", "read_write"):
            raise PermissionError("Handle does not have read permission")

        path = Path(handle.real_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {handle.display_name}")

        logger.info("file_broker.read", handle_id=handle_id, path=handle.display_name)
        return path.read_bytes()

    async def write(self, handle_id: str, content: bytes) -> int:
        """Write file content via handle."""
        handle = self._handles.get(handle_id)
        if not handle:
            raise ValueError(f"Unknown file handle: {handle_id}")
        if handle.revoked:
            raise PermissionError("Handle revoked")
        if handle.permissions not in ("write", "read_write"):
            raise PermissionError("Handle does not have write permission")

        path = Path(handle.real_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

        logger.info("file_broker.write", handle_id=handle_id, bytes_written=len(content))
        return len(content)

    def revoke(self, handle_id: str) -> None:
        """Revoke a file handle."""
        handle = self._handles.get(handle_id)
        if handle:
            handle.revoked = True
            logger.info("file_broker.handle_revoked", handle_id=handle_id)

    def revoke_for_task(self, task_id: str) -> int:
        """Revoke all handles for a task."""
        count = 0
        for handle in self._handles.values():
            if handle.task_id == task_id and not handle.revoked:
                handle.revoked = True
                count += 1
        logger.info("file_broker.task_handles_revoked", task_id=task_id, count=count)
        return count

    def get_handle_info(self, handle_id: str) -> dict[str, Any]:
        """Get sanitized handle info (no real path exposed)."""
        handle = self._handles.get(handle_id)
        if not handle:
            raise ValueError(f"Unknown file handle: {handle_id}")
        return {
            "handle_id": handle.handle_id,
            "display_name": handle.display_name,
            "permissions": handle.permissions,
            "revoked": handle.revoked,
        }
