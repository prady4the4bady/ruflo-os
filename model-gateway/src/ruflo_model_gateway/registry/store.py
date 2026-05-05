"""Persistent model registry backed by SQLite."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import structlog

from ruflo_model_gateway.providers.base import ModelInfo

logger = structlog.get_logger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    capabilities TEXT NOT NULL DEFAULT '[]',
    context_window INTEGER NOT NULL DEFAULT 4096,
    cost_per_1k_input REAL NOT NULL DEFAULT 0.0,
    cost_per_1k_output REAL NOT NULL DEFAULT 0.0,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class ModelRegistryStore:
    """SQLite-backed model registry for tracking available models."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute(CREATE_TABLE_SQL)
        await self._db.commit()
        logger.info("registry.initialized", path=str(self.db_path))

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()

    async def add_model(
        self,
        model_id: str,
        provider: str,
        display_name: str = "",
        capabilities: list[str] | None = None,
        context_window: int = 4096,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
        source_url: str | None = None,
    ) -> None:
        """Register a model in the registry."""
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO models
               (model_id, provider, display_name, capabilities, context_window,
                cost_per_1k_input, cost_per_1k_output, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                model_id, provider, display_name,
                json.dumps(capabilities or []),
                context_window, cost_per_1k_input, cost_per_1k_output, source_url,
            ),
        )
        await self._db.commit()

    async def remove_model(self, model_id: str) -> None:
        """Remove a model from the registry."""
        assert self._db is not None
        await self._db.execute("DELETE FROM models WHERE model_id = ?", (model_id,))
        await self._db.commit()

    async def get_model(self, model_id: str) -> ModelInfo | None:
        """Get a single model by ID."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM models WHERE model_id = ?", (model_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_model_info(row)
            return None

    async def list_models(self) -> list[ModelInfo]:
        """List all registered models."""
        assert self._db is not None
        async with self._db.execute("SELECT * FROM models ORDER BY provider, model_id") as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_model_info(row) for row in rows]

    @staticmethod
    def _row_to_model_info(row: tuple) -> ModelInfo:
        """Convert a database row to ModelInfo."""
        return ModelInfo(
            id=row[0],
            provider=row[1],
            display_name=row[2],
            capabilities=json.loads(row[3]),
            context_window=row[4],
            cost_per_1k_input=row[5],
            cost_per_1k_output=row[6],
            source_url=row[7],
            owned_by=row[1],
        )
