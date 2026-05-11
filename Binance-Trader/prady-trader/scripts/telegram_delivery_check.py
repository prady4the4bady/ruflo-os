#!/usr/bin/env python3
"""Validate Telegram bot wiring and optionally send a delivery test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Telegram bot configuration for PRADY TRADER")
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send a Telegram delivery test after validating the bot and chat",
    )
    return parser.parse_args()


def main() -> int:
    from utils.telegram_bot import get_telegram_bot

    args = parse_args()
    result = get_telegram_bot().validate_connection_sync(send_test=args.send_test)

    print("=" * 60)
    print("  PRADY TRADER — Telegram Delivery Check")
    print("=" * 60)
    print()
    print(f"Configured: {'YES' if result.get('configured') else 'NO'}")
    print(f"Healthy:    {'YES' if result.get('ok') else 'NO'}")
    print(f"Message:    {result.get('message', 'No message returned')}")

    if result.get("bot_username"):
        print(f"Bot:        @{result['bot_username']}")
    if result.get("chat"):
        print(f"Chat:       {result['chat']}")

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())