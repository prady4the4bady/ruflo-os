"""Structured event types for runtime operations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventCategory(str, Enum):
    SANDBOX = "sandbox"
    FILE_ACCESS = "file_access"
    SECRET_ACCESS = "secret_access"
    NETWORK = "network"
    GUI = "gui"
    POLICY = "policy"
    LIFECYCLE = "lifecycle"


class RuntimeEvent(BaseModel):
    """Structured event emitted by runtime components."""

    event_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: EventCategory
    severity: EventSeverity = EventSeverity.INFO
    source: str = ""
    task_id: str | None = None
    worker_id: str | None = None
    action: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    outcome: str = ""  # "success", "denied", "error"


class SandboxCreatedEvent(RuntimeEvent):
    category: EventCategory = EventCategory.SANDBOX
    action: str = "sandbox_created"


class SandboxDestroyedEvent(RuntimeEvent):
    category: EventCategory = EventCategory.SANDBOX
    action: str = "sandbox_destroyed"


class FileAccessEvent(RuntimeEvent):
    category: EventCategory = EventCategory.FILE_ACCESS
    path: str = ""
    operation: str = ""  # "read", "write", "delete"


class SecretAccessEvent(RuntimeEvent):
    category: EventCategory = EventCategory.SECRET_ACCESS
    secret_name: str = ""
    operation: str = ""  # "use", "revoke"


class NetworkEvent(RuntimeEvent):
    category: EventCategory = EventCategory.NETWORK
    host: str = ""
    port: int = 0
    protocol: str = ""
    allowed: bool = False
