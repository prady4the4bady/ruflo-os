#!/usr/bin/env python3
"""
Replay logged council decisions into simulated trade outcomes so symbol selection
can use actual agent-generated LONG/SHORT decisions instead of composite proxies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import ROOT_DIR, get_settings
from council.calibration import load_decision_records
from council.replay import BinanceReplayTradePathResolver, INTERVAL_MINUTES
from council.trade_audit import evaluate_council_trades, write_trade_audit_report

DEFAULT_OUTPUT = ROOT_DIR / "logs" / "council_trade_audit.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit logged council trades against realized price paths")
    parser.add_argument("--days", type=int, default=5, help="Number of recent decision-log files to replay")
    parser.add_argument("--lookahead-minutes", type=int, default=60, help="Trade holding window used for replay")
    parser.add_argument("--stop-loss-pct", type=float, default=0.02, help="Replay stop-loss as a decimal fraction")
    parser.add_argument("--take-profit-pct", type=float, default=0.03, help="Replay take-profit as a decimal fraction")
    parser.add_argument("--min-confidence", type=float, default=0.60, help="Minimum decision confidence required to count as a trade")
    parser.add_argument("--min-trades", type=int, default=6, help="Minimum simulated trades required for symbol eligibility")
    parser.add_argument("--min-profit-factor", type=float, default=1.0, help="Minimum profit factor required for symbol eligibility")
    parser.add_argument("--min-expectancy-pct", type=float, default=0.0, help="Minimum expectancy percentage required for symbol eligibility")
    parser.add_argument("--interval", type=str, default="5m", choices=sorted(INTERVAL_MINUTES), help="Replay price interval")
    parser.add_argument(
        "--decision-log-dir",
        type=Path,
        default=ROOT_DIR / "logs" / "decisions",
        help="Directory containing decisions_*.jsonl files",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Optional subset of symbols to audit",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the council trade audit report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_decision_records(args.decision_log_dir, max_files=args.days)
    if not records:
        print(f"No decision records found in {args.decision_log_dir}")
        return 1

    configured_symbols = args.symbols or list(get_settings().trading_pairs)
    resolver = BinanceReplayTradePathResolver(args.interval, args.lookahead_minutes)
    audit = evaluate_council_trades(
        records,
        resolver,
        lookahead_minutes=args.lookahead_minutes,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        min_confidence=args.min_confidence,
        configured_symbols=configured_symbols,
        selection_min_trades=args.min_trades,
        selection_min_profit_factor=args.min_profit_factor,
        selection_min_expectancy_pct=args.min_expectancy_pct,
    )

    payload = {
        **audit,
        "summary": {
            **audit["summary"],
            "decision_log_dir": str(args.decision_log_dir),
            "decision_files": args.days,
            "interval": args.interval,
            "configured_symbols": configured_symbols,
        },
    }
    write_trade_audit_report(args.output, payload)

    overall = payload["summary"]["overall"]
    print(f"Council trade audit written to {args.output}")
    print(
        "Overall: "
        f"trades={overall['trades']} "
        f"win_rate={overall['win_rate']:.3f} "
        f"profit_factor={overall['profit_factor']:.3f} "
        f"expectancy_pct={overall['expectancy_pct']:.3f}"
    )
    print(f"Eligible symbols: {', '.join(payload['eligible_symbols']) if payload['eligible_symbols'] else '(none)'}")
    controls = payload.get("recommended_path_controls") or {}
    disabled_agents = controls.get("disabled_agents") or []
    penalized_agents = controls.get("penalized_agents") or []
    blocked_coalitions = controls.get("blocked_coalitions") or []
    print(f"Disabled agents: {', '.join(disabled_agents) if disabled_agents else '(none)'}")
    if penalized_agents:
        print(
            "Penalized agents: "
            + ", ".join(
                f"{item['agent']}x{float(item['multiplier']):.2f}"
                for item in penalized_agents
                if isinstance(item, dict)
            )
        )
    else:
        print("Penalized agents: (none)")
    if blocked_coalitions:
        print(
            "Blocked coalitions: "
            + "; ".join(
                f"[{'+'.join(item.get('supporting_agents', []))}]"
                for item in blocked_coalitions
                if isinstance(item, dict)
            )
        )
    else:
        print("Blocked coalitions: (none)")
    for item in payload["ranked_symbols"]:
        print(
            f"  {item['symbol']:8s} eligible={item['eligible']} trades={item['trades']:3d} "
            f"expectancy={item['expectancy_pct']:.3f}% pf={item['profit_factor']:.3f} "
            f"models={item['models_available']}"
        )
    return 0 if overall["expectancy_pct"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())