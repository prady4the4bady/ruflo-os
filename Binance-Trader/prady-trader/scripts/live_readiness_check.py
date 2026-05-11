#!/usr/bin/env python3
"""
PRADY TRADER — Live Readiness Check.
Run this BEFORE switching from paper to live trading.
Validates every prerequisite for real-money trading.

Usage: python scripts/live_readiness_check.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")
from execution.capital_guard import load_rehearsal_summary


def main():
    from config.settings import get_settings

    settings = get_settings()

    print("=" * 60)
    print("  PRADY TRADER — Live Readiness Check")
    print("=" * 60)
    print()

    passed = 0
    failed = 0
    warnings_list = []

    def check(num, total, name, result, msg, fatal=True):
        nonlocal passed, failed
        status = "PASS" if result else ("FAIL" if fatal else "WARN")
        icon = "✅" if result else ("❌" if fatal else "⚠️")
        print(f"  [{num:02d}/{total:02d}] {icon} {status}  {name}")
        if msg:
            print(f"           {msg}")
        if result:
            passed += 1
        elif fatal:
            failed += 1
        else:
            warnings_list.append(name)

    total = 15

    staging_ok = settings.trading_mode in ("paper", "testnet")
    check(
        1,
        total,
        "Trading Mode",
        staging_ok,
        (
            f"Currently: {settings.trading_mode.upper()} — valid rehearsal mode before live cutover"
            if staging_ok
            else f"Currently: {settings.trading_mode.upper()} — switch back to paper or testnet before running live readiness"
        ),
    )

    key_ok = bool(
        settings.trading_binance_api_key
        and settings.trading_binance_api_key != "your_binance_api_key"
    )
    check(
        2,
        total,
        "Binance Execution API Key",
        key_ok,
        "Set the execution key for the current environment in .env" if not key_ok else "Key configured",
    )

    secret_ok = bool(
        settings.trading_binance_secret_key
        and settings.trading_binance_secret_key != "your_binance_secret_key"
    )
    check(
        3,
        total,
        "Binance Execution Secret",
        secret_ok,
        "Set the execution secret for the current environment in .env" if not secret_ok else "Secret configured",
    )

    client = None
    try:
        from data.binance_client import BinanceClientWrapper

        client = BinanceClientWrapper()
        ticker = client.get_ticker_price("BTCUSDT")
        price = float(ticker.get("lastPrice", 0))
        check(4, total, "Binance API Connectivity", price > 0, f"BTC @ ${price:,.2f}")
    except Exception as exc:
        check(4, total, "Binance API Connectivity", False, str(exc))

    if key_ok and secret_ok and client is not None:
        try:
            balance = client.get_usdt_balance()
            check(
                5,
                total,
                "Binance Account Access",
                True,
                f"Execution free USDT: ${float(balance):,.2f} ({settings.execution_environment} spot)",
            )
        except Exception as exc:
            check(5, total, "Binance Account Access", False, str(exc))
    else:
        check(5, total, "Binance Account Access", False, "Needs API keys first")

    try:
        from data.data_store import DataStore

        store = DataStore()
        if store._redis:
            store._redis.ping()
            check(6, total, "Redis Connection", True, "Connected")
        else:
            check(6, total, "Redis Connection", False, "Not connected", fatal=False)
    except Exception as exc:
        check(6, total, "Redis Connection", False, str(exc), fatal=False)

    model_files = (
        list((ROOT / "models").glob("**/*.pkl"))
        + list((ROOT / "models").glob("**/*.pt"))
        + list((ROOT / "models").glob("**/*.json"))
    )
    check(
        7,
        total,
        "ML Models Trained",
        len(model_files) > 0,
        f"{len(model_files)} model files found" if model_files else "No models — run train_models.py",
        fatal=False,
    )

    from execution.trade_journal import TradeJournal

    rehearsal_history = load_rehearsal_summary(ROOT, journal=TradeJournal())
    journal_error = str(rehearsal_history.get("journal_error", "") or "")
    check(
        8,
        total,
        "Rehearsal Trading History",
        bool(rehearsal_history.get("available")) and int(rehearsal_history.get("trades", 0) or 0) > 0,
        (
            f"Source={rehearsal_history['source']}, mode={rehearsal_history['mode']}, trades={rehearsal_history['trades']}"
            if rehearsal_history.get("available")
            else (
                f"No validated paper/testnet history found" + (f" (journal: {journal_error})" if journal_error else "")
            )
        ),
        fatal=True,
    )

    if rehearsal_history.get("available"):
        trades = int(rehearsal_history.get("trades", 0) or 0)
        win_rate = float(rehearsal_history.get("win_rate", 0) or 0.0)
        pnl = float(rehearsal_history.get("pnl", 0) or 0.0)
        min_trades = int(settings.live_min_rehearsal_trades)
        min_win_rate = float(settings.live_min_rehearsal_win_rate)
        positive_pnl_ok = pnl > 0 if settings.live_require_positive_rehearsal_pnl else pnl >= 0
        check(
            9,
            total,
            "Rehearsal Performance Review",
            trades >= min_trades and win_rate >= min_win_rate and positive_pnl_ok,
            (
                f"Source={rehearsal_history['source']}, Trades={trades}/{min_trades}, "
                f"WinRate={win_rate:.0%}/{min_win_rate:.0%}, PnL=${pnl:,.2f}"
            ),
        )
    else:
        check(9, total, "Rehearsal Performance Review", False, "No rehearsal history to review")

    risk_ok = (
        float(settings.max_risk_per_trade) <= 0.05
        and float(settings.max_daily_loss) <= 0.10
        and settings.default_leverage <= 10
    )
    check(
        10,
        total,
        "Risk Settings",
        risk_ok,
        (
            f"Risk={float(settings.max_risk_per_trade) * 100:.0f}%, "
            f"DailyLoss={float(settings.max_daily_loss) * 100:.0f}%, "
            f"Leverage={settings.default_leverage}x"
        ),
    )

    conf_ok = float(settings.min_confidence) >= 0.80
    check(
        11,
        total,
        "Min Confidence Threshold",
        conf_ok,
        f"MinConf={float(settings.min_confidence):.2f}" + (" (too low for live!)" if not conf_ok else ""),
    )

    check(
        12,
        total,
        "Execution Environment",
        True,
        f"BINANCE_TESTNET={settings.binance_testnet} — execution routed to {settings.execution_environment} spot",
    )

    tg_ok = False
    tg_message = "Not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, then run scripts/telegram_delivery_check.py"
    try:
        from utils.telegram_bot import get_telegram_bot

        telegram_status = get_telegram_bot().validate_connection_sync(send_test=False)
        tg_ok = bool(telegram_status.get("ok"))
        tg_message = str(telegram_status.get("message", tg_message))
    except Exception as exc:
        tg_message = f"Telegram validation failed: {exc}"

    check(
        13,
        total,
        "Telegram Notifications",
        tg_ok,
        tg_message,
        fatal=False,
    )

    db_ok = "postgresql" in settings.database_url or "sqlite" in settings.database_url
    check(
        14,
        total,
        "Database",
        db_ok,
        f"Using: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'SQLite'}",
    )

    check(
        15,
        total,
        "Max Concurrent Positions",
        settings.max_concurrent_positions <= 5,
        f"Max={settings.max_concurrent_positions}",
    )

    print()
    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed, {len(warnings_list)} warnings")
    print("=" * 60)

    if failed > 0:
        print()
        print("  ❌ NOT READY for live trading. Fix the failures above.")
        print()
        print("  Transition checklist:")
        print("  1. Fix all FAIL items above")
        print(f"  2. Accumulate at least {int(settings.live_min_rehearsal_trades)} closed rehearsal trades in paper or testnet mode")
        print("  3. Review rehearsal trading results and confirm risk behavior")
        print("  4. Set BINANCE_TESTNET=false in .env when ready for live spot")
        print("  5. Set TRADING_MODE=live in .env")
        print("  6. Ensure live spot credentials are configured for mainnet execution")
        print("  7. Configure Telegram and run scripts/telegram_delivery_check.py --send-test")
        print("  8. Start with small size and verify spot order fills carefully")
        sys.exit(1)

    print()
    print("  ✅ All critical checks passed!")
    print("  When ready, change TRADING_MODE=live in .env")
    sys.exit(0)


if __name__ == "__main__":
    main()
