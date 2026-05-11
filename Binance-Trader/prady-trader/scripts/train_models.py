#!/usr/bin/env python3
"""
PRADY TRADER — Train models on historical Binance data.
Usage: python -m scripts.train_models [--symbol BTCUSDT] [--days 730]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on PATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import setup_logging, get_settings
from ml.trainer import run_training_pipeline, retrain_all_symbols


def parse_args():
    parser = argparse.ArgumentParser(description="PRADY TRADER model trainer")
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Single symbol to train (e.g. BTCUSDT). Omit to train all configured pairs.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=730,
        help="Number of days of historical data (default: 730)",
    )
    return parser.parse_args()


async def main():
    setup_logging(logging.INFO)
    logger = logging.getLogger("prady.scripts.train")

    args = parse_args()

    logger.info("======================================")
    logger.info("PRADY TRADER - Model Training")
    logger.info("======================================")

    settings = get_settings()
    logger.info("Testnet: %s", settings.binance_testnet)
    logger.info("Days: %d", args.days)

    if args.symbol:
        logger.info("Training single symbol: %s", args.symbol)
        result = await run_training_pipeline(args.symbol, days=args.days)
        if result["status"] == "ok":
            logger.info("Training complete: %s", result)
        else:
            logger.error("Training failed: %s", result)
            sys.exit(1)
    else:
        logger.info("Training all configured pairs: %s", settings.trading_pairs)
        results = await retrain_all_symbols(days=args.days)
        failed = [s for s, r in results.items() if r["status"] != "ok"]
        if failed:
            logger.warning("Failed symbols: %s", failed)
        else:
            logger.info("All models trained successfully")
        for symbol, result in results.items():
            logger.info("  %s: %s", symbol, result["status"])


if __name__ == "__main__":
    asyncio.run(main())
