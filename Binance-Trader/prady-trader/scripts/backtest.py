#!/usr/bin/env python3
"""
PRADY TRADER — Composite backtest CLI script.
Usage:
    python -m scripts.backtest --symbol BTCUSDT --days 90
    python -m scripts.backtest --symbol ETHUSDT --days 30 --initial-balance 5000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import setup_logging
from data.binance_client import BinanceClientWrapper
from utils.backtester import Backtester


def load_historical_data(symbol: str, days: int) -> "pd.DataFrame":
    """Load historical 1h klines from Binance free API."""
    import pandas as pd

    bc = BinanceClientWrapper()
    # Binance max per request is 1500 klines
    hours = days * 24
    limit = min(hours, 1500)
    klines = bc.get_klines(symbol, "1h", limit=limit)
    df = pd.DataFrame(klines, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df["timestamp"] = df["timestamp"].astype(int)
    return df


def main():
    parser = argparse.ArgumentParser(description="Run PRADY TRADER composite backtest")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading pair")
    parser.add_argument("--days", type=int, default=90, help="Days of history")
    parser.add_argument("--initial-balance", type=float, default=10000.0, help="Starting balance")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    logger = logging.getLogger("prady.scripts.backtest")

    logger.info("=" * 60)
    logger.info("PRADY TRADER — Composite Backtest")
    logger.info("Symbol: %s | Days: %d | Balance: $%.2f", args.symbol, args.days, args.initial_balance)
    logger.info("=" * 60)

    backtester = Backtester(initial_balance=args.initial_balance)

    logger.info("Loading %d days of 1h klines for %s...", args.days, args.symbol)
    df = load_historical_data(args.symbol, args.days)
    logger.info("Loaded %d candles", len(df))

    result = backtester.run(df=df, symbol=args.symbol)

    logger.info("\n" + "=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)
    logger.info("Total Return:    %.2f%%", result.total_return_pct)
    logger.info("Win Rate:        %.2f%%", result.win_rate * 100)
    logger.info("Total Trades:    %d", result.total_trades)
    logger.info("Max Drawdown:    %.2f%%", result.max_drawdown * 100)
    logger.info("Sharpe Ratio:    %.3f", result.sharpe_ratio)
    logger.info("Sortino Ratio:   %.3f", result.sortino_ratio)
    logger.info("Calmar Ratio:    %.3f", result.calmar_ratio)
    logger.info("Profit Factor:   %.3f", result.profit_factor)
    logger.info("Final Balance:   $%.2f", result.final_balance)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "symbol": args.symbol,
            "days": args.days,
            "initial_balance": args.initial_balance,
            "final_balance": result.final_balance,
            "total_return_pct": result.total_return_pct,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "max_drawdown": result.max_drawdown,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "profit_factor": result.profit_factor,
            "equity_curve_length": len(result.equity_curve),
        }
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info("Report saved to %s", out_path)

    return 0 if result.total_return_pct > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
