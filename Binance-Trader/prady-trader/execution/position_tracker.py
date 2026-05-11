"""
PRADY TRADER — Position tracker.
Tracks all open positions, PnL, and provides portfolio overview.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

logger = logging.getLogger("prady.execution.position_tracker")


@dataclass
class Position:
    """Represents a single open position."""

    symbol: str
    direction: str                    # "LONG" or "SHORT"
    entry_price: Decimal
    quantity: Decimal
    leverage: int = 5
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    entry_time: float = field(default_factory=time.time)
    order_id: Optional[str] = None
    hedge_order_id: Optional[str] = None
    trade_id: Optional[int] = None
    paper: bool = False
    source: str = "internal"
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def notional_value(self) -> Decimal:
        return self.entry_price * self.quantity

    def unrealised_pnl(self, current_price: Decimal) -> Decimal:
        if self.direction == "LONG":
            return (current_price - self.entry_price) * self.quantity * self.leverage
        else:
            return (self.entry_price - current_price) * self.quantity * self.leverage

    def unrealised_pnl_pct(self, current_price: Decimal) -> Decimal:
        if self.notional_value == 0:
            return Decimal("0")
        return self.unrealised_pnl(current_price) / self.notional_value * Decimal("100")

    def should_stop_loss(self, current_price: Decimal) -> bool:
        if self.stop_loss is None:
            return False
        if self.direction == "LONG":
            return current_price <= self.stop_loss
        else:
            return current_price >= self.stop_loss

    def should_take_profit(self, current_price: Decimal) -> bool:
        if self.take_profit is None:
            return False
        if self.direction == "LONG":
            return current_price >= self.take_profit
        else:
            return current_price <= self.take_profit

    def holding_time_minutes(self) -> float:
        return (time.time() - self.entry_time) / 60.0


class PositionTracker:
    """Manages all open positions."""

    def __init__(self):
        self._positions: Dict[str, Position] = {}
        self._closed: List[Dict] = []
        self._total_realised_pnl: Decimal = Decimal("0")

    @property
    def open_positions(self) -> Dict[str, Position]:
        return self._positions.copy()

    @property
    def position_count(self) -> int:
        return len(self._positions)

    @property
    def total_realised_pnl(self) -> Decimal:
        return self._total_realised_pnl

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        leverage: int = 5,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_time: Optional[float] = None,
        order_id: Optional[str] = None,
        trade_id: Optional[int] = None,
        paper: bool = False,
        source: str = "internal",
        metadata: Optional[Dict[str, object]] = None,
    ) -> Position:
        """Record a new open position."""
        pos = Position(
            symbol=symbol,
            direction=direction,
            entry_price=Decimal(str(entry_price)),
            quantity=Decimal(str(quantity)),
            leverage=leverage,
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            take_profit=Decimal(str(take_profit)) if take_profit else None,
            entry_time=entry_time or time.time(),
            order_id=order_id,
            trade_id=trade_id,
            paper=paper,
            source=source,
            metadata=dict(metadata or {}),
        )
        self._positions[symbol] = pos
        logger.info(
            "Opened %s %s %.4f @ %.2f (SL=%.2f TP=%.2f)",
            direction, symbol, quantity, entry_price,
            stop_loss or 0, take_profit or 0,
        )
        return pos

    def sync_position(
        self,
        symbol: str,
        *,
        quantity: float,
        entry_price: float,
        leverage: int = 1,
        paper: bool = False,
        source: str = "exchange_sync",
    ) -> Position:
        """Adopt or refresh an externally-held spot position inside the tracker."""
        synced_qty = Decimal(str(quantity))
        synced_entry = Decimal(str(entry_price))
        if synced_qty <= 0:
            raise ValueError(f"Cannot sync non-positive quantity for {symbol}: {quantity}")

        existing = self._positions.get(symbol)
        if existing is not None:
            existing.quantity = synced_qty
            if existing.trade_id is None and synced_entry > 0:
                existing.entry_price = synced_entry
            existing.direction = "LONG"
            existing.leverage = leverage
            existing.paper = paper
            if existing.trade_id is None:
                existing.source = source
            logger.info(
                "Synced tracked %s position to %.6f units (source=%s)",
                symbol,
                synced_qty,
                existing.source,
            )
            return existing

        pos = Position(
            symbol=symbol,
            direction="LONG",
            entry_price=synced_entry,
            quantity=synced_qty,
            leverage=leverage,
            paper=paper,
            source=source,
        )
        self._positions[symbol] = pos
        logger.warning(
            "Adopted external %s inventory %.6f @ %.2f into tracker",
            symbol,
            synced_qty,
            synced_entry,
        )
        return pos

    def close_position(self, symbol: str, exit_price: float) -> Optional[Dict]:
        """Close a position and record realised PnL."""
        pos = self._positions.pop(symbol, None)
        if pos is None:
            logger.warning("No open position for %s", symbol)
            return None

        exit_p = Decimal(str(exit_price))
        pnl = pos.unrealised_pnl(exit_p)
        self._total_realised_pnl += pnl

        record = {
            "symbol": symbol,
            "direction": pos.direction,
            "entry_price": float(pos.entry_price),
            "exit_price": exit_price,
            "quantity": float(pos.quantity),
            "pnl": float(pnl),
            "holding_minutes": pos.holding_time_minutes(),
            "trade_id": pos.trade_id,
            "paper": pos.paper,
            "source": pos.source,
            "metadata": dict(pos.metadata or {}),
            "timestamp": time.time(),
        }
        self._closed.append(record)

        logger.info(
            "Closed %s %s: PnL=$%.2f (%.2f min hold)",
            pos.direction, symbol, pnl, record["holding_minutes"],
        )
        return record

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        return symbol in self._positions

    def get_open_positions(self) -> List[Dict]:
        """Compatibility helper for callers expecting serializable open positions."""
        return [
            {
                "symbol": pos.symbol,
                "direction": pos.direction,
                "entry_price": float(pos.entry_price),
                "quantity": float(pos.quantity),
                "leverage": pos.leverage,
                "stop_loss": float(pos.stop_loss) if pos.stop_loss is not None else None,
                "take_profit": float(pos.take_profit) if pos.take_profit is not None else None,
                "holding_minutes": pos.holding_time_minutes(),
                "paper": pos.paper,
                "trade_id": pos.trade_id,
                "source": pos.source,
                "metadata": dict(pos.metadata or {}),
            }
            for pos in self._positions.values()
        ]

    def get_portfolio_pnl(self, prices: Dict[str, float]) -> Decimal:
        """Get total unrealised PnL across all open positions."""
        total = Decimal("0")
        for symbol, pos in self._positions.items():
            if symbol in prices:
                total += pos.unrealised_pnl(Decimal(str(prices[symbol])))
        return total

    def get_closed_trades(self, n: int = 50) -> List[Dict]:
        """Return the last N closed trades."""
        return self._closed[-n:]

    def get_win_rate(self) -> float:
        """Calculate win rate from closed trades."""
        if not self._closed:
            return 0.0
        wins = sum(1 for t in self._closed if t["pnl"] > 0)
        return wins / len(self._closed)

    def get_stats(self) -> Dict:
        """Return portfolio statistics."""
        if not self._closed:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "open_positions": self.position_count,
            }

        pnls = [t["pnl"] for t in self._closed]
        return {
            "total_trades": len(self._closed),
            "win_rate": self.get_win_rate(),
            "total_pnl": float(self._total_realised_pnl),
            "avg_pnl": sum(pnls) / len(pnls),
            "best_trade": max(pnls),
            "worst_trade": min(pnls),
            "open_positions": self.position_count,
        }
