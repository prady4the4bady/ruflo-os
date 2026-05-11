"""
PRADY TRADER — L2 order book depth streaming via Binance WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Optional

import websockets

from config.settings import get_settings

logger = logging.getLogger("prady.data.orderbook_feed")

BINANCE_WS_BASE = "wss://fstream.binance.com/ws"
BINANCE_WS_TESTNET = "wss://stream.binancefuture.com/ws"


class OrderBookSnapshot:
    """Immutable snapshot of the top-of-book."""

    __slots__ = ("symbol", "bids", "asks", "timestamp")

    def __init__(self, symbol: str, bids: List[List[float]], asks: List[List[float]], timestamp: int) -> None:
        self.symbol = symbol
        self.bids = bids
        self.asks = asks
        self.timestamp = timestamp

    @property
    def bid_volume(self) -> float:
        return sum(qty for _, qty in self.bids)

    @property
    def ask_volume(self) -> float:
        return sum(qty for _, qty in self.asks)

    @property
    def imbalance(self) -> float:
        total = self.bid_volume + self.ask_volume
        if total == 0:
            return 0.0
        return (self.bid_volume - self.ask_volume) / total

    @property
    def spread(self) -> float:
        if self.asks and self.bids:
            return self.asks[0][0] - self.bids[0][0]
        return 0.0

    @property
    def mid_price(self) -> float:
        if self.asks and self.bids:
            return (self.asks[0][0] + self.bids[0][0]) / 2.0
        return 0.0


class OrderBookFeed:
    """Streams L2 order book depth for all configured symbols."""

    def __init__(self, symbols: Optional[list] = None, depth: int = 20) -> None:
        cfg = get_settings()
        self._symbols = symbols or cfg.trading_pairs
        self._depth = depth
        self._base_url = BINANCE_WS_BASE
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._snapshots: Dict[str, OrderBookSnapshot] = {}

    def get_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        return self._snapshots.get(symbol)

    async def start(self) -> None:
        self._running = True
        logger.info("OrderBookFeed starting for %d symbols", len(self._symbols))
        task = asyncio.create_task(self._listen())
        self._tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        logger.info("OrderBookFeed stopped")

    def _stream_url(self) -> str:
        streams = [f"{s.lower()}@depth{self._depth}@100ms" for s in self._symbols]
        return f"{self._base_url}/{'/'.join(streams)}"

    async def _listen(self) -> None:
        while self._running:
            try:
                async with websockets.connect(
                    self._stream_url(), ping_interval=20, ping_timeout=10
                ) as ws:
                    logger.info("OrderBookFeed WebSocket connected")
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            self._process(msg)
                        except (json.JSONDecodeError, KeyError) as exc:
                            logger.warning("Bad orderbook message: %s", exc)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as exc:
                logger.warning("OrderBookFeed WS disconnected: %s — reconnecting 5s", exc)
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break

    def _process(self, msg: Dict) -> None:
        if "e" not in msg:
            return
        symbol = msg.get("s", "")
        bids = [[float(p), float(q)] for p, q in msg.get("b", [])]
        asks = [[float(p), float(q)] for p, q in msg.get("a", [])]
        ts = msg.get("E", 0)
        self._snapshots[symbol] = OrderBookSnapshot(symbol, bids, asks, ts)


_instance: Optional[OrderBookFeed] = None


def get_orderbook_feed() -> OrderBookFeed:
    global _instance
    if _instance is None:
        _instance = OrderBookFeed()
    return _instance
