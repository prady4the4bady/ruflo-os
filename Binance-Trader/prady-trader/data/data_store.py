"""
PRADY TRADER — Redis-backed price cache / data store.
Stores OHLCV candles as JSON lists in Redis with TTL.
Falls back to in-memory dict when Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import pandas as pd

from config.settings import get_settings

logger = logging.getLogger("prady.data.data_store")

MAX_CANDLES = 1000  # keep last N candles per symbol+tf in memory/redis


def _is_local_service_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    return host in {"localhost", "127.0.0.1", "::1"}


class DataStore:
    """Redis-backed OHLCV cache with in-memory fallback."""

    def __init__(self) -> None:
        self._redis: Any = None
        self._memory: Dict[str, Any] = {}
        self._connect_redis()

    def _connect_redis(self) -> None:
        try:
            cfg = get_settings()
            if not cfg.redis_url:
                logger.info("No REDIS_URL configured — using in-memory store")
                return
            import redis as redis_lib
            self._redis = redis_lib.Redis.from_url(
                cfg.redis_url, decode_responses=True, socket_timeout=3
            )
            self._redis.ping()
            logger.info("DataStore connected to Redis")
        except Exception as exc:
            if getattr(cfg, "redis_url", "") and _is_local_service_url(cfg.redis_url):
                logger.info("Local Redis unavailable (%s) — using in-memory store", exc)
            else:
                logger.warning("Redis unavailable (%s) — using in-memory store", exc)
            self._redis = None

    @staticmethod
    def _key(symbol: str, interval: str) -> str:
        return f"ohlcv:{symbol}:{interval}"

    def push_candle(self, symbol: str, interval: str, candle: Dict[str, Any]) -> None:
        key = self._key(symbol, interval)
        if self._redis is not None:
            try:
                self._redis.rpush(key, json.dumps(candle))
                self._redis.ltrim(key, -MAX_CANDLES, -1)
                self._redis.expire(key, 86400)
                return
            except Exception as exc:
                logger.warning("Redis push failed: %s", exc)
        # Fallback: in-memory
        if key not in self._memory:
            self._memory[key] = []
        self._memory[key].append(candle)
        if len(self._memory[key]) > MAX_CANDLES:
            self._memory[key] = self._memory[key][-MAX_CANDLES:]

    def get_candles(self, symbol: str, interval: str, limit: int = 500) -> List[Dict[str, Any]]:
        key = self._key(symbol, interval)
        if self._redis is not None:
            try:
                raw = self._redis.lrange(key, -limit, -1)
                return [json.loads(r) for r in raw]
            except Exception as exc:
                logger.warning("Redis read failed: %s", exc)
        return self._memory.get(key, [])[-limit:]

    def get_dataframe(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        candles = self.get_candles(symbol, interval, limit)
        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(candles)
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        return df

    def set_value(self, key: str, value: str, ttl: int = 300) -> None:
        if self._redis is not None:
            try:
                self._redis.set(key, value, ex=ttl)
                return
            except Exception:
                pass
        self._memory[key] = value

    def get_value(self, key: str) -> Optional[str]:
        if self._redis is not None:
            try:
                return self._redis.get(key)
            except Exception:
                pass
        val = self._memory.get(key)
        if isinstance(val, str):
            return val
        return None

    def publish(self, channel: str, message: str) -> None:
        if self._redis is not None:
            try:
                self._redis.publish(channel, message)
            except Exception as exc:
                logger.warning("Redis publish failed: %s", exc)

    def clear_symbol(self, symbol: str) -> None:
        for interval in ["1m", "3m", "5m", "15m", "1h", "4h", "1d", "1w"]:
            key = self._key(symbol, interval)
            if self._redis is not None:
                try:
                    self._redis.delete(key)
                except Exception:
                    pass
            self._memory.pop(key, None)


_instance: Optional[DataStore] = None


def get_data_store() -> DataStore:
    global _instance
    if _instance is None:
        _instance = DataStore()
    return _instance
