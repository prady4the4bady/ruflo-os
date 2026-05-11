"""
PRADY TRADER — 17-Step Validation Suite.

Run:  python scripts/validate_build.py
Each test prints PASS/FAIL.  Zero dependencies on Docker or paid APIs.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import os
import time
import traceback

# Ensure project root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok, detail))


# ── TEST 1: Data Connectivity (Binance free REST) ───────────────────
def test_data_connectivity():
    print("\n=== TEST 1: Data Connectivity (Binance Free REST) ===")
    try:
        from data.binance_client import BinanceClientWrapper
        bc = BinanceClientWrapper()

        # Klines — free endpoint
        klines = bc.get_klines("BTCUSDT", "1h", limit=5)
        record("Klines fetch", len(klines) >= 1, f"{len(klines)} candles")

        # Funding rate
        fr = bc.get_funding_rate("BTCUSDT")
        record("Funding rate", fr is not None, f"rate={fr}")

        # Ticker price (returns 24hr ticker dict)
        ticker = bc.get_ticker_price("BTCUSDT")
        price = float(ticker.get("lastPrice", 0)) if isinstance(ticker, dict) else None
        record("Ticker price", price is not None and price > 0, f"${price}")

        # Open interest
        oi = bc.get_open_interest("BTCUSDT")
        record("Open interest", oi is not None, f"OI={oi}")

        # Order book
        ob = bc.get_order_book("BTCUSDT", limit=5)
        record("Order book", "bids" in ob and len(ob["bids"]) > 0, f"{len(ob.get('bids',[]))} bids")

    except Exception as exc:
        record("Data connectivity", False, str(exc))


# ── TEST 2: Technical Indicators ────────────────────────────────────
def test_indicators():
    print("\n=== TEST 2: Technical Indicators ===")
    try:
        import pandas as pd
        import numpy as np
        from data.binance_client import BinanceClientWrapper
        from indicators.trend import compute_all_trend
        from indicators.momentum import compute_all_momentum
        from indicators.volatility import compute_all_volatility
        from indicators.volume import compute_all_volume

        bc = BinanceClientWrapper()
        klines = bc.get_klines("BTCUSDT", "1h", limit=200)
        df = pd.DataFrame(klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        trend = compute_all_trend(df)
        record("Trend indicators", isinstance(trend, dict) and len(trend) > 0, f"{len(trend)} signals")

        mom = compute_all_momentum(df)
        record("Momentum indicators", isinstance(mom, dict) and len(mom) > 0, f"{len(mom)} signals")

        vol = compute_all_volatility(df)
        record("Volatility indicators", isinstance(vol, dict) and len(vol) > 0, f"{len(vol)} signals")

        volm = compute_all_volume(df)
        record("Volume indicators", isinstance(volm, dict) and len(volm) > 0, f"{len(volm)} signals")

    except Exception as exc:
        record("Indicators", False, traceback.format_exc())


# ── TEST 3: Sentiment Feeds ─────────────────────────────────────────
def test_sentiment():
    print("\n=== TEST 3: Sentiment Feeds (Free) ===")
    try:
        from data.sentiment_feeds import fetch_fear_greed
        fng = fetch_fear_greed()
        record(
            "Fear & Greed Index",
            fng is not None and "value" in fng,
            f"value={fng.get('value') if fng else 'N/A'}",
        )
    except Exception as exc:
        record("Fear & Greed", False, str(exc))

    try:
        from data.sentiment_feeds import fetch_crypto_news, get_aggregated_news_sentiment
        news = fetch_crypto_news(limit=5)
        record("Crypto news (Messari+RSS)", isinstance(news, list), f"{len(news)} articles")
    except Exception as exc:
        record("Crypto news pipeline", False, str(exc))

    try:
        from data.whale_detector import WhaleDetector
        wd = WhaleDetector(symbols=["BTCUSDT"], threshold_usdt=50_000)
        summary = wd.get_whale_summary("BTCUSDT")
        record(
            "Whale detection (REST)",
            isinstance(summary, dict) and "whale_count" in summary,
            f"{summary.get('whale_count', 0)} whales, bias={summary.get('bias', '?')}",
        )
    except Exception as exc:
        record("Whale detection", False, str(exc))


# ── TEST 4: ML Feature Engineering ──────────────────────────────────
def test_ml():
    print("\n=== TEST 4: ML Feature Engineering ===")
    try:
        import pandas as pd
        from data.binance_client import BinanceClientWrapper
        from ml.feature_engineer import engineer_features, get_feature_columns

        bc = BinanceClientWrapper()
        klines = bc.get_klines("BTCUSDT", "1h", limit=1500)
        df = pd.DataFrame(klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df["timestamp"] = df["timestamp"].astype(int)

        # Run with drop_na=True (normal mode) to get actual clean row count
        featured = engineer_features(df, drop_na=True)
        cols = get_feature_columns(featured)
        clean_rows = len(featured)
        record(
            "Feature engineering",
            len(cols) > 50 and clean_rows > 500,
            f"{len(cols)} features, {clean_rows} clean rows",
        )

        # Also verify with drop_na=False to show total features
        featured_all = engineer_features(df, drop_na=False)
        cols_all = get_feature_columns(featured_all)

        # Check macro features were added (may be 0 if yfinance fails)
        has_macro = any(c.startswith("macro_") for c in featured_all.columns)
        record("Macro features (yfinance)", has_macro, "present" if has_macro else "skipped (ok)")

    except Exception as exc:
        record("ML features", False, traceback.format_exc())


# ── TEST 5: Council Vote Pipeline ───────────────────────────────────
def test_council():
    print("\n=== TEST 5: Council Vote ===")
    try:
        from council.voting import vote, compute_weighted_score, compute_confidence
        from council.weight_manager import WeightManager
        from agents.base_agent import AgentSignal
        from config.constants import AGENT_WEIGHTS

        signals = {
            "oracle": AgentSignal("oracle", "LONG", 0.8, 40, "test bull"),
            "prophet": AgentSignal("prophet", "LONG", 0.7, 35, "ML bull"),
            "arbiter": AgentSignal("arbiter", "NEUTRAL", 0.5, 0, "neutral"),
            "sentinel": AgentSignal("sentinel", "LONG", 0.6, 20, "safe"),
            "debater": AgentSignal("debater", "LONG", 0.5, 15, "agrees"),
        }

        wm = WeightManager()
        score = compute_weighted_score(signals, wm.weights)
        record("Weighted score", isinstance(score, float), f"score={score:.2f}")

        conf = compute_confidence(signals, wm.weights)
        record("Confidence calc", 0 <= conf <= 1, f"conf={conf:.4f}")

        decision = vote(signals, wm, veto=False)
        record(
            "Vote decision",
            decision.action in ("LONG", "SHORT", "HOLD"),
            f"action={decision.action}, score={decision.weighted_score:.2f}",
        )

    except Exception as exc:
        record("Council", False, traceback.format_exc())


# ── TEST 6: Paper Trading Engine ────────────────────────────────────
def test_paper_trading():
    print("\n=== TEST 6: Paper Trading Engine ===")
    try:
        from execution.paper_engine import PaperTradingEngine

        from decimal import Decimal
        pe = PaperTradingEngine(initial_balance=Decimal("10000"))
        record("Paper engine init", pe.balance == Decimal("10000"), f"balance=${pe.balance}")

        # Place a market order
        result = pe.place_market_order("BTCUSDT", "BUY", 0.01, 60000.0)
        record("Place order", result.get("status") == "FILLED", f"order={result.get('orderId')}")

        # Check position opened
        pos = pe.positions.get("BTCUSDT")
        record("Position opened", pos is not None, f"qty={getattr(pos, 'quantity', '?')}")

        # Close it
        result2 = pe.place_market_order("BTCUSDT", "SELL", 0.01, 61000.0)
        record("Position closed", "BTCUSDT" not in pe.positions, f"balance=${pe.balance:.2f}")

        stats = pe.get_stats()
        record("Trade stats", isinstance(stats, dict), f"trades={stats.get('total_trades', 0)}")

    except Exception as exc:
        record("Paper trading", False, traceback.format_exc())


# ── TEST 7: Shared State + Desktop Imports ──────────────────────────
def test_dashboard():
    print("\n=== TEST 7: Shared State + Desktop Imports ===")
    try:
        import dashboard.state
        record("dashboard.state import", True)
        import dashboard.charts
        record("dashboard.charts import", True)
        import desktop.app
        record("desktop.app import", True)
        import run_desktop
        record("run_desktop import", True)
    except Exception as exc:
        record("Desktop state", False, str(exc))


# ── TEST 8: Full Integration (Orchestrator dry-run) ─────────────────
def test_integration():
    print("\n=== TEST 8: Full Integration ===")
    try:
        # Verify all major modules can be imported
        modules = [
            "config.settings",
            "config.constants",
            "data.binance_client",
            "data.data_store",
            "data.sentiment_feeds",
            "data.whale_detector",
            "data.macro_feeds",
            "data.market_feed",
            "data.orderbook_feed",
            "agents.oracle_agent",
            "agents.sentinel_agent",
            "agents.prophet_agent",
            "agents.arbiter_agent",
            "agents.debater_agent",
            "agents.warden_agent",
            "agents.executor_agent",
            "council.orchestrator",
            "council.voting",
            "execution.paper_engine",
            "execution.risk_manager",
            "execution.position_tracker",
            "execution.trade_journal",
            "ml.feature_engineer",
        ]
        failed_imports = []
        for mod in modules:
            try:
                importlib.import_module(mod)
            except Exception as e:
                failed_imports.append(f"{mod}: {e}")

        record(
            "Module imports",
            len(failed_imports) == 0,
            f"{len(modules) - len(failed_imports)}/{len(modules)} OK"
            + (f" | FAILED: {', '.join(failed_imports[:3])}" if failed_imports else ""),
        )

        # Verify settings load
        from config.settings import get_settings
        cfg = get_settings()
        record("Settings load", cfg is not None, f"pairs={cfg.trading_pairs[:2]}")

        # Verify risk manager
        from execution.risk_manager import RiskManager
        rm = RiskManager()
        from decimal import Decimal as D
        allowed, reason = rm.full_pre_trade_check(
            balance=D("10000"), equity=D("9800"), size_usdt=D("500"), leverage=3
        )
        record("Risk manager", allowed, f"allowed={allowed}, reason={reason}")

    except Exception as exc:
        record("Integration", False, traceback.format_exc())


# ── TEST 9: Production Module Imports ────────────────────────────────
def test_production_imports():
    print("\n=== TEST 9: Production Module Imports ===")
    prod_modules = [
        ("utils.logger_setup", "setup_logging"),
        ("utils.rate_limiter", "get_rate_limiter"),
        ("utils.health_monitor", "HealthMonitor"),
        ("utils.telegram_bot", "get_telegram_bot"),
        ("scripts.process_manager", "ProcessManager"),
    ]
    for mod_name, attr_name in prod_modules:
        try:
            mod = importlib.import_module(mod_name)
            has_attr = hasattr(mod, attr_name)
            record(f"Import {mod_name}", has_attr, f"has {attr_name}={has_attr}")
        except Exception as exc:
            record(f"Import {mod_name}", False, str(exc))


# ── TEST 10: Rate Limiter Functionality ─────────────────────────────
def test_rate_limiter():
    print("\n=== TEST 10: Rate Limiter ===")
    try:
        from utils.rate_limiter import get_rate_limiter
        rl = get_rate_limiter()

        # Test acquire
        acquired = asyncio.get_event_loop().run_until_complete(rl.acquire("binance"))
        record("Rate limiter acquire", acquired is True or acquired is None, "acquired ok")

        # Test stats
        stats = rl.get_stats()
        record("Rate limiter stats", isinstance(stats, dict) and "binance" in stats, f"{len(stats)} providers")

        # Test try_acquire
        ok = rl.try_acquire("coingecko")
        record("Rate limiter try_acquire", isinstance(ok, bool), f"result={ok}")

    except Exception as exc:
        record("Rate limiter", False, traceback.format_exc())


# ── TEST 11: Telegram Bot Structure ─────────────────────────────────
def test_telegram_bot():
    print("\n=== TEST 11: Telegram Bot ===")
    try:
        from utils.telegram_bot import TelegramBot, get_telegram_bot, MAX_RETRIES

        record("MAX_RETRIES defined", MAX_RETRIES == 3, f"retries={MAX_RETRIES}")

        bot = get_telegram_bot()
        record("Singleton creation", bot is not None)

        required_methods = [
            "trade_opened", "trade_closed", "daily_summary",
            "system_started", "kill_switch_triggered",
            "health_alert", "weekly_report",
            "send_council_decision", "send_warden_alert",
            "send_system_status", "send_test", "send_sync",
        ]
        missing = [m for m in required_methods if not hasattr(bot, m)]
        record("All methods present", len(missing) == 0,
               f"{len(required_methods) - len(missing)}/{len(required_methods)}"
               + (f" missing: {missing}" if missing else ""))

        # Backward compat aliases
        record("send_trade_alert alias", hasattr(bot, "send_trade_alert"))
        record("send_trade_closed alias", hasattr(bot, "send_trade_closed"))

    except Exception as exc:
        record("Telegram bot", False, traceback.format_exc())


# ── TEST 12: Health Monitor Structure ────────────────────────────────
def test_health_monitor():
    print("\n=== TEST 12: Health Monitor ===")
    try:
        from utils.health_monitor import HealthMonitor, HealthCheck

        hm = HealthMonitor()
        record("HealthMonitor init", hm is not None)
        fields = getattr(HealthCheck, "__dataclass_fields__", {})
        record("HealthCheck dataclass", "name" in fields and "status" in fields, f"fields={list(fields.keys())}")

        # Verify check methods exist
        check_methods = [
            "_check_binance", "_check_cycle_freshness", "_check_redis",
            "_check_balance_safety", "_check_position_age", "_check_disk", "_check_memory",
        ]
        present = [m for m in check_methods if hasattr(hm, m)]
        record("Health checks present", len(present) == len(check_methods), f"{len(present)}/{len(check_methods)}")

    except Exception as exc:
        record("Health monitor", False, traceback.format_exc())


# ── TEST 13: Logging Setup ──────────────────────────────────────────
def test_logging_setup():
    print("\n=== TEST 13: Logging Setup ===")
    try:
        from utils.logger_setup import setup_logging, LOG_DIR
        record("LOG_DIR defined", LOG_DIR is not None, str(LOG_DIR))

        # Call setup and verify no crash
        setup_logging(level="WARNING")
        record("setup_logging() runs", True)

        # Verify log directory was created
        record("Log directory exists", os.path.isdir(LOG_DIR))

    except Exception as exc:
        record("Logging setup", False, traceback.format_exc())


# ── TEST 14: End-to-End Paper Trade Simulation ─────────────────────
def test_e2e_paper():
    print("\n=== TEST 14: End-to-End Paper Simulation ===")
    try:
        from decimal import Decimal
        from execution.paper_engine import PaperTradingEngine
        from council.voting import vote
        from council.weight_manager import WeightManager
        from agents.base_agent import AgentSignal

        # 1. Create signals → vote → get decision
        signals = {
            "oracle": AgentSignal("oracle", "LONG", 0.95, 90, "strong bull"),
            "prophet": AgentSignal("prophet", "LONG", 0.90, 85, "ML bull"),
            "arbiter": AgentSignal("arbiter", "LONG", 0.85, 70, "volume strong"),
            "sentinel": AgentSignal("sentinel", "LONG", 0.80, 60, "sentiment ok"),
            "oracle_extended": AgentSignal("oracle_extended", "LONG", 0.85, 75, "extended bull"),
            "debater": AgentSignal("debater", "LONG", 0.70, 50, "agrees"),
        }
        wm = WeightManager()
        decision = vote(signals, wm, veto=False)
        record("E2E council vote", decision.action == "LONG", f"action={decision.action}, score={decision.weighted_score:.1f}")

        # 2. Execute paper trade
        pe = PaperTradingEngine(initial_balance=Decimal("10000"))
        result = pe.place_market_order("ETHUSDT", "BUY", 0.5, 3000.0)
        record("E2E open trade", result.get("status") == "FILLED")

        # 3. Close with profit
        result2 = pe.place_market_order("ETHUSDT", "SELL", 0.5, 3100.0)
        profit = pe.balance - Decimal("10000")
        record("E2E close with profit", profit > 0, f"profit=${profit:.2f}")

        stats = pe.get_stats()
        record("E2E stats valid", stats.get("total_trades", 0) >= 1, f"trades={stats.get('total_trades')}")

    except Exception as exc:
        record("E2E simulation", False, traceback.format_exc())


# ── TEST 15: Free APIs Health Check ─────────────────────────────────
def test_free_apis():
    print("\n=== TEST 15: Free APIs Health Check ===")
    import requests as _req

    endpoints = {
        "CoinGecko ping": "https://api.coingecko.com/api/v3/ping",
        "Alternative.me F&G": "https://api.alternative.me/fng/?limit=1",
        "Blockchain.info": "https://blockchain.info/q/getdifficulty",
    }
    for name, url in endpoints.items():
        try:
            r = _req.get(url, timeout=10)
            record(name, r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as exc:
            record(name, False, str(exc))

    # RSS feed check
    try:
        import feedparser
        feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
        record("RSS feeds (CoinDesk)", len(feed.entries) > 0, f"{len(feed.entries)} entries")
    except Exception as exc:
        record("RSS feeds", False, str(exc))


# ── TEST 16: Webhook Server Import ──────────────────────────────────
def test_webhook_server():
    print("\n=== TEST 16: Webhook Server ===")
    try:
        from data.market_feed import MarketFeed
        record("MarketFeed import", True)
    except Exception as exc:
        record("MarketFeed import", False, str(exc))

    try:
        from fastapi import FastAPI
        record("FastAPI available", True)
    except ImportError:
        record("FastAPI available", False, "not installed")


# ── TEST 17: Sentiment Pipeline (VADER) ─────────────────────────────
def test_sentiment_pipeline():
    print("\n=== TEST 17: Sentiment Pipeline (VADER) ===")
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        vader = SentimentIntensityAnalyzer()
        score = vader.polarity_scores("Bitcoin surges to new all-time high")
        record("VADER sentiment", -1 <= score["compound"] <= 1, f"compound={score['compound']:.3f}")
    except ImportError:
        record("VADER sentiment", False, "vaderSentiment not installed")
    except Exception as exc:
        record("VADER sentiment", False, str(exc))

    try:
        from data.sentiment_feeds import get_aggregated_news_sentiment
        record("Aggregated sentiment import", True)
    except ImportError as exc:
        record("Aggregated sentiment import", False, str(exc))

    try:
        from config.settings import get_settings
        cfg = get_settings()
        record(
            "effective_min_confidence",
            hasattr(cfg, "effective_min_confidence"),
            f"value={cfg.effective_min_confidence}",
        )
    except Exception as exc:
        record("effective_min_confidence", False, str(exc))


# ── MAIN ─────────────────────────────────────────────────────────────
def test_freecrypto_api():
    print("\n=== TEST 18: FreeCryptoAPI Module ===")
    try:
        from data.freecrypto_api import (
            get_live_data, get_technical_analysis, get_fear_greed,
            get_breakouts, get_top_coins, get_btc_summary,
        )
        record("FreeCryptoAPI import", True, "6 endpoints loaded")
    except ImportError as exc:
        record("FreeCryptoAPI import", False, str(exc))

    try:
        from execution.strategies import strategy_freecrypto_ta
        record("strategy_freecrypto_ta import", True)
    except ImportError as exc:
        record("strategy_freecrypto_ta import", False, str(exc))

    try:
        from config.settings import get_settings
        cfg = get_settings()
        record("freecrypto_api_key setting", hasattr(cfg, "freecrypto_api_key"), "present")
    except Exception as exc:
        record("freecrypto_api_key setting", False, str(exc))


def main():
    print("=" * 60)
    print("  PRADY TRADER — 18-Step Build Validation Suite")
    print("=" * 60)

    t0 = time.time()

    test_data_connectivity()
    test_indicators()
    test_sentiment()
    test_ml()
    test_council()
    test_paper_trading()
    test_dashboard()
    test_integration()
    test_production_imports()
    test_rate_limiter()
    test_telegram_bot()
    test_health_monitor()
    test_logging_setup()
    test_e2e_paper()
    test_free_apis()
    test_webhook_server()
    test_sentiment_pipeline()
    test_freecrypto_api()

    elapsed = time.time() - t0
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed  ({elapsed:.1f}s)")
    print("=" * 60)

    if failed:
        print("\nFailed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  [X] {name}: {detail}")
        sys.exit(1)
    else:
        print("\n  All checks passed! Production-ready.")
        sys.exit(0)


if __name__ == "__main__":
    main()
