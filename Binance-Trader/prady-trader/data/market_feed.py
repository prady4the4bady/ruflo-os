"""
PRADY TRADER — Real-time OHLCV market feed via Binance WebSocket.
Streams kline data and pushes into Redis-backed DataStore.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Optional

import websockets

from config.settings import get_settings
from config.constants import TIMEFRAMES
from data.data_store import get_data_store

logger = logging.getLogger("prady.data.market_feed")

BINANCE_WS_BASE = "wss://fstream.binance.com/ws"
BINANCE_WS_TESTNET = "wss://stream.binancefuture.com/ws"


class MarketFeed:
    """Connects to Binance Futures kline WebSocket streams and stores OHLCV."""

    def __init__(self, symbols: Optional[list] = None, timeframes: Optional[list] = None) -> None:
        cfg = get_settings()
        self._symbols = symbols or cfg.trading_pairs
        self._timeframes = timeframes or TIMEFRAMES
        self._base_url = BINANCE_WS_BASE
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._store = get_data_store()

    def _build_stream_url(self) -> str:
        streams = []
        for sym in self._symbols:
            for tf in self._timeframes:
                streams.append(f"{sym.lower()}@kline_{tf}")
        combined = "/".join(streams)
        return f"{self._base_url}/{combined}"

    async def start(self) -> None:
        self._running = True
        logger.info(
            "MarketFeed starting for %d symbols × %d timeframes",
            len(self._symbols),
            len(self._timeframes),
        )
        task = asyncio.create_task(self._listen())
        self._tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        logger.info("MarketFeed stopped")

    async def _listen(self) -> None:
        while self._running:
            try:
                async with websockets.connect(
                    self._build_stream_url(), ping_interval=20, ping_timeout=10
                ) as ws:
                    logger.info("MarketFeed WebSocket connected")
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            await self._process_kline(msg)
                        except (json.JSONDecodeError, KeyError) as exc:
                            logger.warning("Bad kline message: %s", exc)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as exc:
                logger.warning("MarketFeed WS disconnected: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break

    async def _process_kline(self, msg: Dict) -> None:
        if "e" not in msg or msg["e"] != "kline":
            return
        k = msg["k"]
        symbol = k["s"]
        interval = k["i"]
        candle = {
            "timestamp": k["t"],
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "closed": k["x"],
        }
        self._store.push_candle(symbol, interval, candle)
        if candle["closed"]:
            logger.debug(
                "Closed candle %s %s O=%.2f H=%.2f L=%.2f C=%.2f V=%.2f",
                symbol, interval,
                candle["open"], candle["high"], candle["low"],
                candle["close"], candle["volume"],
            )


_instance: Optional[MarketFeed] = None


def get_market_feed() -> MarketFeed:
    global _instance
    if _instance is None:
        _instance = MarketFeed()
    return _instance
