"""
PRADY TRADER — Self-healing health monitor.
Runs 7 checks on a configurable interval and exposes status + auto-recovery.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import psutil
from loguru import logger

ROOT_DIR = Path(__file__).resolve().parent.parent
HEALTH_FILE = ROOT_DIR / "data" / "health_status.json"


@dataclass
class HealthCheck:
    name: str
    status: str = "unknown"  # healthy, degraded, critical
    message: str = ""
    last_check: float = 0.0
    consecutive_failures: int = 0


@dataclass
class HealthStatus:
    overall: str = "unknown"
    checks: Dict[str, HealthCheck] = field(default_factory=dict)
    uptime_sec: float = 0.0
    start_time: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "uptime_sec": round(time.time() - self.start_time, 1),
            "checks": {
                name: {
                    "status": c.status,
                    "message": c.message,
                    "last_check": c.last_check,
                    "consecutive_failures": c.consecutive_failures,
                }
                for name, c in self.checks.items()
            },
        }


class HealthMonitor:
    """Runs periodic health checks with auto-recovery actions."""

    def __init__(
        self,
        interval_sec: int = 30,
        on_critical: Optional[Callable] = None,
    ) -> None:
        self._interval = interval_sec
        self._on_critical = on_critical
        self._status = HealthStatus()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def status(self) -> HealthStatus:
        return self._status

    async def start(self) -> None:
        """Start the health check loop."""
        self._running = True
        self._status.start_time = time.time()
        self._task = asyncio.create_task(self._loop())
        logger.info("Health monitor started (interval={}s)", self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitor stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.run_all_checks()
                self._persist()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Health check loop error: {}", exc)
            await asyncio.sleep(self._interval)

    async def run_all_checks(self) -> HealthStatus:
        """Execute all health checks and update status."""
        await self._check_binance()
        await self._check_cycle_freshness()
        await self._check_redis()
        self._check_balance_safety()
        self._check_position_age()
        self._check_disk()
        self._check_memory()

        # Compute overall
        statuses = [c.status for c in self._status.checks.values()]
        if any(s == "critical" for s in statuses):
            self._status.overall = "critical"
            if self._on_critical:
                try:
                    self._on_critical()
                except Exception as exc:
                    logger.error("on_critical callback failed: {}", exc)
        elif any(s == "degraded" for s in statuses):
            self._status.overall = "degraded"
        else:
            self._status.overall = "healthy"

        return self._status

    # ── Individual checks ────────────────────────────────────────

    async def _check_binance(self) -> None:
        name = "binance_api"
        check = self._status.checks.setdefault(name, HealthCheck(name=name))
        try:
            from data.binance_client import BinanceClientWrapper
            client = BinanceClientWrapper()
            ticker = client.get_ticker_price("BTCUSDT")
            price = float(ticker.get("lastPrice", 0)) if isinstance(ticker, dict) else 0
            if price > 0:
                check.status = "healthy"
                check.message = f"BTC=${price:,.0f}"
                check.consecutive_failures = 0
            else:
                raise ValueError("Zero price returned")
        except Exception as exc:
            check.consecutive_failures += 1
            check.status = "critical" if check.consecutive_failures >= 3 else "degraded"
            check.message = str(exc)[:100]
            logger.warning("Binance health check failed ({}x): {}", check.consecutive_failures, exc)
        check.last_check = time.time()

    async def _check_cycle_freshness(self) -> None:
        name = "cycle_freshness"
        check = self._status.checks.setdefault(name, HealthCheck(name=name))
        state_file = ROOT_DIR / "data" / "last_state.json"
        try:
            if state_file.exists():
                data = json.loads(state_file.read_text(encoding="utf-8"))
                last_ts = data.get("timestamp", 0)
                age = time.time() - last_ts
                if age < 300:  # 5 minutes
                    check.status = "healthy"
                    check.message = f"Last cycle {age:.0f}s ago"
                    check.consecutive_failures = 0
                else:
                    check.status = "degraded"
                    check.message = f"Stale: last cycle {age:.0f}s ago"
                    check.consecutive_failures += 1
            else:
                check.status = "degraded"
                check.message = "No state file yet"
                check.consecutive_failures = 0
        except Exception as exc:
            check.status = "degraded"
            check.message = str(exc)[:100]
        check.last_check = time.time()

    async def _check_redis(self) -> None:
        name = "redis"
        check = self._status.checks.setdefault(name, HealthCheck(name=name))
        try:
            from config.settings import get_settings
            settings = get_settings()
            if not settings.redis_url:
                check.status = "healthy"
                check.message = "Not configured (using in-memory)"
                check.last_check = time.time()
                return
            import redis as _redis
            r = _redis.from_url(settings.redis_url, socket_timeout=3)
            r.ping()
            check.status = "healthy"
            check.message = "Connected"
            check.consecutive_failures = 0
        except Exception as exc:
            check.consecutive_failures += 1
            check.status = "degraded"
            check.message = str(exc)[:100]
        check.last_check = time.time()

    def _check_balance_safety(self) -> None:
        name = "balance_safety"
        check = self._status.checks.setdefault(name, HealthCheck(name=name))
        state_file = ROOT_DIR / "data" / "last_state.json"
        try:
            if state_file.exists():
                data = json.loads(state_file.read_text(encoding="utf-8"))
                balance = float(data.get("balance", 10000))
                initial = float(data.get("initial_balance", 10000))
                drawdown = (initial - balance) / initial if initial > 0 else 0
                if drawdown < 0.10:
                    check.status = "healthy"
                    check.message = f"Balance=${balance:,.2f} (drawdown={drawdown:.1%})"
                    check.consecutive_failures = 0
                elif drawdown < 0.20:
                    check.status = "degraded"
                    check.message = f"High drawdown: {drawdown:.1%}"
                    check.consecutive_failures += 1
                else:
                    check.status = "critical"
                    check.message = f"CRITICAL drawdown: {drawdown:.1%}"
                    check.consecutive_failures += 1
            else:
                check.status = "healthy"
                check.message = "No state file yet"
        except Exception as exc:
            check.status = "degraded"
            check.message = str(exc)[:100]
        check.last_check = time.time()

    def _check_position_age(self) -> None:
        name = "position_age"
        check = self._status.checks.setdefault(name, HealthCheck(name=name))
        state_file = ROOT_DIR / "data" / "last_state.json"
        try:
            if state_file.exists():
                data = json.loads(state_file.read_text(encoding="utf-8"))
                positions = data.get("open_positions", [])
                max_age = 0
                for pos in positions:
                    opened = pos.get("opened_at", time.time())
                    age = (time.time() - opened) / 60
                    max_age = max(max_age, age)
                if max_age > 480:  # 8 hours
                    check.status = "degraded"
                    check.message = f"Oldest position: {max_age:.0f}min"
                    check.consecutive_failures += 1
                else:
                    check.status = "healthy"
                    check.message = f"{len(positions)} positions, max age={max_age:.0f}min"
                    check.consecutive_failures = 0
            else:
                check.status = "healthy"
                check.message = "No state file"
        except Exception as exc:
            check.status = "degraded"
            check.message = str(exc)[:100]
        check.last_check = time.time()

    def _check_disk(self) -> None:
        name = "disk_space"
        check = self._status.checks.setdefault(name, HealthCheck(name=name))
        try:
            usage = psutil.disk_usage(str(ROOT_DIR))
            free_gb = usage.free / (1024 ** 3)
            pct_used = usage.percent
            if free_gb < 1.0:
                check.status = "critical"
                check.message = f"Only {free_gb:.1f} GB free ({pct_used}% used)"
            elif free_gb < 5.0:
                check.status = "degraded"
                check.message = f"{free_gb:.1f} GB free ({pct_used}% used)"
            else:
                check.status = "healthy"
                check.message = f"{free_gb:.1f} GB free"
            check.consecutive_failures = 0
        except Exception as exc:
            check.status = "degraded"
            check.message = str(exc)[:100]
        check.last_check = time.time()

    def _check_memory(self) -> None:
        name = "memory"
        check = self._status.checks.setdefault(name, HealthCheck(name=name))
        try:
            mem = psutil.virtual_memory()
            proc = psutil.Process()
            proc_mb = proc.memory_info().rss / (1024 ** 2)
            if mem.percent > 90:
                check.status = "critical"
                check.message = f"System RAM {mem.percent}% used, process {proc_mb:.0f} MB"
            elif mem.percent > 80:
                check.status = "degraded"
                check.message = f"System RAM {mem.percent}% used, process {proc_mb:.0f} MB"
            else:
                check.status = "healthy"
                check.message = f"RAM {mem.percent}% used, process {proc_mb:.0f} MB"
            check.consecutive_failures = 0
        except Exception as exc:
            check.status = "degraded"
            check.message = str(exc)[:100]
        check.last_check = time.time()

    def _persist(self) -> None:
        """Write health status to disk for dashboard consumption."""
        try:
            HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            HEALTH_FILE.write_text(
                json.dumps(self._status.to_dict(), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist health status: {}", exc)
