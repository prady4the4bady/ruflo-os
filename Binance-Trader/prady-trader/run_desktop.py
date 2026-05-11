#!/usr/bin/env python3
"""
PRADY TRADER — Desktop Application Launcher.
Native PyQt6 desktop app — no web server, no browser overhead.

Usage:
    python run_desktop.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from config.settings import setup_logging

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main():
    setup_logging(logging.INFO)
    logger = logging.getLogger("prady.desktop.launcher")

    logger.info("==========================================================")
    logger.info("PRADY TRADER | Native Desktop App")
    logger.info("Starting PyQt6 GUI...")
    logger.info("==========================================================")

    try:
        from desktop.app import run_app

        run_app()
    except Exception:
        logger.exception("Desktop application failed during startup")
        raise


if __name__ == "__main__":
    main()
