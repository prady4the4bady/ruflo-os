"""Approval workflow broker — gates destructive actions behind user consent."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


@dataclass
class ApprovalRequest:
    """A pending approval request."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    action_description: str = ""
    risk_level: str = "medium"
    details: dict[str, Any] = field(default_factory=dict)
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ApprovalBroker:
    """Manages approval workflows for destructive or sensitive actions.

    Actions requiring approval:
    - Destructive file operations (delete, overwrite)
    - Package installation
    - Credential/secret entry
    - Browser purchases or form submissions
    - Root/sudo operations
    - Network requests to unknown hosts
    """

    ALWAYS_APPROVE_ACTIONS = frozenset({"read_file", "list_directory", "get_time", "screenshot"})

    def __init__(self, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds
        self._pending: dict[str, ApprovalRequest] = {}
        self._events: dict[str, asyncio.Event] = {}

    async def request_approval(
        self,
        task_id: str,
        action: str,
        details: dict[str, Any] | None = None,
        risk_level: str = "medium",
    ) -> ApprovalRequest:
        """Create an approval request and wait for user decision."""
        # Auto-approve safe actions
        if action in self.ALWAYS_APPROVE_ACTIONS:
            return ApprovalRequest(
                task_id=task_id, action_description=action,
                decision=ApprovalDecision.APPROVED, risk_level="low",
            )

        req = ApprovalRequest(
            task_id=task_id, action_description=action,
            risk_level=risk_level, details=details or {},
        )
        self._pending[req.request_id] = req
        self._events[req.request_id] = asyncio.Event()

        logger.info("approval.requested", request_id=req.request_id,
                     action=action, risk_level=risk_level)

        # Wait for decision or timeout
        try:
            await asyncio.wait_for(self._events[req.request_id].wait(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            req.decision = ApprovalDecision.TIMED_OUT
            logger.warning("approval.timed_out", request_id=req.request_id)

        return req

    def decide(self, request_id: str, approved: bool, reason: str | None = None) -> bool:
        """Submit an approval decision."""
        req = self._pending.get(request_id)
        if not req or req.decision != ApprovalDecision.PENDING:
            return False

        req.decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.REJECTED
        req.decided_at = datetime.now(timezone.utc).isoformat()

        event = self._events.get(request_id)
        if event:
            event.set()

        logger.info("approval.decided", request_id=request_id,
                     decision=req.decision, reason=reason)
        return True

    def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        return [r for r in self._pending.values() if r.decision == ApprovalDecision.PENDING]
