"""
PRADY TRADER — Backtesting engine.
Replays historical data through the simplified composite-score path.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.settings import get_settings
from config.constants import (
    COUNCIL_LONG_THRESHOLD, COUNCIL_SHORT_THRESHOLD,
    BACKTEST_LONG_THRESHOLD, BACKTEST_SHORT_THRESHOLD, BACKTEST_MIN_CONFIDENCE,
)
from indicators.composite import compute_composite_score
from data.data_store import get_data_store
from execution.paper_engine import PaperTradingEngine

logger = logging.getLogger("prady.utils.backtester")


class BacktestResult:
    """Container for backtest results."""

    def __init__(self):
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = []
        self.timestamps: List[datetime] = []
        self.initial_balance: float = 10000.0
        self.final_balance: float = 10000.0

    @property
    def total_return_pct(self) -> float:
        if self.initial_balance <= 0:
            return 0.0
        return (self.final_balance - self.initial_balance) / self.initial_balance * 100

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        return wins / len(self.trades)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        eq = np.array(self.equity_curve)
        returns = np.diff(eq) / eq[:-1]
        returns = returns[np.isfinite(returns)]
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0
        # Annualize: assume hourly bars → 365*24 periods/year
        return float(np.mean(returns) / np.std(returns) * np.sqrt(365 * 24))

    @property
    def sortino_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        eq = np.array(self.equity_curve)
        returns = np.diff(eq) / eq[:-1]
        returns = returns[np.isfinite(returns)]
        if len(returns) < 2:
            return 0.0
        downside = returns[returns < 0]
        if len(downside) == 0 or np.std(downside) == 0:
            return float("inf") if np.mean(returns) > 0 else 0.0
        return float(np.mean(returns) / np.std(downside) * np.sqrt(365 * 24))

    @property
    def calmar_ratio(self) -> float:
        if self.max_drawdown == 0:
            return float("inf") if self.total_return_pct > 0 else 0.0
        # Annualize return based on equity curve length (hourly bars)
        hours = max(len(self.equity_curve), 1)
        annual_return = self.total_return_pct / 100 * (365 * 24 / hours)
        return float(annual_return / self.max_drawdown)

    @property
    def profit_factor(self) -> float:
        wins = sum(t["pnl"] for t in self.trades if t.get("pnl", 0) > 0)
        losses = abs(sum(t["pnl"] for t in self.trades if t.get("pnl", 0) < 0))
        if losses == 0:
            return float("inf") if wins > 0 else 0.0
        return wins / losses

    def summary(self) -> Dict:
        return {
            "initial_balance": self.initial_balance,
            "final_balance": round(self.final_balance, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "profit_factor": round(self.profit_factor, 2),
        }


class Backtester:
    """
    Replays historical candle data and simulates trading decisions.
    Uses the composite score path, not full council-agent decisions.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        risk_per_trade: float = 0.02,
        sl_pct: float = 0.02,
        tp_pct: float = 0.03,
        leverage: int = 5,
        max_hold_bars: int = 48,
    ):
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.leverage = leverage
        self.max_hold_bars = max_hold_bars
        self.engine = PaperTradingEngine(Decimal(str(initial_balance)))

    def run(
        self,
        df: pd.DataFrame,
        symbol: str = "BTCUSDT",
        warmup_bars: int = 200,
    ) -> BacktestResult:
        """
        Run backtest on a DataFrame with columns: open, high, low, close, volume.
        """
        result = BacktestResult()
        result.initial_balance = self.initial_balance

        if len(df) < warmup_bars + 50:
            logger.warning("Insufficient data for backtest: %d bars", len(df))
            result.final_balance = self.initial_balance
            return result

        logger.info("Starting backtest: %d bars, warmup=%d", len(df), warmup_bars)
        start_time = time.time()

        store = get_data_store()

        position_entry_bars: Dict[str, int] = {}

        for i in range(warmup_bars, len(df)):
            current = df.iloc[i]
            current_price = float(current["close"])
            window = df.iloc[max(0, i - 500):i + 1].copy()

            # Push data to store for indicator computation
            for _, row in window.tail(5).iterrows():
                candle = {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
                store.push_candle(symbol, "1h", candle)

            # Check pending orders
            self.engine.check_pending_orders(symbol, current_price)

            # Clean up entry bar tracking for closed positions
            for sym in list(position_entry_bars):
                if sym not in self.engine._positions:
                    del position_entry_bars[sym]

            # Close stale positions after max_hold_bars
            if symbol in self.engine._positions:
                entry_bar = position_entry_bars.get(symbol, i)
                bars_held = i - entry_bar
                if bars_held >= self.max_hold_bars:
                    pos = self.engine._positions[symbol]
                    side = "SELL" if pos.side == "BUY" else "BUY"
                    self.engine.place_market_order(symbol, side, float(pos.quantity), current_price)
                    position_entry_bars.pop(symbol, None)
                else:
                    result.equity_curve.append(
                        float(self.engine.get_equity({symbol: current_price}))
                    )
                    continue

            # Compute composite score
            try:
                dataframes = {"1h": window}
                composite = compute_composite_score(dataframes)
                score = composite.get("score", 50)
                direction = composite.get("direction", "WAIT")
                confidence = composite.get("confidence", 0.0)
            except Exception:
                score = 50
                direction = "WAIT"
                confidence = 0.0

            # Generate signals using relaxed backtest thresholds
            if (direction == "LONG" and score >= BACKTEST_LONG_THRESHOLD
                    and confidence >= BACKTEST_MIN_CONFIDENCE
                    and symbol not in self.engine._positions):
                qty = (self.initial_balance * self.risk_per_trade * self.leverage) / current_price
                self.engine.place_market_order(symbol, "BUY", qty, current_price)

                sl_price = current_price * (1 - self.sl_pct)
                tp_price = current_price * (1 + self.tp_pct)
                self.engine.place_stop_market(symbol, "SELL", qty, sl_price)
                self.engine.place_limit_order(symbol, "SELL", qty, tp_price)

                position_entry_bars[symbol] = i

            elif (direction == "SHORT" and score <= BACKTEST_SHORT_THRESHOLD
                    and confidence >= BACKTEST_MIN_CONFIDENCE
                    and symbol not in self.engine._positions):
                qty = (self.initial_balance * self.risk_per_trade * self.leverage) / current_price
                self.engine.place_market_order(symbol, "SELL", qty, current_price)

                sl_price = current_price * (1 + self.sl_pct)
                tp_price = current_price * (1 - self.tp_pct)
                self.engine.place_stop_market(symbol, "BUY", qty, sl_price)
                self.engine.place_limit_order(symbol, "BUY", qty, tp_price)

            result.equity_curve.append(
                float(self.engine.get_equity({symbol: current_price}))
            )

        result.trades = self.engine.get_trade_history()
        result.final_balance = float(self.engine.balance)

        elapsed = time.time() - start_time
        logger.info(
            "Backtest complete in %.1fs: %d trades, return=%.2f%%, win_rate=%.2f%%",
            elapsed, result.total_trades, result.total_return_pct, result.win_rate * 100,
        )

        return result
