from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from data.binance_client import BinanceClientWrapper

INTERVAL_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
}


class _BinanceReplayBase:
    def __init__(self, interval: str, lookahead_minutes: int):
        if interval not in INTERVAL_MINUTES:
            raise ValueError(f"Unsupported replay interval: {interval}")
        self._client = BinanceClientWrapper()
        self._interval = interval
        self._interval_minutes = INTERVAL_MINUTES[interval]
        self._interval_ms = self._interval_minutes * 60 * 1000
        self._lookahead_minutes = lookahead_minutes
        self._cache: Dict[Tuple[str, str], List[List[Any]]] = {}

    def _load_day(self, symbol: str, timestamp: datetime) -> List[List[Any]]:
        day_start = datetime(timestamp.year, timestamp.month, timestamp.day, tzinfo=timezone.utc)
        day_key = (symbol, day_start.date().isoformat())
        cached = self._cache.get(day_key)
        if cached is not None:
            return cached

        buffer_minutes = self._interval_minutes * 2
        start_time = day_start - timedelta(minutes=buffer_minutes)
        end_time = day_start + timedelta(days=1, minutes=self._lookahead_minutes + buffer_minutes)
        total_minutes = int((end_time - start_time).total_seconds() // 60)
        limit = min(int(total_minutes / self._interval_minutes) + 5, 1500)

        klines = self._client.get_klines(
            symbol=symbol,
            interval=self._interval,
            limit=limit,
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000),
        )
        self._cache[day_key] = klines
        return klines

    def _resolve_index(self, klines: List[List[Any]], target_ms: int) -> Optional[int]:
        if not klines:
            return None
        previous_index: Optional[int] = None
        for index, row in enumerate(klines):
            open_time = int(row[0])
            if target_ms < open_time + self._interval_ms:
                return index
            previous_index = index
        return previous_index

    def _resolve_close(self, klines: List[List[Any]], target_ms: int) -> Optional[float]:
        index = self._resolve_index(klines, target_ms)
        if index is None:
            return None
        return float(klines[index][4])


class BinanceReplayPriceResolver(_BinanceReplayBase):
    def __call__(
        self,
        symbol: str,
        timestamp: datetime,
        lookahead_minutes: int,
    ) -> Optional[Tuple[float, float]]:
        klines = self._load_day(symbol, timestamp)
        if not klines:
            return None

        entry_ms = int(timestamp.timestamp() * 1000)
        future_ms = int((timestamp + timedelta(minutes=lookahead_minutes)).timestamp() * 1000)
        entry_price = self._resolve_close(klines, entry_ms)
        future_price = self._resolve_close(klines, future_ms)
        if entry_price is None or future_price is None:
            return None
        return float(entry_price), float(future_price)


class BinanceReplayTradePathResolver(_BinanceReplayBase):
    def __call__(
        self,
        symbol: str,
        timestamp: datetime,
        lookahead_minutes: int,
    ) -> Optional[Dict[str, Any]]:
        klines = self._load_day(symbol, timestamp)
        if not klines:
            return None

        entry_ms = int(timestamp.timestamp() * 1000)
        future_ms = int((timestamp + timedelta(minutes=lookahead_minutes)).timestamp() * 1000)

        entry_index = self._resolve_index(klines, entry_ms)
        future_index = self._resolve_index(klines, future_ms)
        if entry_index is None or future_index is None:
            return None

        entry_price = float(klines[entry_index][4])
        future_price = float(klines[future_index][4])
        start_index = min(entry_index + 1, len(klines))
        end_index = min(future_index + 1, len(klines))

        bars = [
            {
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in klines[start_index:end_index]
        ]

        return {
            "entry_price": entry_price,
            "future_price": future_price,
            "bars": bars,
            "entry_index": entry_index,
            "future_index": future_index,
        }