"""
PRADY TRADER — Scheduler for periodic tasks.
Handles: model retraining, daily resets, weight updates, Telegram summaries.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from utils.time_utils import utc_now

logger = logging.getLogger("prady.utils.scheduler")


class ScheduledTask:
    """A single scheduled task."""

    def __init__(
        self,
        name: str,
        coro_factory: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
    ):
        self.name = name
        self.coro_factory = coro_factory
        self.interval = interval_seconds
        self.run_immediately = run_immediately
        self.last_run: Optional[datetime] = None
        self.run_count: int = 0
        self.error_count: int = 0

    def is_due(self) -> bool:
        if self.last_run is None:
            return self.run_immediately
        return utc_now() >= self.last_run + timedelta(seconds=self.interval)


class Scheduler:
    """
    Async task scheduler for periodic operations.
    """

    def __init__(self):
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False

    def register(
        self,
        name: str,
        coro_factory: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
    ):
        """Register a periodic task."""
        self._tasks[name] = ScheduledTask(
            name=name,
            coro_factory=coro_factory,
            interval_seconds=interval_seconds,
            run_immediately=run_immediately,
        )
        logger.info("Registered task '%s' (every %ds)", name, interval_seconds)

    def unregister(self, name: str):
        """Remove a registered task."""
        self._tasks.pop(name, None)

    async def _run_task(self, task: ScheduledTask):
        """Execute a single task with error handling."""
        try:
            logger.debug("Running task '%s'", task.name)
            await task.coro_factory()
            task.last_run = utc_now()
            task.run_count += 1
        except Exception as exc:
            task.error_count += 1
            logger.exception("Task '%s' failed: %s", task.name, exc)

    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        logger.info("Scheduler started with %d tasks", len(self._tasks))

        while self._running:
            for task in self._tasks.values():
                if task.is_due():
                    await self._run_task(task)
            await asyncio.sleep(1)

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        logger.info("Scheduler stopped")

    def get_status(self) -> List[Dict]:
        """Get status of all tasks."""
        return [
            {
                "name": t.name,
                "interval": t.interval,
                "last_run": t.last_run.isoformat() if t.last_run else None,
                "run_count": t.run_count,
                "error_count": t.error_count,
            }
            for t in self._tasks.values()
        ]


def setup_default_tasks(scheduler: Scheduler):
    """Register the default periodic tasks."""
    from council.weight_manager import WeightManager
    from execution.position_tracker import PositionTracker
    from execution.risk_manager import RiskManager
    from utils.telegram_bot import get_telegram_bot

    async def daily_reset():
        """Reset daily counters at UTC midnight."""
        now = utc_now()
        if now.hour == 0 and now.minute < 2:
            logger.info("Performing daily reset")
            risk = RiskManager()
            risk.daily_loss = 0.0
            risk.daily_trades = 0
            tracker = PositionTracker()
            stats = tracker.get_stats()
            bot = get_telegram_bot()
            await bot.send_daily_summary({
                "date": now.strftime("%Y-%m-%d"),
                "total_trades": stats.get("total_trades", 0),
                "win_rate": stats.get("win_rate", 0),
                "total_pnl": stats.get("total_pnl", 0),
                "open_positions": stats.get("open_positions", 0),
            })
            logger.info("Daily reset complete")

    async def weight_update():
        """Update agent weights based on recent accuracy."""
        logger.info("Scheduled weight update")
        wm = WeightManager()
        wm.update_weights()
        current = wm.get_current_weights()
        logger.info("Updated agent weights: %s", current)

    async def model_retrain_check():
        """Check if models need retraining (every 24h)."""
        logger.info("Checking model freshness")
        from ml.model_store import get_latest_model_path
        from config.settings import get_settings
        import os

        settings = get_settings()
        stale_symbols = []
        for symbol in settings.trading_pairs:
            path = get_latest_model_path("xgboost", symbol)
            if path is None:
                stale_symbols.append(symbol)
                continue
            mtime = os.path.getmtime(path)
            age_hours = (utc_now().timestamp() - mtime) / 3600
            if age_hours > 48:
                stale_symbols.append(symbol)
                logger.info("Model for %s is %.1fh old — needs retrain", symbol, age_hours)

        if stale_symbols:
            logger.info("Triggering retrain for %d symbols: %s", len(stale_symbols), stale_symbols)
            from ml.trainer import run_training_pipeline
            for symbol in stale_symbols:
                try:
                    await run_training_pipeline(symbol)
                    logger.info("Retrained models for %s", symbol)
                except Exception as exc:
                    logger.error("Retrain failed for %s: %s", symbol, exc)
        else:
            logger.info("All models are fresh — no retraining needed")

    scheduler.register("daily_reset", daily_reset, 60, run_immediately=False)
    scheduler.register("weight_update", weight_update, 3600, run_immediately=False)
    scheduler.register("model_retrain", model_retrain_check, 86400, run_immediately=False)
