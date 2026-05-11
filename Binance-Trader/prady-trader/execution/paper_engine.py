"""
PRADY TRADER — Paper trading engine.
Simulates order execution, tracks positions and PnL without real money.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional

logger = logging.getLogger("prady.execution.paper_engine")


class PaperOrder:
    """Simulated order."""

    def __init__(
        self,
        order_id: int,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        order_type: str = "MARKET",
        stop_price: Optional[Decimal] = None,
    ):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.order_type = order_type
        self.stop_price = stop_price
        self.filled = order_type == "MARKET"
        self.timestamp = time.time()


class PaperPosition:
    """Simulated position."""

    def __init__(self, symbol: str, side: str, quantity: Decimal, entry_price: Decimal, leverage: int = 5):
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.entry_price = entry_price
        self.leverage = leverage
        self.entry_time = time.time()

    def unrealised_pnl(self, current_price: Decimal) -> Decimal:
        if self.side == "BUY":
            return (current_price - self.entry_price) * self.quantity * self.leverage
        else:
            return (self.entry_price - current_price) * self.quantity * self.leverage


class PaperTradingEngine:
    """Full paper trading simulator."""

    def __init__(self, initial_balance: Decimal = Decimal("10000")):
        self._balance = initial_balance
        self._initial_balance = initial_balance
        self._positions: Dict[str, PaperPosition] = {}
        self._orders: List[PaperOrder] = []
        self._pending_orders: List[PaperOrder] = []
        self._trade_history: List[Dict] = []
        self._order_counter = 0

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def positions(self) -> Dict[str, PaperPosition]:
        return self._positions.copy()

    def _next_order_id(self) -> int:
        self._order_counter += 1
        return self._order_counter

    def _cancel_symbol_pending_orders(self, symbol: str) -> int:
        before = len(self._pending_orders)
        self._pending_orders = [
            order for order in self._pending_orders
            if order.symbol != symbol
        ]
        return before - len(self._pending_orders)

    def place_market_order(
        self, symbol: str, side: str, quantity: float, current_price: float
    ) -> Dict:
        """Simulate market order execution."""
        existing = self._positions.get(symbol)
        if existing and existing.side == side:
            logger.info(
                "[PAPER] Ignored %s %s %.4f @ %.2f — %s position already open",
                side,
                symbol,
                quantity,
                current_price,
                existing.side,
            )
            return {
                "orderId": None,
                "status": "IGNORED",
                "symbol": symbol,
                "side": side,
                "quantity": float(existing.quantity),
                "price": float(existing.entry_price),
            }

        qty = Decimal(str(quantity))
        price = Decimal(str(current_price))
        order_id = self._next_order_id()

        order = PaperOrder(order_id, symbol, side, qty, price, "MARKET")
        self._orders.append(order)

        # Check if closing existing position
        if existing and (
            (existing.side == "BUY" and side == "SELL") or
            (existing.side == "SELL" and side == "BUY")
        ):
            pnl = existing.unrealised_pnl(price)
            self._balance += pnl
            self._trade_history.append({
                "symbol": symbol,
                "direction": "LONG" if existing.side == "BUY" else "SHORT",
                "entry_price": float(existing.entry_price),
                "exit_price": float(price),
                "quantity": float(existing.quantity),
                "pnl": float(pnl),
                "holding_minutes": (time.time() - existing.entry_time) / 60.0,
                "timestamp": time.time(),
            })
            del self._positions[symbol]
            self._cancel_symbol_pending_orders(symbol)
            logger.info("[PAPER] Closed %s: PnL=$%.2f", symbol, pnl)
        else:
            # Open new position
            self._cancel_symbol_pending_orders(symbol)
            pos = PaperPosition(symbol, side, qty, price)
            self._positions[symbol] = pos
            logger.info("[PAPER] Opened %s %s %.4f @ %.2f", side, symbol, qty, price)

        return {
            "orderId": order_id,
            "status": "FILLED",
            "symbol": symbol,
            "side": side,
            "quantity": float(qty),
            "price": float(price),
        }

    def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> Dict:
        """Place a simulated limit order (pending)."""
        qty = Decimal(str(quantity))
        limit_price = Decimal(str(price))
        order_id = self._next_order_id()

        order = PaperOrder(order_id, symbol, side, qty, limit_price, "LIMIT")
        self._pending_orders.append(order)
        self._orders.append(order)

        return {
            "orderId": order_id,
            "status": "NEW",
            "symbol": symbol,
            "type": "LIMIT",
        }

    def place_stop_market(
        self, symbol: str, side: str, quantity: float, stop_price: float
    ) -> Dict:
        """Place a simulated stop-market order."""
        qty = Decimal(str(quantity))
        stop = Decimal(str(stop_price))
        order_id = self._next_order_id()

        order = PaperOrder(order_id, symbol, side, qty, stop, "STOP_MARKET", stop)
        self._pending_orders.append(order)
        self._orders.append(order)

        return {
            "orderId": order_id,
            "status": "NEW",
            "symbol": symbol,
            "type": "STOP_MARKET",
        }

    def check_pending_orders(self, symbol: str, current_price: float):
        """Check if any pending orders should be triggered at the current price."""
        price = Decimal(str(current_price))
        triggered = []

        for order in self._pending_orders:
            if order.symbol != symbol or order.filled:
                continue

            if order.order_type == "LIMIT":
                if order.side == "BUY" and price <= order.price:
                    triggered.append(order)
                elif order.side == "SELL" and price >= order.price:
                    triggered.append(order)

            elif order.order_type == "STOP_MARKET" and order.stop_price:
                if order.side == "SELL" and price <= order.stop_price:
                    triggered.append(order)
                elif order.side == "BUY" and price >= order.stop_price:
                    triggered.append(order)

        for order in triggered:
            if order not in self._pending_orders:
                continue
            order.filled = True
            self._pending_orders.remove(order)
            self.place_market_order(symbol, order.side, float(order.quantity), current_price)

    def cancel_all_orders(self, symbol: str):
        """Cancel all pending orders for a symbol."""
        cancelled = self._cancel_symbol_pending_orders(symbol)
        return {"symbol": symbol, "cancelled": cancelled}

    def get_equity(self, prices: Dict[str, float]) -> Decimal:
        """Calculate total equity (balance + unrealised PnL)."""
        equity = self._balance
        for symbol, pos in self._positions.items():
            if symbol in prices:
                equity += pos.unrealised_pnl(Decimal(str(prices[symbol])))
        return equity

    def get_stats(self) -> Dict:
        """Get paper trading statistics."""
        if not self._trade_history:
            return {
                "balance": float(self._balance),
                "initial_balance": float(self._initial_balance),
                "total_return_pct": 0.0,
                "total_trades": 0,
                "win_rate": 0.0,
            }

        pnls = [t["pnl"] for t in self._trade_history]
        wins = sum(1 for p in pnls if p > 0)
        return {
            "balance": float(self._balance),
            "initial_balance": float(self._initial_balance),
            "total_return_pct": float((self._balance - self._initial_balance) / self._initial_balance * 100),
            "total_trades": len(self._trade_history),
            "win_rate": wins / len(pnls) if pnls else 0.0,
            "total_pnl": sum(pnls),
            "avg_pnl": sum(pnls) / len(pnls),
            "best_trade": max(pnls),
            "worst_trade": min(pnls),
            "open_positions": len(self._positions),
        }

    def get_trade_history(self, n: int = 50) -> List[Dict]:
        """Return last N closed trades."""
        return self._trade_history[-n:]
