#!/usr/bin/env python3
"""
PRADY TRADER — Live Smoke Test.
Calls every API endpoint and verifies every component connection.
Run: python scripts/live_smoke_test.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results = []


def record(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    results.append((name, ok, detail))
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))


async def probe_binance_rest():
    print("\n=== 1. Binance REST API ===")
    from data.binance_client import get_binance_client
    client = get_binance_client()

    try:
        ticker = client.get_ticker_price("BTCUSDT")
        price = float(ticker.get("lastPrice", 0) or ticker.get("price", 0))
        record("Binance ticker", price > 0, f"${price:.2f}")
    except Exception as e:
        record("Binance ticker", False, str(e))

    try:
        klines = client.get_klines(symbol="BTCUSDT", interval="1h", limit=5)
        record("Binance klines", len(klines) == 5, f"{len(klines)} candles")
    except Exception as e:
        record("Binance klines", False, str(e))

    try:
        oi = client.get_open_interest(symbol="BTCUSDT")
        record("Binance open interest", float(oi.get("openInterest", 0)) > 0,
               f"OI={oi.get('openInterest', 'N/A')}")
    except Exception as e:
        record("Binance open interest", False, str(e))

    try:
        fr = client.get_funding_rate(symbol="BTCUSDT")
        record("Binance funding rate", len(fr) > 0, f"rate={fr[0]['fundingRate']}")
    except Exception as e:
        record("Binance funding rate", False, str(e))

    try:
        book = client.get_order_book(symbol="BTCUSDT", limit=5)
        record("Binance order book", len(book.get("bids", [])) > 0,
               f"{len(book.get('bids', []))} bids")
    except Exception as e:
        record("Binance order book", False, str(e))


async def probe_coingecko():
    print("\n=== 2. CoinGecko API ===")
    from data.free_apis import async_fetch_coingecko_price, async_fetch_coingecko_global

    try:
        price = await async_fetch_coingecko_price("bitcoin")
        btc_price = price.get("bitcoin", {}).get("usd", 0) if price else 0
        record("CoinGecko price", btc_price > 0,
               f"${btc_price:.2f}" if btc_price else "empty")
    except Exception as e:
        record("CoinGecko price", False, str(e))

    try:
        g = await async_fetch_coingecko_global()
        dom = g.get("btc_dominance", 0) if g else 0
        record("CoinGecko global", dom > 0, f"BTC dom={dom:.1f}%")
    except Exception as e:
        record("CoinGecko global", False, str(e))


async def probe_fear_greed():
    print("\n=== 3. Fear & Greed Index ===")
    from data.free_apis import async_fetch_fear_greed

    try:
        fng = await async_fetch_fear_greed()
        val = fng.get("value", 0) if fng else 0
        record("Fear & Greed", val > 0, f"value={val}")
    except Exception as e:
        record("Fear & Greed", False, str(e))


async def probe_news_apis():
    print("\n=== 4. News APIs ===")
    from data.free_apis import (
        async_fetch_all_news,
        async_fetch_yahoo_finance_news,
        async_fetch_yahoo_finance_prices,
    )

    try:
        yahoo_prices = await async_fetch_yahoo_finance_prices(["BTC-USD"])
        btc_price = yahoo_prices.get("BTC-USD", {}).get("price", 0) if yahoo_prices else 0
        record("Yahoo Finance price", btc_price > 0,
               f"${btc_price:.2f}" if btc_price else "empty")
    except Exception as e:
        record("Yahoo Finance price", False, str(e))

    try:
        yahoo_news = await async_fetch_yahoo_finance_news(["BTC-USD"], max_per_symbol=3)
        record("Yahoo Finance news", len(yahoo_news) > 0, f"{len(yahoo_news)} articles")
    except Exception as e:
        record("Yahoo Finance news", False, str(e))

    try:
        articles = await async_fetch_all_news()
        providers = sorted({a.get("_provider", "unknown") for a in articles})
        detail = f"{len(articles)} articles from {', '.join(providers)}" if articles else "0 articles"
        record("News aggregation", len(articles) > 0, detail)
    except Exception as e:
        record("News aggregation", False, str(e))


async def probe_cryptocompare():
    print("\n=== 5. CryptoCompare Social ===")
    from data.free_apis import async_fetch_cryptocompare_social

    try:
        social = await async_fetch_cryptocompare_social(1182)  # BTC
        record("CryptoCompare social", social is not None,
               f"reddit_active={social.get('reddit_active', 'N/A')}" if social else "empty")
    except Exception as e:
        record("CryptoCompare social", False, str(e))


async def probe_bitquery():
    print("\n=== 6. Bitquery Whale Transfers ===")
    from data.free_apis import async_fetch_bitquery_whale_transfers

    try:
        whales = await async_fetch_bitquery_whale_transfers(limit=5)
        record("Bitquery whales", whales is not None,
               f"{len(whales)} transfers" if whales else "empty/none")
    except Exception as e:
        record("Bitquery whales", False, str(e))


async def probe_blockchain():
    print("\n=== 7. Blockchain.info ===")
    from data.free_apis import async_fetch_blockchain_mempool, async_fetch_blockchain_stats

    try:
        mempool = await async_fetch_blockchain_mempool()
        record("Blockchain mempool", mempool is not None,
               f"size={mempool.get('n_tx', 'N/A')}" if mempool else "empty")
    except Exception as e:
        record("Blockchain mempool", False, str(e))

    try:
        stats = await async_fetch_blockchain_stats()
        record("Blockchain stats", stats is not None,
               f"hash_rate={stats.get('hash_rate', 'N/A')}" if stats else "empty")
    except Exception as e:
        record("Blockchain stats", False, str(e))


async def probe_taapi():
    print("\n=== 8. TAAPI.IO ===")
    from data.crypto_indicators_api import async_fetch_taapi_rsi

    try:
        rsi = await async_fetch_taapi_rsi("BTC/USDT", "1h")
        record("TAAPI RSI", rsi is not None, f"RSI={rsi}" if rsi else "empty/rate-limited")
    except Exception as e:
        record("TAAPI RSI", False, str(e))


async def probe_freecrypto():
    print("\n=== 9. FreeCryptoAPI ===")
    from data.freecrypto_api import (
        get_live_data, get_fear_greed, get_technical_analysis,
        get_top_coins, get_breakouts, get_news,
    )

    try:
        data = await get_live_data("BTC")
        symbols = data.get("symbols") if isinstance(data, dict) else None
        symbol_count = len(symbols) if isinstance(symbols, list) else 0
        record(
            "FreeCrypto live data",
            symbol_count > 0,
            f"{symbol_count} symbol(s)" if symbol_count else "empty",
        )
    except Exception as e:
        record("FreeCrypto live data", False, str(e))

    try:
        fng = await get_fear_greed()
        record("FreeCrypto fear/greed", fng is not None,
               str(fng)[:80] if fng else "empty")
    except Exception as e:
        record("FreeCrypto fear/greed", False, str(e))

    try:
        ta = await get_technical_analysis("BTC")
        record("FreeCrypto TA", ta is not None,
               str(ta)[:80] if ta else "empty")
    except Exception as e:
        record("FreeCrypto TA", False, str(e))

    try:
        top = await get_top_coins(5)
        record("FreeCrypto top coins", top is not None,
               f"{len(top)} coins" if isinstance(top, list) else str(type(top)))
    except Exception as e:
        record("FreeCrypto top coins", False, str(e))

    try:
        brk = await get_breakouts()
        record("FreeCrypto breakouts", brk is not None,
               str(brk)[:80] if brk else "empty")
    except Exception as e:
        record("FreeCrypto breakouts", False, str(e))

    try:
        news = await get_news(limit=5)
        record("FreeCrypto news", news is not None,
               f"{len(news)} articles" if isinstance(news, list) else str(type(news)))
    except Exception as e:
        record("FreeCrypto news", False, str(e))


async def probe_coincodex():
    print("\n=== 10. CoinCodex Prediction ===")
    from data.crypto_indicators_api import async_fetch_coincodex_prediction

    try:
        pred = await async_fetch_coincodex_prediction("bitcoin")
        record("CoinCodex prediction", pred is not None,
               str(pred)[:80] if pred else "empty")
    except Exception as e:
        record("CoinCodex prediction", False, str(e))


async def probe_multi_exchange():
    print("\n=== 11. Multi-Exchange Price ===")
    from data.crypto_indicators_api import async_fetch_multi_exchange_price

    try:
        prices = await async_fetch_multi_exchange_price("BTC")
        record("Multi-exchange prices", prices is not None and len(prices) > 0,
               f"{len(prices)} exchanges" if prices else "empty")
    except Exception as e:
        record("Multi-exchange prices", False, str(e))


async def probe_sentiment():
    print("\n=== 12. Sentiment Pipeline ===")
    from data.sentiment_feeds import get_aggregated_news_sentiment

    try:
        score = await get_aggregated_news_sentiment()
        record("VADER sentiment", score is not None, f"score={score}")
    except Exception as e:
        record("VADER sentiment", False, str(e))


def test_redis():
    print("\n=== 13. Redis Connection ===")
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379)
        r.ping()
        r.set("smoke_test", "ok")
        val = r.get("smoke_test").decode()
        record("Redis ping+read", val == "ok", "connected")
    except Exception as e:
        record("Redis ping+read", False, str(e))


def test_postgres():
    print("\n=== 14. PostgreSQL Connection ===")
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=5433, dbname="prady_trader",
            user="trader", password="password",
        )
        cur = conn.cursor()
        cur.execute("SELECT version()")
        ver = cur.fetchone()[0][:50]
        conn.close()
        record("PostgreSQL", True, ver)
    except Exception as e:
        record("PostgreSQL", False, str(e))


def test_ollama():
    print("\n=== 15. Ollama LLM ===")
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            record("Ollama API", len(models) > 0, f"models={models}")
    except Exception as e:
        record("Ollama API", False, str(e))


async def probe_agents():
    print("\n=== 16. Agent Signal Generation ===")
    from agents.oracle_agent import OracleAgent
    from agents.sentinel_agent import SentinelAgent
    from agents.oracle_extended_agent import OracleExtendedAgent

    # Oracle
    try:
        oracle = OracleAgent()
        sig = await oracle.run("BTCUSDT")
        record("OracleAgent", sig.direction in ("LONG", "SHORT", "NEUTRAL"),
               f"dir={sig.direction} conf={sig.confidence:.2f} score={sig.score:.1f}")
    except Exception as e:
        record("OracleAgent", False, str(e))

    # Sentinel
    try:
        sentinel = SentinelAgent()
        sig = await sentinel.run("BTCUSDT")
        record("SentinelAgent", sig.direction in ("LONG", "SHORT", "NEUTRAL"),
               f"dir={sig.direction} conf={sig.confidence:.2f} score={sig.score:.1f}")
    except Exception as e:
        record("SentinelAgent", False, str(e))

    # OracleExtended
    try:
        oext = OracleExtendedAgent()
        sig = await oext.run("BTCUSDT")
        record("OracleExtendedAgent", sig.direction in ("LONG", "SHORT", "NEUTRAL"),
               f"dir={sig.direction} conf={sig.confidence:.2f} score={sig.score:.1f}")
    except Exception as e:
        record("OracleExtendedAgent", False, str(e))


async def probe_council():
    print("\n=== 17. Council Vote (Full Pipeline) ===")
    from council.orchestrator import CouncilOrchestrator

    try:
        orch = CouncilOrchestrator()
        decision = await orch.run_cycle("BTCUSDT")
        record("Council vote", decision.action in ("LONG", "SHORT", "HOLD"),
               f"action={decision.action} score={decision.weighted_score:.1f} "
               f"conf={decision.confidence:.2f} veto={decision.veto}")
    except Exception as e:
        record("Council vote", False, str(e))


async def probe_strategies():
    print("\n=== 18. Strategy Execution ===")
    from execution.strategies import ALL_STRATEGIES

    for strat in ALL_STRATEGIES:
        try:
            sig = await strat("BTCUSDT")
            record(f"Strategy: {sig.name}", sig.direction in ("LONG", "SHORT", "NEUTRAL"),
                   f"dir={sig.direction} conf={sig.confidence:.2f} score={sig.score:.1f}")
        except Exception as e:
            record(f"Strategy: {strat.__name__}", False, str(e))


def test_settings():
    print("\n=== 19. Settings & Config ===")
    from config.settings import get_settings

    s = get_settings()
    api_checks = [
        ("binance_api_key", s.binance_api_key),
        ("coingecko_api_key", s.coingecko_api_key),
        ("news_api_key", s.news_api_key),
        ("newsdata_api_key", s.newsdata_api_key),
        ("cryptocompare_api_key", s.cryptocompare_api_key),
        ("coinapi_key", s.coinapi_key),
        ("bitquery_api_key", s.bitquery_api_key),
        ("taapi_secret", s.taapi_secret),
        ("freecrypto_api_key", s.freecrypto_api_key),
    ]

    for name, val in api_checks:
        has_val = bool(val and len(val) > 3)
        record(f"Setting: {name}", has_val, "configured" if has_val else "EMPTY")

    record(
        "Trading mode",
        s.trading_mode in ("paper", "testnet", "live"),
        f"{s.trading_mode} (execution={s.execution_environment})",
    )
    record("Database URL", bool(s.database_url), s.database_url[:30] + "...")
    record("Redis URL", bool(s.redis_url), s.redis_url[:20] + "..." if s.redis_url else "empty")


async def main():
    print("=" * 65)
    print("  PRADY TRADER — Live Smoke Test (All APIs + Components)")
    print("=" * 65)

    t0 = time.time()

    # Sync tests
    test_settings()
    test_redis()
    test_postgres()
    test_ollama()

    # Async tests
    await probe_binance_rest()
    await probe_coingecko()
    await probe_fear_greed()
    await probe_news_apis()
    await probe_cryptocompare()
    await probe_bitquery()
    await probe_blockchain()
    await probe_taapi()
    await probe_freecrypto()
    await probe_coincodex()
    await probe_multi_exchange()
    await probe_sentiment()
    await probe_agents()
    await probe_strategies()

    # Full pipeline
    await probe_council()

    elapsed = time.time() - t0
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    failed = total - passed

    print("\n" + "=" * 65)
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed  ({elapsed:.1f}s)")
    print("=" * 65)

    if failed:
        print("\nFailed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  [X] {name}: {detail}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
