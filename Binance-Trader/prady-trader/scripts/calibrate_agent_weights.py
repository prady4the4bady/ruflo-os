"""
Replay council decisions against realized forward price moves and emit
recommended agent weights for the live weight manager bootstrap file.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import ROOT_DIR
from council.calibration import (
    evaluate_agent_decisions,
    load_decision_records,
    recommend_agent_weights,
    recommend_score_thresholds,
    write_calibration_report,
)
from council.replay import INTERVAL_MINUTES, BinanceReplayPriceResolver
from council.weight_manager import DEFAULT_WEIGHT_BOOTSTRAP_FILE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay decision logs into calibrated council weights")
    parser.add_argument("--days", type=int, default=3, help="Number of recent decision-log files to replay")
    parser.add_argument("--lookahead-minutes", type=int, default=60, help="Forward window used to score decisions")
    parser.add_argument(
        "--move-threshold-pct",
        type=float,
        default=0.002,
        help="Minimum absolute forward move, as a decimal fraction, to count as LONG/SHORT",
    )
    parser.add_argument("--interval", type=str, default="5m", choices=sorted(INTERVAL_MINUTES), help="Replay price interval")
    parser.add_argument("--min-samples", type=int, default=8, help="Minimum samples before an agent gets full calibration weight")
    parser.add_argument(
        "--decision-log-dir",
        type=Path,
        default=ROOT_DIR / "logs" / "decisions",
        help="Directory containing decisions_*.jsonl files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_WEIGHT_BOOTSTRAP_FILE,
        help="Where to write the calibrated weight report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_decision_records(args.decision_log_dir, max_files=args.days)
    if not records:
        print(f"No decision records found in {args.decision_log_dir}")
        return 1

    resolver = BinanceReplayPriceResolver(args.interval, args.lookahead_minutes)
    evaluation = evaluate_agent_decisions(
        records,
        resolver,
        lookahead_minutes=args.lookahead_minutes,
        move_threshold_pct=args.move_threshold_pct,
    )
    calibration = recommend_agent_weights(
        evaluation["agent_stats"],
        min_samples=args.min_samples,
    )
    threshold_recommendation = recommend_score_thresholds(evaluation["decision_outcomes"])
    write_calibration_report(
        args.output,
        summary={
            **evaluation["summary"],
            "decision_log_dir": str(args.decision_log_dir),
            "decision_files": args.days,
            "interval": args.interval,
            "min_samples": args.min_samples,
        },
        agent_stats=evaluation["agent_stats"],
        recommended_weights=calibration["recommended_weights"],
        threshold_recommendation=threshold_recommendation,
    )

    print(f"Calibrated weights written to {args.output}")
    print("Recommended weights:")
    for name, weight in calibration["recommended_weights"].items():
        stats = evaluation["agent_stats"].get(name, {})
        print(
            f"  {name:16s} weight={weight:.3f} accuracy={float(stats.get('accuracy', 0.5)):.3f} samples={int(stats.get('samples', 0.0))}"
        )
    print(
        "Recommended thresholds: "
        f"LONG>={threshold_recommendation['long']} SHORT<={threshold_recommendation['short']} metric={threshold_recommendation['metric']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())