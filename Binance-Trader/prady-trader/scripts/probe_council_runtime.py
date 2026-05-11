#!/usr/bin/env python3
"""
Bounded council and paper-runtime probes for PRADY TRADER.

Use this script to:
1. Seed fresh candle and order-book context from Binance public REST.
2. Run council cycles that write today's decision logs.
3. Inspect the resulting strategy_fusion/local-setup behavior.
4. Exercise the paper runtime state path without starting the infinite main loop.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import apply_runtime_mode, get_settings
from council.decision_log import LOG_DIR
from council.orchestrator import CouncilOrchestrator, TradingOrchestrator
from data.binance_client import BinanceClientWrapper
from data.data_store import get_data_store
from data.orderbook_feed import OrderBookSnapshot, get_orderbook_feed
from utils.time_utils import utc_date_str


DEFAULT_INTERVALS = ["5m", "15m", "1h", "4h", "1d"]
LOCAL_SETUP_NAMES = {
    "liquidity_sweep_avwap",
    "failed_auction_delta",
    "cumulative_volume_delta_reversal",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded council/paper probes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--symbols",
            nargs="+",
            default=["BTCUSDT", "ETHUSDT"],
            help="Symbols to seed and probe",
        )
        target.add_argument(
            "--intervals",
            nargs="+",
            default=DEFAULT_INTERVALS,
            help="Kline intervals to seed into the data store",
        )
        target.add_argument(
            "--candle-limit",
            type=int,
            default=300,
            help="How many Binance klines to seed per interval",
        )

    council_parser = subparsers.add_parser("council", help="Run bounded council probe cycles")
    add_common_flags(council_parser)
    council_parser.add_argument("--rounds", type=int, default=1, help="How many probe rounds to run")
    council_parser.add_argument(
        "--allow-execution",
        action="store_true",
        help="Allow the executor path instead of stubbing execute_entry",
    )

    paper_parser = subparsers.add_parser("paper", help="Run bounded paper runtime cycles")
    add_common_flags(paper_parser)
    paper_parser.add_argument("--cycles", type=int, default=1, help="How many bounded paper cycles to run")
    paper_parser.add_argument(
        "--paper-min-confidence",
        type=float,
        default=0.68,
        help="Temporary min confidence to use during this bounded paper probe",
    )

    return parser.parse_args()


def _decision_log_path() -> Path:
    return LOG_DIR / f"decisions_{utc_date_str()}.jsonl"


def _count_log_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _configure_runtime(symbols: List[str]) -> None:
    settings = apply_runtime_mode("paper", persist=False)
    settings.trading_pairs = [symbol.upper().strip() for symbol in symbols]
    settings.enable_ollama_reasoning = False
    settings.enable_nvidia_nim_reasoning = False


def _kline_to_candle(kline: List[Any]) -> Dict[str, Any]:
    return {
        "timestamp": int(kline[0]),
        "open": float(kline[1]),
        "high": float(kline[2]),
        "low": float(kline[3]),
        "close": float(kline[4]),
        "volume": float(kline[5]),
    }


def _seed_symbol_context(
    client: BinanceClientWrapper,
    symbol: str,
    intervals: List[str],
    candle_limit: int,
) -> None:
    store = get_data_store()
    orderbook_feed = get_orderbook_feed()

    store.clear_symbol(symbol)
    for interval in intervals:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=candle_limit)
        for kline in klines:
            store.push_candle(symbol, interval, _kline_to_candle(kline))

    book = client.get_order_book(symbol=symbol, limit=20)
    bids = [[float(price), float(quantity)] for price, quantity in book.get("bids", [])]
    asks = [[float(price), float(quantity)] for price, quantity in book.get("asks", [])]
    timestamp = int(book.get("E") or book.get("T") or book.get("lastUpdateId") or 0)
    orderbook_feed._snapshots[symbol] = OrderBookSnapshot(symbol, bids, asks, timestamp)


def _extract_local_setups(strategy_fusion_signal) -> Dict[str, Dict[str, Any]]:
    if not strategy_fusion_signal:
        return {}
    metadata = getattr(strategy_fusion_signal, "metadata", {}) or {}
    signals = metadata.get("signals") or []
    extracted: Dict[str, Dict[str, Any]] = {}
    for signal in signals:
        name = signal.get("name")
        if name not in LOCAL_SETUP_NAMES:
            continue
        extracted[name] = {
            "direction": signal.get("direction"),
            "confidence": signal.get("confidence"),
            "score": signal.get("score"),
            "reasoning": signal.get("reasoning"),
        }
    return extracted


def _summarize_decision(symbol: str, decision) -> Dict[str, Any]:
    strategy_fusion = decision.agent_signals.get("strategy_fusion")
    strategy_fusion_metadata = getattr(strategy_fusion, "metadata", {}) or {}
    return {
        "symbol": symbol,
        "action": decision.action,
        "weighted_score": decision.weighted_score,
        "confidence": decision.confidence,
        "strategy_fusion": {
            "direction": getattr(strategy_fusion, "direction", None),
            "score": getattr(strategy_fusion, "score", None),
            "confidence": getattr(strategy_fusion, "confidence", None),
            "contributing_count": strategy_fusion_metadata.get("contributing_count"),
            "active_count": strategy_fusion_metadata.get("active_count"),
        },
        "local_setups": _extract_local_setups(strategy_fusion),
    }


async def run_council_probe(args: argparse.Namespace) -> Dict[str, Any]:
    symbols = [symbol.upper().strip() for symbol in args.symbols]
    _configure_runtime(symbols)

    client = BinanceClientWrapper()
    council = CouncilOrchestrator()
    if not args.allow_execution:
        council.executor.execute_entry = AsyncMock(return_value={
            "status": "probe",
            "reason": "execution_stubbed",
        })

    log_path = _decision_log_path()
    before_lines = _count_log_lines(log_path)
    results: List[Dict[str, Any]] = []

    for round_number in range(1, args.rounds + 1):
        for symbol in symbols:
            _seed_symbol_context(client, symbol, args.intervals, args.candle_limit)
            decision = await council.run_cycle(symbol)
            summary = _summarize_decision(symbol, decision)
            summary["round"] = round_number
            results.append(summary)

    after_lines = _count_log_lines(log_path)
    return {
        "mode": "council",
        "symbols": symbols,
        "rounds": args.rounds,
        "decision_log_path": str(log_path),
        "decision_log_delta": after_lines - before_lines,
        "thresholds": {
            "long": council.weight_manager.long_threshold,
            "short": council.weight_manager.short_threshold,
        },
        "results": results,
    }


async def run_paper_probe(args: argparse.Namespace) -> Dict[str, Any]:
    symbols = [symbol.upper().strip() for symbol in args.symbols]
    _configure_runtime(symbols)

    settings = get_settings()
    settings.min_confidence = Decimal(str(args.paper_min_confidence))

    client = BinanceClientWrapper()
    orchestrator = TradingOrchestrator()

    for _ in range(args.cycles):
        orchestrator._cycle_count += 1
        await orchestrator._refresh_prices()
        orchestrator._sync_execution_positions()
        orchestrator._check_pending_orders()
        await orchestrator._check_position_limits()
        trading_allowed = orchestrator._evaluate_runtime_guard()
        active_symbols = list(orchestrator._active_symbols())

        if trading_allowed:
            for symbol in active_symbols:
                _seed_symbol_context(client, symbol, args.intervals, args.candle_limit)
                decision = await orchestrator.council.run_cycle(symbol)
                orchestrator._agent_signals[symbol] = decision.agent_signals

        orchestrator._write_state()
        orchestrator._persist_new_trades()

    state = orchestrator.state_writer.read_state("paper")
    stats = orchestrator.paper_engine.get_stats()
    return {
        "mode": "paper",
        "symbols": symbols,
        "active_symbols": state.get("active_symbols", []),
        "cycles": args.cycles,
        "min_confidence": float(settings.min_confidence),
        "balance": stats.get("balance"),
        "equity": float(orchestrator.paper_engine.get_equity(orchestrator._prices)),
        "total_return_pct": stats.get("total_return_pct"),
        "total_trades": stats.get("total_trades"),
        "win_rate": stats.get("win_rate"),
        "open_positions": len(orchestrator.paper_engine.positions),
        "state_file": str((ROOT / "data" / "state_paper.json")),
        "runtime_guard": state.get("runtime_guard", {}),
        "last_decisions": state.get("last_decisions", {}),
        "closed_trades": state.get("closed_trades", [])[-5:],
    }


async def main() -> int:
    args = parse_args()
    if args.command == "council":
        payload = await run_council_probe(args)
    else:
        payload = await run_paper_probe(args)
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))