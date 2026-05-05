"""Append-only hash-chained audit log service."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AuditEntry:
    """A single audit log entry in the hash chain."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = ""
    task_id: str | None = None
    agent_type: str | None = None
    action: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    outcome: str = ""  # "success", "failure", "denied", "approved"
    previous_hash: str = ""
    entry_hash: str = ""

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry."""
        payload = json.dumps({
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "action": self.action,
            "outcome": self.outcome,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class AuditService:
    """Append-only hash-chained audit log.

    Every external action, approval decision, policy evaluation,
    and agent operation is recorded with a hash chain for tamper evidence.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._last_hash: str = "0" * 64  # genesis hash

    def log(
        self,
        event_type: str,
        action: str,
        outcome: str,
        task_id: str | None = None,
        agent_type: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Record an audit entry with hash chaining."""
        entry = AuditEntry(
            event_type=event_type,
            task_id=task_id,
            agent_type=agent_type,
            action=action,
            details=details or {},
            outcome=outcome,
            previous_hash=self._last_hash,
        )
        entry.entry_hash = entry.compute_hash()
        self._entries.append(entry)
        self._last_hash = entry.entry_hash

        logger.info(
            "audit.recorded",
            event_type=event_type, action=action, outcome=outcome,
            task_id=task_id, hash=entry.entry_hash[:16],
        )
        return entry

    def verify_chain(self) -> bool:
        """Verify the integrity of the hash chain."""
        if not self._entries:
            return True

        prev_hash = "0" * 64
        for entry in self._entries:
            if entry.previous_hash != prev_hash:
                logger.error("audit.chain_broken", entry_id=entry.entry_id)
                return False
            computed = entry.compute_hash()
            if computed != entry.entry_hash:
                logger.error("audit.hash_mismatch", entry_id=entry.entry_id)
                return False
            prev_hash = entry.entry_hash
        return True

    def get_entries(
        self,
        task_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters."""
        entries = self._entries
        if task_id:
            entries = [e for e in entries if e.task_id == task_id]
        if event_type:
            entries = [e for e in entries if e.event_type == event_type]
        return entries[-limit:]

    @property
    def count(self) -> int:
        return len(self._entries)
