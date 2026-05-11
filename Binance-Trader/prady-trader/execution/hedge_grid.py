"""
PRADY TRADER — Hedge grid manager.
Zero-drawdown hedge grid strategy implementation.
Main position + hedge counter-position with harvest cycling.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from config.constants import (
    DEFAULT_HEDGE_RATIO,
    DEFAULT_HARVEST_THRESHOLD,
    DEFAULT_MAX_HOLD_MINUTES,
    DEFAULT_DAILY_PROFIT_TARGET,
)
from config.settings import get_settings
from data.binance_client import get_binance_client

logger = logging.getLogger("prady.execution.hedge_grid")


@dataclass
class GridLevel:
    """A single level in the hedge grid."""

    price: Decimal
    quantity: Decimal
    side: str             # "BUY" or "SELL"
    filled: bool = False
    order_id: Optional[str] = None
    pnl: Decimal = Decimal("0")


@dataclass
class HedgeGridState:
    """State for one symbol's hedge grid."""

    symbol: str
    direction: str                     # Primary direction: "LONG" or "SHORT"
    entry_price: Decimal = Decimal("0")
    main_quantity: Decimal = Decimal("0")
    hedge_quantity: Decimal = Decimal("0")
    grid_levels: List[GridLevel] = field(default_factory=list)
    total_harvested: Decimal = Decimal("0")
    cycles: int = 0
    start_time: float = field(default_factory=time.time)
    active: bool = True


class HedgeGridManager:
    """
    Manages hedge grid positions.
    The grid creates a primary position and a smaller hedge in the opposite direction.
    When price moves favorably, it harvests profits; when adverse, the hedge limits loss.
    """

    def __init__(self):
        self.settings = get_settings()
        self.client = get_binance_client()
        self._grids: Dict[str, HedgeGridState] = {}
        self._daily_profit: Decimal = Decimal("0")

    @property
    def active_grids(self) -> Dict[str, HedgeGridState]:
        return {s: g for s, g in self._grids.items() if g.active}

    def reset_daily(self):
        """Reset daily profit counter."""
        self._daily_profit = Decimal("0")

    async def setup_grid(
        self,
        symbol: str,
        direction: str,
        entry_price: Decimal,
        main_quantity: Decimal,
        num_levels: int = 5,
    ) -> HedgeGridState:
        """
        Create a new hedge grid for a position.
        Places main position + hedge counter-position grid levels.
        """
        hedge_ratio = self.settings.hedge_ratio
        harvest_threshold = self.settings.harvest_threshold
        hedge_qty = main_quantity * hedge_ratio

        # Create grid levels spread around entry price
        grid_spacing = entry_price * harvest_threshold
        levels: List[GridLevel] = []

        for i in range(1, num_levels + 1):
            if direction == "LONG":
                # Hedge levels below entry (sells if price drops)
                level_price = entry_price - (grid_spacing * i)
                levels.append(GridLevel(
                    price=level_price,
                    quantity=hedge_qty / num_levels,
                    side="SELL",
                ))
                # Take-profit levels above entry
                tp_price = entry_price + (grid_spacing * i)
                levels.append(GridLevel(
                    price=tp_price,
                    quantity=main_quantity / num_levels,
                    side="SELL",
                ))
            else:
                # Hedge levels above entry (buys if price rises)
                level_price = entry_price + (grid_spacing * i)
                levels.append(GridLevel(
                    price=level_price,
                    quantity=hedge_qty / num_levels,
                    side="BUY",
                ))
                # Take-profit levels below entry
                tp_price = entry_price - (grid_spacing * i)
                levels.append(GridLevel(
                    price=tp_price,
                    quantity=main_quantity / num_levels,
                    side="BUY",
                ))

        state = HedgeGridState(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            main_quantity=main_quantity,
            hedge_quantity=hedge_qty,
            grid_levels=levels,
        )

        # Place grid orders
        if not self.settings.is_paper:
            for level in levels:
                try:
                    order = await self.client.place_limit_order(
                        symbol,
                        level.side,
                        float(level.quantity.quantize(Decimal("0.001"))),
                        float(level.price.quantize(Decimal("0.01"))),
                    )
                    level.order_id = order.get("orderId")
                except Exception as exc:
                    logger.warning("Failed to place grid level @ %.2f: %s", level.price, exc)

        self._grids[symbol] = state
        logger.info(
            "Hedge grid setup for %s: direction=%s, main=%.4f, hedge=%.4f, levels=%d",
            symbol, direction, main_quantity, hedge_qty, len(levels),
        )
        return state

    async def check_and_harvest(self, symbol: str, current_price: Decimal) -> Decimal:
        """
        Check if any grid levels have been hit and harvest profits.
        Returns the harvested PnL.
        """
        state = self._grids.get(symbol)
        if state is None or not state.active:
            return Decimal("0")

        harvested = Decimal("0")

        for level in state.grid_levels:
            if level.filled:
                continue

            hit = False
            if level.side == "SELL" and current_price >= level.price:
                hit = True
            elif level.side == "BUY" and current_price <= level.price:
                hit = True

            if hit:
                level.filled = True
                # Calculate PnL for this level
                if state.direction == "LONG":
                    if level.side == "SELL" and level.price > state.entry_price:
                        pnl = (level.price - state.entry_price) * level.quantity
                    else:
                        pnl = Decimal("0")   # hedge activation, not profit
                else:
                    if level.side == "BUY" and level.price < state.entry_price:
                        pnl = (state.entry_price - level.price) * level.quantity
                    else:
                        pnl = Decimal("0")

                level.pnl = pnl
                harvested += pnl
                logger.info(
                    "Grid level hit: %s @ %.2f → PnL=$%.4f",
                    level.side, level.price, pnl,
                )

        if harvested > 0:
            state.total_harvested += harvested
            state.cycles += 1
            self._daily_profit += harvested

        return harvested

    async def check_time_exit(self, symbol: str) -> bool:
        """Check if grid has exceeded max hold time."""
        state = self._grids.get(symbol)
        if state is None:
            return False
        holding_min = (time.time() - state.start_time) / 60.0
        return holding_min >= self.settings.max_hold_minutes

    def check_daily_target(self) -> bool:
        """Check if daily profit target has been reached."""
        return self._daily_profit >= self.settings.daily_profit_target

    async def close_grid(self, symbol: str) -> Dict:
        """Close all grid orders and the grid state."""
        state = self._grids.get(symbol)
        if state is None:
            return {"status": "no_grid", "symbol": symbol}

        if not self.settings.is_paper:
            try:
                await self.client.cancel_all_orders(symbol)
            except Exception as exc:
                logger.warning("Failed cancelling grid orders for %s: %s", symbol, exc)

        state.active = False
        result = {
            "status": "closed",
            "symbol": symbol,
            "total_harvested": float(state.total_harvested),
            "cycles": state.cycles,
            "holding_minutes": (time.time() - state.start_time) / 60.0,
        }
        logger.info("Grid closed for %s: harvested=$%.4f over %d cycles", symbol, state.total_harvested, state.cycles)
        return result

    def get_grid_status(self, symbol: str) -> Optional[Dict]:
        """Get current grid status for dashboard display."""
        state = self._grids.get(symbol)
        if state is None:
            return None

        filled_levels = sum(1 for l in state.grid_levels if l.filled)
        return {
            "symbol": symbol,
            "direction": state.direction,
            "entry_price": float(state.entry_price),
            "main_qty": float(state.main_quantity),
            "hedge_qty": float(state.hedge_quantity),
            "total_levels": len(state.grid_levels),
            "filled_levels": filled_levels,
            "total_harvested": float(state.total_harvested),
            "cycles": state.cycles,
            "active": state.active,
            "holding_minutes": (time.time() - state.start_time) / 60.0,
        }

    async def recycle_grid(self, symbol: str, current_price: Decimal) -> bool:
        """Reset filled grid levels around the current price for another harvest cycle.
        Returns True if grid was recycled.
        """
        state = self._grids.get(symbol)
        if state is None or not state.active:
            return False

        filled = [l for l in state.grid_levels if l.filled]
        if not filled:
            return False

        harvest_threshold = self.settings.harvest_threshold
        grid_spacing = current_price * harvest_threshold
        num_levels = len(state.grid_levels) // 2  # half hedge, half TP

        # Rebuild levels around current price
        new_levels: List[GridLevel] = []
        hedge_qty = state.hedge_quantity

        for i in range(1, num_levels + 1):
            if state.direction == "LONG":
                new_levels.append(GridLevel(
                    price=current_price - (grid_spacing * i),
                    quantity=hedge_qty / num_levels,
                    side="SELL",
                ))
                new_levels.append(GridLevel(
                    price=current_price + (grid_spacing * i),
                    quantity=state.main_quantity / num_levels,
                    side="SELL",
                ))
            else:
                new_levels.append(GridLevel(
                    price=current_price + (grid_spacing * i),
                    quantity=hedge_qty / num_levels,
                    side="BUY",
                ))
                new_levels.append(GridLevel(
                    price=current_price - (grid_spacing * i),
                    quantity=state.main_quantity / num_levels,
                    side="BUY",
                ))

        state.grid_levels = new_levels
        state.entry_price = current_price
        logger.info(
            "Grid recycled for %s around price %.2f (%d filled levels reset)",
            symbol, current_price, len(filled),
        )
        return True

    @staticmethod
    def dynamic_hedge_ratio(volatility_pct: float) -> Decimal:
        """Compute hedge ratio based on recent volatility.
        Higher volatility → larger hedge. Range [0.2, 0.6].
        """
        ratio = 0.3 + (volatility_pct * 2.0)
        ratio = max(0.2, min(0.6, ratio))
        return Decimal(str(round(ratio, 2)))
