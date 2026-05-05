"""Secret broker — agents never see raw secrets, only opaque references."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SecretHandle:
    handle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    secret_name: str = ""
    service: str = ""
    scoped_action: str = ""
    task_id: str = ""
    issued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    use_count: int = 0
    max_uses: int = 1
    revoked: bool = False


class SecretBroker:
    """Agents NEVER see raw secrets. They get opaque handles scoped to actions."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}
        self._handles: dict[str, SecretHandle] = {}

    def register_secret(self, name: str, value: str) -> str:
        fingerprint = hashlib.sha256(value.encode()).hexdigest()[:16]
        self._secrets[name] = value
        return fingerprint

    def issue_handle(self, secret_name: str, task_id: str, scoped_action: str, max_uses: int = 1) -> SecretHandle:
        if secret_name not in self._secrets:
            raise ValueError(f"Secret '{secret_name}' not found")
        handle = SecretHandle(secret_name=secret_name, scoped_action=scoped_action, task_id=task_id, max_uses=max_uses)
        self._handles[handle.handle_id] = handle
        logger.info("secret_broker.issued", handle_id=handle.handle_id, action=scoped_action)
        return handle

    async def use_secret(self, handle_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        handle = self._handles.get(handle_id)
        if not handle:
            raise ValueError(f"Unknown handle: {handle_id}")
        if handle.revoked:
            raise PermissionError("Handle revoked")
        if handle.use_count >= handle.max_uses:
            raise PermissionError("Handle exhausted")
        handle.use_count += 1
        logger.info("secret_broker.used", handle_id=handle_id, action=handle.scoped_action)
        return {"status": "executed", "scoped_action": handle.scoped_action, "remaining": handle.max_uses - handle.use_count}

    def revoke(self, handle_id: str) -> None:
        handle = self._handles.get(handle_id)
        if handle:
            handle.revoked = True

    def revoke_for_task(self, task_id: str) -> int:
        count = 0
        for h in self._handles.values():
            if h.task_id == task_id and not h.revoked:
                h.revoked = True
                count += 1
        return count
