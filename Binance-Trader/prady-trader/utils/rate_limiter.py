"""
PRADY TRADER — Token-bucket rate limiter per API provider.
Prevents 429s by throttling outgoing requests.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict

from loguru import logger


@dataclass
class _Bucket:
    """Token bucket for a single provider."""
    max_tokens: float
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)
    daily_limit: int = 0
    daily_used: int = 0
    daily_reset: float = field(default_factory=time.time)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        # Daily counter reset
        if self.daily_limit > 0 and time.time() - self.daily_reset >= 86400:
            self.daily_used = 0
            self.daily_reset = time.time()

    def can_acquire(self) -> bool:
        self._refill()
        if self.daily_limit > 0 and self.daily_used >= self.daily_limit:
            return False
        return self.tokens >= 1.0

    def acquire_nowait(self) -> bool:
        self._refill()
        if self.daily_limit > 0 and self.daily_used >= self.daily_limit:
            return False
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            self.daily_used += 1
            return True
        return False

    def wait_time(self) -> float:
        self._refill()
        if self.tokens >= 1.0:
            return 0.0
        deficit = 1.0 - self.tokens
        return deficit / self.refill_rate if self.refill_rate > 0 else 1.0


# ── Default provider limits ─────────────────────────────────────────
PROVIDER_LIMITS: Dict[str, dict] = {
    "binance":       {"max_tokens": 20, "refill_rate": 10.0, "daily_limit": 0},
    "coingecko":     {"max_tokens": 5,  "refill_rate": 0.5,  "daily_limit": 500},
    "newsapi":       {"max_tokens": 3,  "refill_rate": 0.1,  "daily_limit": 100},
    "newsdata":      {"max_tokens": 3,  "refill_rate": 0.1,  "daily_limit": 200},
    "cryptocompare": {"max_tokens": 5,  "refill_rate": 0.5,  "daily_limit": 1000},
    "coinapi":       {"max_tokens": 3,  "refill_rate": 0.05, "daily_limit": 100},
    "alternative":   {"max_tokens": 3,  "refill_rate": 0.1,  "daily_limit": 500},
    "reddit":        {"max_tokens": 5,  "refill_rate": 1.0,  "daily_limit": 600},
    "blockchain":    {"max_tokens": 5,  "refill_rate": 0.5,  "daily_limit": 500},
    "freecrypto":    {"max_tokens": 5,  "refill_rate": 0.5,  "daily_limit": 3000},
    "default":       {"max_tokens": 5,  "refill_rate": 1.0,  "daily_limit": 0},
}


class RateLimiter:
    """Async-compatible token-bucket rate limiter per provider."""

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()
        self._init_buckets()

    def _init_buckets(self) -> None:
        for name, cfg in PROVIDER_LIMITS.items():
            self._buckets[name] = _Bucket(
                max_tokens=cfg["max_tokens"],
                refill_rate=cfg["refill_rate"],
                tokens=cfg["max_tokens"],
                daily_limit=cfg.get("daily_limit", 0),
            )

    def _get_bucket(self, provider: str) -> _Bucket:
        provider = provider.lower()
        if provider not in self._buckets:
            default = PROVIDER_LIMITS["default"]
            self._buckets[provider] = _Bucket(
                max_tokens=default["max_tokens"],
                refill_rate=default["refill_rate"],
                tokens=default["max_tokens"],
                daily_limit=default.get("daily_limit", 0),
            )
        return self._buckets[provider]

    async def acquire(self, provider: str) -> None:
        """Wait until a token is available, then consume it."""
        bucket = self._get_bucket(provider)
        while True:
            async with self._lock:
                if bucket.acquire_nowait():
                    return
                wait = bucket.wait_time()

            if bucket.daily_limit > 0 and bucket.daily_used >= bucket.daily_limit:
                logger.warning(
                    "Rate limiter: {} daily limit reached ({}/{})",
                    provider, bucket.daily_used, bucket.daily_limit,
                )
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(max(wait, 0.05))

    def try_acquire(self, provider: str) -> bool:
        """Non-blocking attempt to acquire a token."""
        bucket = self._get_bucket(provider)
        return bucket.acquire_nowait()

    def get_stats(self) -> Dict[str, dict]:
        """Return usage stats per provider."""
        stats = {}
        for name, bucket in self._buckets.items():
            bucket._refill()
            stats[name] = {
                "tokens_available": round(bucket.tokens, 1),
                "daily_used": bucket.daily_used,
                "daily_limit": bucket.daily_limit,
            }
        return stats


# ── Singleton ────────────────────────────────────────────────────────
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
