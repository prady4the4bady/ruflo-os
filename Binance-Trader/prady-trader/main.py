#!/usr/bin/env python3
"""
PRADY TRADER — Main entry point.
Wires together all subsystems: data feeds, council orchestrator,
scheduler, and graceful shutdown.

Usage:
    python main.py                    # default: configured runtime mode
    python main.py --mode testnet     # Binance Spot Testnet execution
    python main.py --mode live        # live trading (DANGER)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import apply_runtime_mode, get_settings, setup_logging
from config.constants import COUNCIL_CYCLE_SEC

logger: logging.Logger = None  # type: ignore[assignment]


async def run_trading_system(mode: str | None = None):
    """
    Main async loop that starts all subsystems.
    1. Initialise settings and logging
    2. Start data feeds (MarketFeed + OrderBookFeed)
    3. Start Scheduler with default tasks
    4. Start CouncilOrchestrator loop
    5. Wait for shutdown signal
    """
    global logger

    log = setup_logging()
    logger = logging.getLogger("prady.main")
    settings = apply_runtime_mode(mode or get_settings().trading_mode, persist=False)

    log.info("=" * 70)
    log.info("   PRADY TRADER — AI Agent Council Trading System")
    log.info("=" * 70)
    log.info("Mode:       %s", settings.mode_label)
    log.info("Execution:  %s", settings.execution_environment.upper())
    log.info("Pairs:      %s", settings.trading_pairs)
    log.info("Leverage:   %dx", settings.default_leverage)
    log.info("Max risk:   %s%%", settings.max_risk_per_trade * 100)
    log.info("Min conf:   %s", settings.min_confidence)
    log.info("Council:    every %ds", COUNCIL_CYCLE_SEC)
    log.info("=" * 70)

    if settings.is_live:
        logger.warning("⚠ LIVE TRADING MODE — Real money at risk!")
        logger.warning("Waiting 5 seconds... Press Ctrl+C to abort.")
        await asyncio.sleep(5)
    elif settings.is_testnet:
        logger.info("Testnet mode enabled — orders route to Binance Spot Testnet")
    else:
        logger.info("Paper mode enabled — orders remain simulated")

    # ── Initialise subsystems ────────────────────────────────
    from data.market_feed import MarketFeed
    from data.orderbook_feed import OrderBookFeed
    from council.orchestrator import TradingOrchestrator
    from utils.scheduler import Scheduler, setup_default_tasks
    from utils.telegram_bot import get_telegram_bot

    market_feed = MarketFeed()
    orderbook_feed = OrderBookFeed()
    orchestrator = TradingOrchestrator()
    scheduler = Scheduler()
    setup_default_tasks(scheduler)
    telegram = get_telegram_bot()

    # ── Shutdown event ───────────────────────────────────────
    shutdown_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_name, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # ── Start all subsystems ─────────────────────────────────
    logger.info("Starting data feeds...")
    await market_feed.start()
    await orderbook_feed.start()
    logger.info("Data feeds running")

    # Let feeds warm up
    logger.info("Warming up data feeds (10s)...")
    await asyncio.sleep(10)

    logger.info("Starting scheduler...")
    scheduler_task = asyncio.create_task(scheduler.start())

    logger.info("Starting trading orchestrator...")
    orchestrator_task = asyncio.create_task(orchestrator.run())

    await telegram.send_system_status({
        "status": "started",
        "mode": settings.trading_mode,
        "pairs": settings.trading_pairs,
    })

    logger.info("All systems online. PRADY TRADER is running.")

    # ── Wait for shutdown ────────────────────────────────────
    try:
        await shutdown_event.wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Keyboard interrupt received")

    # ── Graceful shutdown ────────────────────────────────────
    logger.info("Shutting down PRADY TRADER...")

    orchestrator.stop()
    scheduler.stop()

    await market_feed.stop()
    await orderbook_feed.stop()

    await telegram.send_system_status({
        "status": "stopped",
        "mode": settings.trading_mode,
    })

    # Wait for tasks to finish
    tasks = [orchestrator_task, scheduler_task]
    for t in tasks:
        try:
            await asyncio.wait_for(t, timeout=5.0)
        except asyncio.TimeoutError:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        except asyncio.CancelledError:
            pass

    logger.info("PRADY TRADER stopped. Goodbye.")


def main():
    parser = argparse.ArgumentParser(description="PRADY TRADER — AI Agent Council Trading System")
    parser.add_argument("--mode", choices=["paper", "testnet", "live"], help="Runtime mode to launch")
    parser.add_argument("--live", action="store_true", help="Legacy alias for --mode live")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.live and args.mode and args.mode != "live":
        parser.error("--live cannot be combined with --mode set to paper or testnet")

    selected_mode = "live" if args.live else args.mode

    global logger
    log = setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    logger = logging.getLogger("prady.main")

    try:
        asyncio.run(run_trading_system(mode=selected_mode))
    except KeyboardInterrupt:
        logger.info("Interrupted.")
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
