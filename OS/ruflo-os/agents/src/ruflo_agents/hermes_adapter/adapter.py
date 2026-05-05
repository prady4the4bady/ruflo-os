"""Hermes memory adapter — 3-layer memory system for persistent learning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MemoryEntry:
    entry_id: str = ""
    layer: str = ""  # "episodic", "semantic", "procedural"
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    relevance_score: float = 0.0


class HermesMemoryAdapter:
    """Adapter for Hermes Agent's 3-layer memory system.

    Layer 1 — Episodic: Task execution traces, screenshots, outcomes
    Layer 2 — Semantic: Extracted facts, user preferences, system knowledge
    Layer 3 — Procedural: Learned skills, reusable action sequences

    When Hermes SDK is available, this delegates to it.
    Currently provides an in-memory implementation.
    """

    def __init__(self) -> None:
        self._episodic: list[MemoryEntry] = []
        self._semantic: list[MemoryEntry] = []
        self._procedural: list[MemoryEntry] = []

    async def store_episodic(self, task_id: str, content: str, metadata: dict | None = None) -> str:
        """Store a task execution trace."""
        entry = MemoryEntry(entry_id=f"ep-{len(self._episodic)}", layer="episodic",
                            content=content, metadata={"task_id": task_id, **(metadata or {})})
        self._episodic.append(entry)
        logger.info("hermes.store_episodic", entry_id=entry.entry_id, task_id=task_id)
        return entry.entry_id

    async def store_semantic(self, fact: str, source: str = "") -> str:
        """Store an extracted fact or preference."""
        entry = MemoryEntry(entry_id=f"sem-{len(self._semantic)}", layer="semantic",
                            content=fact, metadata={"source": source})
        self._semantic.append(entry)
        return entry.entry_id

    async def store_procedural(self, skill_name: str, steps: list[str], success_rate: float = 1.0) -> str:
        """Store a learned skill (reusable action sequence)."""
        entry = MemoryEntry(entry_id=f"proc-{len(self._procedural)}", layer="procedural",
                            content=skill_name, metadata={"steps": steps, "success_rate": success_rate})
        self._procedural.append(entry)
        logger.info("hermes.store_skill", skill=skill_name, steps=len(steps))
        return entry.entry_id

    async def recall(self, query: str, layer: str | None = None, limit: int = 5) -> list[MemoryEntry]:
        """Recall memories matching a query. Basic keyword search (production: vector similarity)."""
        query_lower = query.lower()
        pools = []
        if layer is None or layer == "episodic":
            pools.extend(self._episodic)
        if layer is None or layer == "semantic":
            pools.extend(self._semantic)
        if layer is None or layer == "procedural":
            pools.extend(self._procedural)

        scored = []
        for entry in pools:
            score = sum(1 for word in query_lower.split() if word in entry.content.lower())
            if score > 0:
                entry.relevance_score = score
                scored.append(entry)

        scored.sort(key=lambda e: e.relevance_score, reverse=True)
        return scored[:limit]

    async def get_skills(self) -> list[MemoryEntry]:
        """Get all learned procedural skills."""
        return list(self._procedural)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "episodic": len(self._episodic),
            "semantic": len(self._semantic),
            "procedural": len(self._procedural),
        }
