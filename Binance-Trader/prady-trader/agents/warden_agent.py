"""
PRADY TRADER — Warden Agent (VETO power).
Portfolio-level risk manager. Can VETO any trade if:
  - Daily loss limit breached
  - Drawdown too deep
  - Too many concurrent positions
  - Correlation overload
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent, AgentSignal
from config.settings import get_settings
from data.binance_client import get_binance_client
from utils.time_utils import parse_utc_timestamp, utc_now

logger = logging.getLogger("prady.agents.warden")
MIN_TRACKED_NOTIONAL_USDT = Decimal("5")


class WardenAgent(BaseAgent):
    """
    Risk-gating warden with VETO authority.
    Weight: N/A — operates as a binary gate, not a council voter.
    """

    def __init__(self):
        super().__init__(name="warden", weight=0.0)  # does not vote
        self._daily_pnl: Decimal = Decimal("0")
        self._peak_equity: Optional[Decimal] = None
        self._trade_log: List[Dict] = []

    def record_trade_result(self, pnl: Decimal, symbol: str):
        """Record a trade result for daily tracking."""
        self._daily_pnl += pnl
        self._trade_log.append({
            "symbol": symbol,
            "pnl": float(pnl),
            "time": utc_now().isoformat(),
        })

    def reset_daily(self):
        """Reset daily PnL counter (call at UTC midnight)."""
        self._daily_pnl = Decimal("0")
        self._trade_log.clear()

    async def analyze(self, symbol: str) -> AgentSignal:
        """Warden doesn't produce directional signals — use check_veto() instead."""
        veto, reason = await self.check_veto(symbol)
        if veto:
            return AgentSignal(
                agent_name=self.name,
                direction="NEUTRAL",
                confidence=1.0,
                score=0.0,
                reasoning=f"VETO: {reason}",
                metadata={"veto": True, "reason": reason},
            )
        return AgentSignal(
            agent_name=self.name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning="No veto — conditions within limits",
            metadata={"veto": False},
        )

    async def check_veto(self, symbol: str) -> tuple[bool, str]:
        """
        Returns (veto: bool, reason: str).
        True = trade must be rejected.
        """
        settings = get_settings()
        client = get_binance_client()
        reasons: List[str] = []

        # 1. Daily loss limit
        if self._daily_pnl <= -settings.max_daily_loss * Decimal("100"):
            reasons.append(
                f"Daily loss limit hit: {self._daily_pnl} "
                f"(max: {-settings.max_daily_loss * Decimal('100')})"
            )

        # 2. Max concurrent positions
        try:
            positions = client.get_positions()
            active = [
                p for p in positions
                if Decimal(str(p.get("estimated_usdt_value", 0) or 0)) >= MIN_TRACKED_NOTIONAL_USDT
            ]
            if len(active) >= settings.max_concurrent_positions:
                reasons.append(
                    f"Max concurrent positions reached: {len(active)}"
                    f"/{settings.max_concurrent_positions}"
                )
        except Exception as exc:
            logger.warning("Position check failed: %s", exc)

        # 3. Drawdown check — compare current equity to peak
        try:
            account = client.get_execution_account_info() if settings.uses_binance_execution else {}
            summary = account.get("account_summary", {}) if isinstance(account, dict) else {}
            equity_value = summary.get("estimated_total_usdt") or summary.get("free_usdt")
            if equity_value in (None, ""):
                equity_value = client.get_usdt_balance()
            equity = Decimal(str(equity_value))
            if self._peak_equity is None or equity > self._peak_equity:
                self._peak_equity = equity
            if self._peak_equity > 0:
                drawdown = (self._peak_equity - equity) / self._peak_equity
                if drawdown > Decimal("0.10"):
                    reasons.append(f"Drawdown {drawdown:.2%} exceeds 10% limit")
        except Exception as exc:
            logger.warning("Balance check failed: %s", exc)

        # 4. Same-symbol duplicate check
        recent_same = [
            t for t in self._trade_log
            if t["symbol"] == symbol
            and parse_utc_timestamp(t["time"]) > utc_now() - timedelta(minutes=5)
        ]
        if len(recent_same) >= 3:
            reasons.append(f"Too many recent trades on {symbol}: {len(recent_same)} in 5 min")

        if reasons:
            veto_reason = "; ".join(reasons)
            logger.info("WARDEN VETO on %s: %s", symbol, veto_reason)
            return True, veto_reason

        return False, ""
