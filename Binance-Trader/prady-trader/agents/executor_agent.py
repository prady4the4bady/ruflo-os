"""
PRADY TRADER — Executor Agent.
Translates council decisions into Binance spot orders for testnet or live.
Handles position sizing, order placement, and protective exits for spot longs.
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional

from config.settings import get_settings
from config.constants import (
    MAX_POSITION_PCT,
    KELLY_ROLLING_WINDOW,
    DEFAULT_HEDGE_RATIO,
    DEFAULT_HARVEST_THRESHOLD,
    FORCE_SIGNAL_EXIT_CONFIDENCE,
    FORCE_SIGNAL_EXIT_LOSS_PCT,
)
from data.binance_client import get_binance_client

logger = logging.getLogger("prady.agents.executor")
MIN_SPOT_POSITION_NOTIONAL_USDT = Decimal("5")
MIN_SIGNAL_EXIT_HOLD_MINUTES = 5.0


def _ticker_to_price(ticker) -> float:
    """Extract price float from get_ticker_price() return value."""
    if isinstance(ticker, dict):
        return float(ticker.get("lastPrice", ticker.get("price", 0)))
    return float(ticker)


class ExecutorAgent:
    """
    Converts council decisions into live/paper orders on Binance Spot.
    Uses Kelly criterion for position sizing.
    """

    def __init__(self, paper_engine=None, position_tracker=None, journal=None):
        self.settings = get_settings()
        self.client = get_binance_client()
        self.paper_engine = paper_engine
        self.position_tracker = position_tracker
        self.journal = journal
        self._win_history: list[bool] = []

    def record_outcome(self, win: bool):
        """Record win/loss for Kelly calculation."""
        self._win_history.append(win)
        if len(self._win_history) > KELLY_ROLLING_WINDOW:
            self._win_history = self._win_history[-KELLY_ROLLING_WINDOW:]

    def _kelly_fraction(self, confidence: float) -> Decimal:
        """Calculate Kelly Criterion position size fraction."""
        if len(self._win_history) < 10:
            return self.settings.kelly_fraction * Decimal(str(confidence))

        wins = sum(self._win_history)
        total = len(self._win_history)
        p = Decimal(str(wins / total))
        q = Decimal("1") - p

        if p <= Decimal("0"):
            return Decimal("0")

        kelly = max(Decimal("0"), p - q)
        fraction = kelly * self.settings.kelly_fraction * Decimal(str(confidence))
        return min(fraction, MAX_POSITION_PCT)

    def compute_position_size(
        self, balance: Decimal, confidence: float
    ) -> Decimal:
        """Calculate USDT position size based on Kelly and account balance."""
        fraction = self._kelly_fraction(confidence)
        raw_size = balance * fraction

        if raw_size < Decimal("5"):
            logger.info("Position size $%.2f below minimum $5 — skipping", raw_size)
            return Decimal("0")

        logger.info(
            "Position size: $%.2f (%.2f%% of $%.2f, Kelly frac=%.4f)",
            raw_size, float(fraction) * 100, balance, fraction,
        )
        return raw_size.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    def _get_current_price(self, symbol: str) -> Decimal:
        """Get current price from Binance free API."""
        ticker = self.client.get_ticker_price(symbol)
        return Decimal(str(_ticker_to_price(ticker)))

    def _get_quote_balance(self, symbol: str, *, include_reserve: bool = False) -> Decimal:
        """Return spendable quote balance with compatibility fallbacks for older clients/tests."""
        try:
            if include_reserve and hasattr(self.client, "get_quote_balance_with_safe_reserve"):
                return Decimal(str(self.client.get_quote_balance_with_safe_reserve(symbol)))
            if hasattr(self.client, "get_quote_balance"):
                return Decimal(str(self.client.get_quote_balance(symbol)))
        except Exception as exc:
            logger.debug("Quote-balance lookup failed for %s: %s", symbol, exc)
        return Decimal(str(self.client.get_usdt_balance()))

    def _exchange_inventory(self, symbol: str, current_price: Optional[Decimal] = None) -> tuple[Decimal, Decimal]:
        """Return existing exchange-held base quantity and its notional value."""
        if current_price is None:
            current_price = self._get_current_price(symbol)
        quantity = Decimal(str(self.client.get_symbol_base_balance(symbol, include_locked=True)))
        notional = quantity * current_price
        return quantity, notional

    def _sync_exchange_inventory_position(
        self,
        symbol: str,
        current_price: Optional[Decimal] = None,
    ) -> Optional[Dict[str, Any]]:
        """Adopt exchange-held spot inventory into the tracker so exits and state remain consistent."""
        if self.settings.is_paper or self.position_tracker is None:
            return None

        if current_price is None:
            current_price = self._get_current_price(symbol)

        held_qty, held_notional = self._exchange_inventory(symbol, current_price)
        if held_qty <= 0 or held_notional < MIN_SPOT_POSITION_NOTIONAL_USDT:
            return None

        had_position = self.position_tracker.has_position(symbol)
        entry_price = current_price
        try:
            estimated_entry = float(
                self.client.estimate_spot_entry_price(symbol, quantity=float(held_qty))
            )
            if estimated_entry > 0:
                entry_price = Decimal(str(estimated_entry))
        except Exception as exc:
            logger.debug("Entry-price estimate unavailable for %s: %s", symbol, exc)

        tracked = self.position_tracker.sync_position(
            symbol=symbol,
            quantity=float(held_qty),
            entry_price=float(entry_price),
            leverage=1,
            paper=False,
            source="exchange_sync",
        )
        return {
            "created": not had_position,
            "position": tracked,
            "held_quantity": float(held_qty),
            "held_notional": float(held_notional),
            "entry_price": float(entry_price),
        }

    def sync_exchange_positions(self, positions: Optional[list[dict]] = None) -> Dict[str, int]:
        """Reconcile exchange inventory into the in-memory tracker."""
        if self.settings.is_paper or self.position_tracker is None:
            return {"synced": 0, "adopted": 0, "updated": 0}

        if positions is None:
            positions = self.client.get_positions()

        adopted = 0
        updated = 0
        for raw in positions or []:
            symbol = str(raw.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            mark_price_raw = raw.get("markPrice")
            mark_price = None
            if mark_price_raw not in (None, ""):
                try:
                    mark_price = Decimal(str(mark_price_raw))
                except Exception:
                    mark_price = None
            sync_info = self._sync_exchange_inventory_position(symbol, current_price=mark_price)
            if sync_info is None:
                continue
            if sync_info["created"]:
                adopted += 1
            else:
                updated += 1
        return {"synced": adopted + updated, "adopted": adopted, "updated": updated}

    async def execute_entry(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        decision_context: Optional[Dict[str, Any]] = None,
        entry_price: Optional[Decimal] = None,
        stop_loss_pct: Decimal = Decimal("0.02"),
        take_profit_pct: Decimal = Decimal("0.03"),
    ) -> Dict[str, Any]:
        """Place entry order with stop-loss and take-profit."""
        settings = self.settings

        if settings.is_paper:
            return self._paper_entry(symbol, direction, confidence, stop_loss_pct, take_profit_pct)

        current_price = self._get_current_price(symbol)

        if direction == "LONG":
            if self.position_tracker is not None and self.position_tracker.has_position(symbol):
                return {"status": "skipped", "reason": "tracked_position_exists"}

            held_qty, held_notional = self._exchange_inventory(symbol, current_price)
            if held_notional >= MIN_SPOT_POSITION_NOTIONAL_USDT:
                sync_info = self._sync_exchange_inventory_position(symbol, current_price)
                logger.warning(
                    "Skipping %s entry for %s — unmanaged spot inventory %.6f (~$%.2f) already exists",
                    direction,
                    symbol,
                    held_qty,
                    held_notional,
                )
                return {
                    "status": "skipped",
                    "reason": "exchange_inventory_exists",
                    "held_quantity": float(held_qty),
                    "held_notional": float(held_notional),
                    "tracked_position_synced": bool(sync_info),
                }

            deployable_quote = self._get_quote_balance(symbol, include_reserve=True)
            size_usdt = self.compute_position_size(deployable_quote, confidence)
            if size_usdt <= Decimal("0"):
                return {"status": "skipped", "reason": "position_too_small"}

            available_quote = self._get_quote_balance(symbol)
            reserve_transfer = None
            if size_usdt > available_quote and hasattr(self.client, "ensure_quote_liquidity"):
                reserve_transfer = self.client.ensure_quote_liquidity(symbol, float(size_usdt))
                available_quote = self._get_quote_balance(symbol)
            size_usdt = min(size_usdt, available_quote)
            if size_usdt <= Decimal("0"):
                result = {"status": "skipped", "reason": "insufficient_quote_balance"}
                if reserve_transfer is not None:
                    result["reserve_transfer"] = reserve_transfer
                return result

            quantity = size_usdt / current_price
            quantity = Decimal(str(self.client.normalize_quantity(symbol, float(quantity))))
            if quantity <= Decimal("0"):
                return {"status": "skipped", "reason": "quantity_below_lot_size"}

            side = "BUY"
            order = self.client.place_market_order(symbol, side, float(quantity))

            sl_price = current_price * (Decimal("1") - stop_loss_pct)
            tp_price = current_price * (Decimal("1") + take_profit_pct)

            trade_id = None
            if self.journal is not None:
                try:
                    trade_id = self.journal.record_entry(
                        symbol=symbol,
                        direction="LONG",
                        entry_price=float(current_price),
                        quantity=float(quantity),
                        leverage=1,
                        stop_loss=float(sl_price),
                        take_profit=float(tp_price),
                        council_confidence=confidence,
                        paper=False,
                    )
                except Exception as exc:
                    logger.warning("Live trade journal entry failed for %s: %s", symbol, exc)

            if self.position_tracker is not None:
                self.position_tracker.open_position(
                    symbol=symbol,
                    direction="LONG",
                    entry_price=float(current_price),
                    quantity=float(quantity),
                    leverage=1,
                    stop_loss=float(sl_price),
                    take_profit=float(tp_price),
                    order_id=str(order.get("orderId")) if order.get("orderId") is not None else None,
                    trade_id=trade_id,
                    paper=False,
                    metadata=decision_context,
                )

            result = {
                "status": "filled",
                "symbol": symbol,
                "direction": direction,
                "quantity": float(quantity),
                "entry_price": float(current_price),
                "stop_loss": float(sl_price),
                "take_profit": float(tp_price),
                "order_id": order.get("orderId"),
                "sl_order_id": None,
                "tp_order_id": None,
                "execution_market": "spot",
                "execution_environment": self.client.execution_environment,
            }
            if reserve_transfer is not None:
                result["reserve_transfer"] = reserve_transfer
            logger.info(
                "SPOT ENTRY: %s %s %.6f @ %.2f | SL=%.2f TP=%.2f",
                direction,
                symbol,
                quantity,
                current_price,
                sl_price,
                tp_price,
            )
            return result

        if self.position_tracker is None or not self.position_tracker.has_position(symbol):
            sync_info = self._sync_exchange_inventory_position(symbol, current_price)
            if sync_info is not None:
                logger.info(
                    "Reverse signal for %s will liquidate synced exchange inventory %.6f (~$%.2f)",
                    symbol,
                    sync_info["held_quantity"],
                    sync_info["held_notional"],
                )
                return await self.close_position(symbol, reason="signal_reverse", signal_confidence=confidence)
            return {"status": "skipped", "reason": "no_tracked_spot_position"}

        return await self.close_position(symbol, reason="signal_reverse", signal_confidence=confidence)

    def _paper_entry(
        self, symbol: str, direction: str, confidence: float,
        stop_loss_pct: Decimal, take_profit_pct: Decimal,
    ) -> Dict[str, Any]:
        """Simulate entry for paper trading mode using PaperTradingEngine."""
        current_price = self._get_current_price(symbol)
        side = "BUY" if direction == "LONG" else "SELL"

        existing = None
        reversed_position = False
        if self.paper_engine is not None:
            existing = self.paper_engine.positions.get(symbol)
            if existing is not None:
                if existing.side == side:
                    return {
                        "status": "skipped",
                        "reason": "paper_position_exists",
                        "symbol": symbol,
                        "direction": direction,
                    }
                self.paper_engine.place_market_order(
                    symbol, side, float(existing.quantity), float(current_price)
                )
                reversed_position = True

        # Use paper engine balance if available, otherwise default
        if self.paper_engine is not None:
            balance = self.paper_engine.balance
        else:
            balance = Decimal("10000")

        size_usdt = self.compute_position_size(balance, confidence)
        if size_usdt <= Decimal("0"):
            return {"status": "skipped", "reason": "position_too_small"}

        quantity = (size_usdt * self.settings.default_leverage) / current_price
        quantity = quantity.quantize(Decimal("0.001"), rounding=ROUND_DOWN)

        # Actually execute on paper engine
        if self.paper_engine is not None:
            self.paper_engine.place_market_order(
                symbol, side, float(quantity), float(current_price)
            )

            # Place paper SL/TP
            if direction == "LONG":
                sl_price = float(current_price * (Decimal("1") - stop_loss_pct))
                tp_price = float(current_price * (Decimal("1") + take_profit_pct))
                sl_side = "SELL"
            else:
                sl_price = float(current_price * (Decimal("1") + stop_loss_pct))
                tp_price = float(current_price * (Decimal("1") - take_profit_pct))
                sl_side = "BUY"

            self.paper_engine.place_stop_market(symbol, sl_side, float(quantity), sl_price)
            self.paper_engine.place_limit_order(symbol, sl_side, float(quantity), tp_price)
        else:
            if direction == "LONG":
                sl_price = float(current_price * (Decimal("1") - stop_loss_pct))
                tp_price = float(current_price * (Decimal("1") + take_profit_pct))
            else:
                sl_price = float(current_price * (Decimal("1") + stop_loss_pct))
                tp_price = float(current_price * (Decimal("1") - take_profit_pct))

        result = {
            "status": "paper_filled",
            "symbol": symbol,
            "direction": direction,
            "quantity": float(quantity),
            "entry_price": float(current_price),
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "paper": True,
            "reversed_position": reversed_position,
        }
        logger.info("[PAPER] ENTRY: %s %s %.3f @ %.2f | SL=%.2f TP=%.2f",
                     direction, symbol, quantity, current_price, sl_price, tp_price)
        return result

    async def execute_hedge_grid(
        self,
        symbol: str,
        direction: str,
        entry_price: Decimal,
        quantity: Decimal,
    ) -> Dict[str, Any]:
        """Set up hedge grid: place a smaller counter-position as insurance."""
        hedge_qty = quantity * DEFAULT_HEDGE_RATIO
        hedge_side = "SELL" if direction == "LONG" else "BUY"

        if direction == "LONG":
            hedge_trigger = entry_price * (Decimal("1") - DEFAULT_HARVEST_THRESHOLD)
        else:
            hedge_trigger = entry_price * (Decimal("1") + DEFAULT_HARVEST_THRESHOLD)

        if self.settings.is_paper:
            logger.info("[PAPER] HEDGE: %s %.3f @ trigger %.2f", hedge_side, hedge_qty, hedge_trigger)
            return {
                "status": "paper_hedge",
                "hedge_side": hedge_side,
                "hedge_qty": float(hedge_qty),
                "trigger_price": float(hedge_trigger),
            }

        logger.info("Spot execution does not support hedge-grid shorts for %s", symbol)
        return {
            "status": "skipped",
            "reason": "hedge_grid_not_supported_on_spot",
            "symbol": symbol,
        }

    async def close_position(
        self,
        symbol: str,
        reason: str = "signal",
        signal_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Close all positions and cancel open orders for a symbol."""
        if self.settings.is_paper:
            if self.paper_engine is not None and symbol in self.paper_engine._positions:
                price = float(self._get_current_price(symbol))
                pos = self.paper_engine._positions[symbol]
                close_side = "SELL" if pos.side == "BUY" else "BUY"
                self.paper_engine.place_market_order(
                    symbol, close_side, float(pos.quantity), price
                )
                self.paper_engine.cancel_all_orders(symbol)
            logger.info("[PAPER] CLOSE ALL for %s", symbol)
            return {"status": "paper_closed", "symbol": symbol}

        if self.position_tracker is None:
            return {"status": "skipped", "symbol": symbol, "reason": "position_tracker_missing"}

        current_price = self._get_current_price(symbol)
        tracked = self.position_tracker.get_position(symbol)
        if tracked is None:
            self._sync_exchange_inventory_position(symbol, current_price)
            tracked = self.position_tracker.get_position(symbol)
        if tracked is None:
            return {"status": "skipped", "symbol": symbol, "reason": "no_tracked_spot_position"}

        if reason == "signal_reverse" and tracked.source != "exchange_sync":
            hold_minutes = tracked.holding_time_minutes()
            pnl_pct = tracked.unrealised_pnl_pct(current_price)
            min_harvest_pct = Decimal(str(self.settings.harvest_threshold)) * Decimal("100")
            strong_reverse = (
                signal_confidence is not None
                and signal_confidence >= FORCE_SIGNAL_EXIT_CONFIDENCE
            )
            adverse_move = pnl_pct <= FORCE_SIGNAL_EXIT_LOSS_PCT
            if not (strong_reverse or adverse_move) and hold_minutes < MIN_SIGNAL_EXIT_HOLD_MINUTES and pnl_pct < min_harvest_pct:
                logger.info(
                    "Skipping reverse exit for %s — hold %.2fm, pnl %.2f%%, target %.2f%%",
                    symbol,
                    hold_minutes,
                    pnl_pct,
                    min_harvest_pct,
                )
                return {
                    "status": "skipped",
                    "symbol": symbol,
                    "reason": "signal_reverse_guard",
                    "holding_minutes": hold_minutes,
                    "pnl_pct": float(pnl_pct),
                    "required_pnl_pct": float(min_harvest_pct),
                }

        self.client.cancel_all_orders(symbol)

        available_qty = Decimal(str(self.client.get_symbol_base_balance(symbol)))
        quantity = min(tracked.quantity, available_qty)
        quantity = Decimal(str(self.client.normalize_quantity(symbol, float(quantity))))
        if quantity <= Decimal("0"):
            return {"status": "skipped", "symbol": symbol, "reason": "no_sellable_quantity"}

        price = float(current_price)
        order = self.client.place_market_order(symbol, "SELL", float(quantity))
        closed = self.position_tracker.close_position(symbol, price)
        if closed is not None:
            pnl = float(closed.get("pnl", 0.0) or 0.0)
            if pnl != 0.0:
                self.record_outcome(pnl > 0.0)
        if closed and self.journal is not None and closed.get("trade_id"):
            entry_price = closed.get("entry_price", 0) or 0
            pnl_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0.0
            try:
                self.journal.record_exit(
                    trade_id=int(closed["trade_id"]),
                    exit_price=price,
                    pnl=float(closed.get("pnl", 0.0)),
                    pnl_pct=float(pnl_pct),
                    exit_reason=reason,
                )
            except Exception as exc:
                logger.warning("Live trade journal exit failed for %s: %s", symbol, exc)

        logger.info("SPOT CLOSE: %s %.6f @ %.2f (%s)", symbol, quantity, price, reason)
        result = {
            "status": "closed",
            "symbol": symbol,
            "quantity": float(quantity),
            "exit_price": price,
            "order_id": order.get("orderId"),
            "reason": reason,
            "closed_trade": closed,
        }
        try:
            reserve_transfer = self.client.park_quote_in_safe_reserve(symbol)
        except Exception as exc:
            logger.warning("Safe-reserve parking failed for %s: %s", symbol, exc)
            reserve_transfer = {"status": "skipped", "reason": "reserve_transfer_failed"}
        result["reserve_transfer"] = reserve_transfer
        return result
