"""SQLAlchemy models for the control plane database."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Float, Integer, String, Text, JSON
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TaskModel(Base):
    """Persistent task record."""
    __tablename__ = "tasks"

    task_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    goal = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    priority = Column(String(16), nullable=False, default="normal")
    token_budget = Column(Integer, nullable=False, default=100000)
    tokens_used = Column(Integer, nullable=False, default=0)
    requires_approval = Column(Integer, nullable=False, default=1)  # boolean as int
    parent_task_id = Column(String(36), nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AuditEntryModel(Base):
    """Persistent audit log entry."""
    __tablename__ = "audit_log"

    entry_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    event_type = Column(String(64), nullable=False)
    task_id = Column(String(36), nullable=True, index=True)
    agent_type = Column(String(32), nullable=True)
    action = Column(String(128), nullable=False)
    details = Column(JSON, nullable=True)
    outcome = Column(String(32), nullable=False)
    previous_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False)


class ApprovalModel(Base):
    """Persistent approval request record."""
    __tablename__ = "approvals"

    request_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    action_description = Column(Text, nullable=False)
    risk_level = Column(String(16), nullable=False, default="medium")
    details = Column(JSON, nullable=True)
    decision = Column(String(16), nullable=False, default="pending")
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
