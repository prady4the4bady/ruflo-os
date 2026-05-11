"""
PRADY TRADER — Risk manager.
Enforces risk rules: per-trade risk, daily loss limits, max leverage,
drawdown protection, trailing stops.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional, Tuple

from config.settings import get_settings
from config.constants import (
    MAX_POSITION_PCT,
    MAX_LEVERAGE,
    DEFAULT_MAX_HOLD_MINUTES,
    CONFIDENCE_EXIT_THRESHOLD,
)

logger = logging.getLogger("prady.execution.risk_manager")


class RiskManager:
    """Centralised risk-limiting logic."""

    def __init__(self):
        self.settings = get_settings()
        self._daily_loss: Decimal = Decimal("0")
        self._daily_trades: int = 0
        self._peak_equity: Optional[Decimal] = None

    def reset_daily(self):
        """Reset at UTC midnight."""
        self._daily_loss = Decimal("0")
        self._daily_trades = 0

    def record_loss(self, amount: Decimal):
        """Record a realised loss."""
        if amount < 0:
            self._daily_loss += abs(amount)
        self._daily_trades += 1

    def update_equity(self, equity: Decimal):
        """Track peak equity for drawdown calculation."""
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

    def current_drawdown(self, equity: Decimal) -> Decimal:
        """Calculate current drawdown from peak."""
        if self._peak_equity is None or self._peak_equity <= 0:
            return Decimal("0")
        return (self._peak_equity - equity) / self._peak_equity

    def check_daily_loss_limit(self, balance: Decimal) -> Tuple[bool, str]:
        """Returns (allowed, reason). False means daily limit reached."""
        max_loss = balance * self.settings.max_daily_loss
        if self._daily_loss >= max_loss:
            reason = f"Daily loss ${self._daily_loss:.2f} >= limit ${max_loss:.2f}"
            logger.warning("RISK: %s", reason)
            return False, reason
        return True, ""

    def check_position_size(self, size_usdt: Decimal, balance: Decimal) -> Tuple[bool, str]:
        """Ensure position size doesn't exceed max % of portfolio."""
        max_size = balance * MAX_POSITION_PCT
        if size_usdt > max_size:
            reason = f"Position ${size_usdt:.2f} exceeds max ${max_size:.2f} ({MAX_POSITION_PCT*100}%)"
            logger.warning("RISK: %s", reason)
            return False, reason
        return True, ""

    def check_leverage(self, leverage: int) -> Tuple[bool, str]:
        """Ensure leverage doesn't exceed maximum."""
        if leverage > MAX_LEVERAGE:
            reason = f"Leverage {leverage}x exceeds max {MAX_LEVERAGE}x"
            return False, reason
        return True, ""

    def check_drawdown(self, equity: Decimal, max_drawdown: Decimal = Decimal("0.10")) -> Tuple[bool, str]:
        """Check if current drawdown exceeds limit."""
        dd = self.current_drawdown(equity)
        if dd > max_drawdown:
            reason = f"Drawdown {dd:.2%} exceeds limit {max_drawdown:.2%}"
            logger.warning("RISK: %s", reason)
            return False, reason
        return True, ""

    def compute_stop_loss(
        self,
        entry_price: Decimal,
        direction: str,
        atr: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate stop-loss price.
        Uses ATR-based stop if ATR provided, else fixed 2%.
        """
        risk_pct = self.settings.max_risk_per_trade

        if atr is not None and atr > 0:
            # 1.5x ATR stop
            atr_stop = atr * Decimal("1.5")
            pct_stop = entry_price * risk_pct
            stop_distance = max(atr_stop, pct_stop)
        else:
            stop_distance = entry_price * risk_pct

        if direction == "LONG":
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance

    def compute_take_profit(
        self,
        entry_price: Decimal,
        direction: str,
        risk_reward_ratio: Decimal = Decimal("1.5"),
        stop_loss: Optional[Decimal] = None,
    ) -> Decimal:
        """Calculate take-profit based on risk-reward ratio."""
        if stop_loss is not None:
            risk = abs(entry_price - stop_loss)
        else:
            risk = entry_price * self.settings.max_risk_per_trade

        reward = risk * risk_reward_ratio

        if direction == "LONG":
            return entry_price + reward
        else:
            return entry_price - reward

    def compute_trailing_stop(
        self,
        current_price: Decimal,
        direction: str,
        trail_pct: Decimal = Decimal("0.015"),
    ) -> Decimal:
        """Calculate trailing stop level."""
        trail_distance = current_price * trail_pct
        if direction == "LONG":
            return current_price - trail_distance
        else:
            return current_price + trail_distance

    def should_exit_on_time(self, holding_minutes: float) -> bool:
        """Check if position has been held too long."""
        return holding_minutes >= DEFAULT_MAX_HOLD_MINUTES

    def should_exit_on_confidence(self, current_confidence: float) -> bool:
        """Exit if council confidence drops below threshold."""
        return current_confidence < CONFIDENCE_EXIT_THRESHOLD

    def full_pre_trade_check(
        self,
        balance: Decimal,
        equity: Decimal,
        size_usdt: Decimal,
        leverage: int,
    ) -> Tuple[bool, str]:
        """Run all pre-trade risk checks. Returns (allowed, reason)."""
        checks = [
            self.check_daily_loss_limit(balance),
            self.check_position_size(size_usdt, balance),
            self.check_leverage(leverage),
            self.check_drawdown(equity),
        ]
        for allowed, reason in checks:
            if not allowed:
                return False, reason
        return True, ""
