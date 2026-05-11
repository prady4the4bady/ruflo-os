"""
PRADY TRADER — Structured logging with loguru.
Five outputs: console, main log, trades log, errors log, JSON structured log.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"


def setup_logging(level: str = "INFO") -> None:
    """Configure loguru with five sinks."""
    LOG_DIR.mkdir(exist_ok=True)

    # Remove default handler
    logger.remove()

    fmt_console = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
        "<level>{message}</level>"
    )
    fmt_file = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    )

    # 1. Console — coloured, INFO+
    logger.add(
        sys.stdout,
        format=fmt_console,
        level=level,
        colorize=True,
    )

    # 2. Main log — all levels, 10 MB rotation, 7 day retention
    logger.add(
        LOG_DIR / "prady_trader.log",
        format=fmt_file,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    # 3. Trades log — only trade-related messages
    logger.add(
        LOG_DIR / "trades.log",
        format=fmt_file,
        level="INFO",
        rotation="5 MB",
        retention="30 days",
        encoding="utf-8",
        filter=lambda record: "trade" in record["name"].lower()
            or "executor" in record["name"].lower()
            or "paper" in record["name"].lower(),
    )

    # 4. Errors log — WARNING+
    logger.add(
        LOG_DIR / "errors.log",
        format=fmt_file,
        level="WARNING",
        rotation="5 MB",
        retention="30 days",
        encoding="utf-8",
    )

    # 5. JSON structured log — for machine parsing
    logger.add(
        LOG_DIR / "structured.jsonl",
        serialize=True,
        level="INFO",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    logger.info("Logging initialised — outputs: console, main, trades, errors, JSON")
