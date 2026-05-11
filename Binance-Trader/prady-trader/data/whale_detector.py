"""
PRADY TRADER — Whale trade detection via Binance aggTrade stream.

Uses the FREE Binance Futures WebSocket aggTrade stream to detect
large trades that may indicate institutional/whale activity.
Also provides a REST fallback via /fapi/v1/aggTrades endpoint.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import time
from collections import deque
from typing import Dict, List, Optional

import requests

from config.settings import get_settings

logger = logging.getLogger("prady.data.whale_detector")

FAPI_BASE = "https://fapi.binance.com"
FAPI_TESTNET = "https://testnet.binancefuture.com"
WS_BASE = "wss://fstream.binance.com/ws"
WS_TESTNET = "wss://stream.binancefuture.com/ws"

# Default threshold in USDT to qualify as a "whale" trade
DEFAULT_WHALE_THRESHOLD = 100_000.0


class WhaleTrade:
    """A single large trade detection."""

    __slots__ = ("symbol", "price", "qty", "usdt_value", "is_buyer_maker", "timestamp")

    def __init__(
        self,
        symbol: str,
        price: float,
        qty: float,
        usdt_value: float,
        is_buyer_maker: bool,
        timestamp: int,
    ) -> None:
        self.symbol = symbol
        self.price = price
        self.qty = qty
        self.usdt_value = usdt_value
        self.is_buyer_maker = is_buyer_maker
        self.timestamp = timestamp

    @property
    def side(self) -> str:
        return "SELL" if self.is_buyer_maker else "BUY"

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "qty": self.qty,
            "usdt_value": self.usdt_value,
            "side": self.side,
            "timestamp": self.timestamp,
        }


class WhaleDetector:
    """
    Detects whale trades using Binance aggTrade WebSocket stream.
    Falls back to REST polling when WebSocket is unavailable.
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        threshold_usdt: float = DEFAULT_WHALE_THRESHOLD,
        window_seconds: int = 300,
    ) -> None:
        cfg = get_settings()
        self._symbols = symbols or cfg.trading_pairs
        self._threshold = threshold_usdt
        self._window = window_seconds
        self._base_url = FAPI_BASE
        self._ws_base = WS_BASE

        # Recent whale trades per symbol (capped deque)
        self._whale_trades: Dict[str, deque] = {
            s: deque(maxlen=200) for s in self._symbols
        }

        self._running = False
        self._tasks: list[asyncio.Task] = []

    # ── REST fallback (no WebSocket needed) ──────────────────────────

    def fetch_recent_whale_trades(
        self, symbol: str, limit: int = 1000
    ) -> List[WhaleTrade]:
        """
        Fetch recent aggTrades via REST and filter for whale-sized trades.
        FREE endpoint — no API key needed.
        """
        url = f"{self._base_url}/fapi/v1/aggTrades"
        params = {"symbol": symbol, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            trades = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch aggTrades for %s: %s", symbol, exc)
            return []

        whales: List[WhaleTrade] = []
        for t in trades:
            price = float(t["p"])
            qty = float(t["q"])
            usdt_value = price * qty
            if usdt_value >= self._threshold:
                wt = WhaleTrade(
                    symbol=symbol,
                    price=price,
                    qty=qty,
                    usdt_value=usdt_value,
                    is_buyer_maker=t["m"],
                    timestamp=t["T"],
                )
                whales.append(wt)
        return whales

    def get_whale_summary(self, symbol: str) -> Dict:
        """
        Return a summary of recent whale activity for a symbol.
        Uses REST endpoint — works without WebSocket.
        """
        whales = self.fetch_recent_whale_trades(symbol)
        if not whales:
            return {
                "symbol": symbol,
                "whale_count": 0,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "net_flow": 0.0,
                "bias": "NEUTRAL",
            }

        buy_vol = sum(w.usdt_value for w in whales if w.side == "BUY")
        sell_vol = sum(w.usdt_value for w in whales if w.side == "SELL")
        net = buy_vol - sell_vol
        total = buy_vol + sell_vol

        if total > 0 and abs(net) / total > 0.2:
            bias = "LONG" if net > 0 else "SHORT"
        else:
            bias = "NEUTRAL"

        return {
            "symbol": symbol,
            "whale_count": len(whales),
            "buy_volume": round(buy_vol, 2),
            "sell_volume": round(sell_vol, 2),
            "net_flow": round(net, 2),
            "bias": bias,
        }

    # ── WebSocket streaming ──────────────────────────────────────────

    async def start(self) -> None:
        """Start WebSocket aggTrade stream for whale detection."""
        if importlib.util.find_spec("websockets") is None:
            logger.warning("websockets not installed — whale detector using REST only")
            return

        self._running = True
        logger.info(
            "WhaleDetector starting for %d symbols (threshold=$%.0f)",
            len(self._symbols),
            self._threshold,
        )
        task = asyncio.create_task(self._listen())
        self._tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        logger.info("WhaleDetector stopped")

    async def _listen(self) -> None:
        import websockets

        streams = "/".join(f"{s.lower()}@aggTrade" for s in self._symbols)
        url = f"{self._ws_base}/{streams}"

        while self._running:
            try:
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=10
                ) as ws:
                    logger.info("WhaleDetector WebSocket connected")
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            self._process_trade(msg)
                        except (json.JSONDecodeError, KeyError) as exc:
                            logger.debug("Bad aggTrade message: %s", exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "WhaleDetector WS disconnected: %s — reconnecting in 5s", exc
                )
                await asyncio.sleep(5)

    def _process_trade(self, msg: Dict) -> None:
        """Process a single aggTrade message, store if whale-sized."""
        if msg.get("e") != "aggTrade":
            return

        symbol = msg["s"]
        price = float(msg["p"])
        qty = float(msg["q"])
        usdt_value = price * qty

        if usdt_value < self._threshold:
            return

        wt = WhaleTrade(
            symbol=symbol,
            price=price,
            qty=qty,
            usdt_value=usdt_value,
            is_buyer_maker=msg["m"],
            timestamp=msg["T"],
        )

        if symbol not in self._whale_trades:
            self._whale_trades[symbol] = deque(maxlen=200)
        self._whale_trades[symbol].append(wt)

        logger.info(
            "🐋 Whale %s on %s: %.2f %s @ $%.2f ($%.0f)",
            wt.side,
            symbol,
            qty,
            symbol,
            price,
            usdt_value,
        )

    def get_streaming_summary(self, symbol: str) -> Dict:
        """Summary from WebSocket-collected whale trades within the time window."""
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - (self._window * 1000)

        trades = [
            w
            for w in self._whale_trades.get(symbol, [])
            if w.timestamp >= cutoff
        ]

        if not trades:
            return {
                "symbol": symbol,
                "whale_count": 0,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "net_flow": 0.0,
                "bias": "NEUTRAL",
            }

        buy_vol = sum(w.usdt_value for w in trades if w.side == "BUY")
        sell_vol = sum(w.usdt_value for w in trades if w.side == "SELL")
        net = buy_vol - sell_vol
        total = buy_vol + sell_vol

        if total > 0 and abs(net) / total > 0.2:
            bias = "LONG" if net > 0 else "SHORT"
        else:
            bias = "NEUTRAL"

        return {
            "symbol": symbol,
            "whale_count": len(trades),
            "buy_volume": round(buy_vol, 2),
            "sell_volume": round(sell_vol, 2),
            "net_flow": round(net, 2),
            "bias": bias,
        }
