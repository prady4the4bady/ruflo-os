"""
PRADY TRADER — Common utility helpers.
Decimal math, rate limiting, retry helpers, time formatting.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("prady.utils.helpers")


# ── Decimal helpers ──────────────────────────────────────────

def to_decimal(value: Any) -> Decimal:
    """Safely convert any numeric value to Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def round_price(price: Decimal, tick_size: Decimal = Decimal("0.01")) -> Decimal:
    """Round price to tick size."""
    return (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick_size


def round_quantity(qty: Decimal, step_size: Decimal = Decimal("0.001")) -> Decimal:
    """Round quantity to step size."""
    return (qty / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size


def pct_change(old: Decimal, new: Decimal) -> Decimal:
    """Calculate percentage change from old to new."""
    if old == 0:
        return Decimal("0")
    return ((new - old) / old) * Decimal("100")


# ── Rate limiter ─────────────────────────────────────────────

class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, max_calls: int = 10, period: float = 1.0):
        self._max = max_calls
        self._period = period
        self._calls: list[float] = []

    async def acquire(self):
        """Wait until a call is allowed."""
        now = time.time()
        self._calls = [t for t in self._calls if now - t < self._period]

        while len(self._calls) >= self._max:
            sleep_time = self._calls[0] + self._period - now
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self._period]

        self._calls.append(time.time())


# ── Time formatting ──────────────────────────────────────────

def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    elif seconds < 86400:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"
    else:
        d = int(seconds // 86400)
        h = int((seconds % 86400) // 3600)
        return f"{d}d {h}h"


def format_pnl(pnl: float) -> str:
    """Format PnL with color indicator."""
    if pnl >= 0:
        return f"+${pnl:,.2f}"
    return f"-${abs(pnl):,.2f}"


def format_pct(pct: float) -> str:
    """Format percentage."""
    return f"{pct:+.2f}%"


# ── Hashing ──────────────────────────────────────────────────

def hash_config(config: Dict) -> str:
    """Generate a hash of config dict for change detection."""
    raw = str(sorted(config.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Async retry helper ───────────────────────────────────────

def async_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for async functions with exponential backoff retry."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        logger.warning(
                            "%s attempt %d/%d failed: %s — retrying in %.1fs",
                            func.__name__, attempt + 1, max_retries + 1, exc, current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_exc
        return wrapper
    return decorator


# ── Chunk helper ─────────────────────────────────────────────

def chunk_list(lst: list, size: int) -> list[list]:
    """Split a list into chunks of the given size."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]
