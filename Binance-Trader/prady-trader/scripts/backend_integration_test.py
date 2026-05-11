#!/usr/bin/env python3
"""
PRADY TRADER — Backend Infrastructure Integration Test.
Tests PostgreSQL, Redis, reasoning backends, and dashboard state wiring.
Run with:  python scripts/backend_integration_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

pytestmark = [
    pytest.mark.filterwarnings(
        r"ignore:Type google\._upb\._message\..*uses PyType_Spec.*:DeprecationWarning"
    ),
    pytest.mark.filterwarnings(
        r"ignore:invalid escape sequence '\\\.':SyntaxWarning"
    ),
]

PASS = 0
FAIL = 0
WARN = 0
RESULTS: list[tuple[str, str, str]] = []  # (status, test_name, detail)


def ok(name: str, detail: str = ""):
    global PASS
    PASS += 1
    RESULTS.append(("PASS", name, detail))
    print(f"  ✅ {name}" + (f"  — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    global FAIL
    FAIL += 1
    RESULTS.append(("FAIL", name, detail))
    print(f"  ❌ {name}" + (f"  — {detail}" if detail else ""))


def warn(name: str, detail: str = ""):
    global WARN
    WARN += 1
    RESULTS.append(("WARN", name, detail))
    print(f"  ⚠️  {name}" + (f"  — {detail}" if detail else ""))


# ══════════════════════════════════════════════════════════════
# 1. POSTGRESQL
# ══════════════════════════════════════════════════════════════
def test_postgresql():
    print("\n═══ POSTGRESQL ═══")

    from config.settings import get_settings
    settings = get_settings()

    # 1a. Connection string configured
    db_url = settings.database_url
    if "postgresql" in db_url:
        ok("DB URL configured", db_url.split("@")[-1])
    else:
        fail("DB URL not PostgreSQL", db_url)
        return

    # 1b. Raw psycopg2/SQLAlchemy connection
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url, pool_pre_ping=True, pool_size=2)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        ok("SQLAlchemy connect + SELECT 1")
    except Exception as exc:
        fail("SQLAlchemy connection", str(exc))
        return

    # 1c. TradeJournal schema creation
    try:
        from execution.trade_journal import TradeJournal
        journal = TradeJournal()
        assert journal._available is True
        ok("TradeJournal init (schema created)")
    except Exception as exc:
        fail("TradeJournal init", str(exc))
        return

    # 1d. CRUD — record entry
    try:
        trade_id = journal.record_entry(
            symbol="BTCUSDT_TEST",
            direction="LONG",
            entry_price=50000.0,
            quantity=0.01,
            leverage=5,
            council_score=0.8,
            council_confidence=0.9,
            paper=True,
        )
        assert trade_id > 0
        ok("record_entry", f"trade_id={trade_id}")
    except Exception as exc:
        fail("record_entry", str(exc))
        return

    # 1e. CRUD — record exit
    try:
        journal.record_exit(
            trade_id=trade_id,
            exit_price=51000.0,
            pnl=50.0,
            pnl_pct=2.0,
            exit_reason="test",
        )
        ok("record_exit", f"PnL=$50.00")
    except Exception as exc:
        fail("record_exit", str(exc))

    # 1f. Query recent trades
    try:
        trades = journal.get_recent_trades(10)
        assert any(t["symbol"] == "BTCUSDT_TEST" for t in trades)
        ok("get_recent_trades", f"{len(trades)} trades returned")
    except Exception as exc:
        fail("get_recent_trades", str(exc))

    # 1g. Get stats
    try:
        stats = journal.get_stats()
        assert stats["total_trades"] > 0
        ok("get_stats", f"total_trades={stats['total_trades']}, win_rate={stats.get('win_rate', 0):.2f}")
    except Exception as exc:
        fail("get_stats", str(exc))

    # 1h. Cleanup test data
    try:
        from execution.trade_journal import TradeRecord
        from sqlalchemy.orm import Session
        with journal._session_factory() as session:
            session.query(TradeRecord).filter(TradeRecord.symbol == "BTCUSDT_TEST").delete()
            session.commit()
        ok("Cleanup test data")
    except Exception as exc:
        warn("Cleanup failed (non-critical)", str(exc))


# ══════════════════════════════════════════════════════════════
# 2. REDIS
# ══════════════════════════════════════════════════════════════
def test_redis():
    print("\n═══ REDIS ═══")

    from config.settings import get_settings
    settings = get_settings()

    # 2a. Redis URL configured
    if not settings.redis_url:
        fail("REDIS_URL not configured")
        return
    ok("REDIS_URL configured", settings.redis_url)

    # 2b. Connection + ping
    try:
        import redis
        r = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=3)
        assert r.ping() is True
        ok("Redis PING")
    except Exception as exc:
        fail("Redis connection", str(exc))
        return

    # 2c. SET / GET / TTL
    try:
        test_key = "prady:test:integration"
        r.set(test_key, "hello", ex=10)
        val = r.get(test_key)
        assert val == "hello"
        ttl = r.ttl(test_key)
        assert 0 < ttl <= 10
        r.delete(test_key)
        ok("SET/GET/TTL cycle")
    except Exception as exc:
        fail("SET/GET/TTL", str(exc))

    # 2d. DataStore integration
    try:
        from data.data_store import DataStore
        store = DataStore()
        assert store._redis is not None
        ok("DataStore connected to Redis")
    except Exception as exc:
        fail("DataStore Redis init", str(exc))
        return

    # 2e. DataStore push/get candles
    try:
        test_candle = {"o": 50000, "h": 50100, "l": 49900, "c": 50050, "v": 100, "t": time.time()}
        store.push_candle("BTCUSDT_TEST", "1m", test_candle)
        candles = store.get_candles("BTCUSDT_TEST", "1m")
        assert len(candles) >= 1
        assert candles[-1]["c"] == 50050
        ok("DataStore push/get candles", f"{len(candles)} candle(s)")
    except Exception as exc:
        fail("DataStore candle ops", str(exc))

    # 2f. StateWriter Redis pub/sub
    try:
        from data.state_writer import StateWriter
        writer = StateWriter()
        assert writer._redis is not None
        ok("StateWriter connected to Redis")

        # Write test state
        test_state = {"system_running": True, "balance": 10000, "_test": True}
        writer.write(test_state)

        # Read it back from Redis
        data_str = r.get("prady:live_state")
        assert data_str is not None
        data = json.loads(data_str)
        assert data.get("system_running") is True
        ok("StateWriter → Redis → read back")
    except Exception as exc:
        fail("StateWriter Redis", str(exc))

    # 2g. Dashboard reads from Redis
    try:
        from dashboard.state import _load_live_state
        live = _load_live_state()
        if live is not None:
            ok("Dashboard _load_live_state from Redis", f"keys={len(live)}")
        else:
            warn("Dashboard _load_live_state returned None (state may be stale)")
    except Exception as exc:
        fail("Dashboard state from Redis", str(exc))

    # 2h. Cleanup
    try:
        r.delete("prady:live_state")
        # Clean test candle keys
        for key in r.scan_iter("prady:candle:BTCUSDT_TEST:*"):
            r.delete(key)
        ok("Redis cleanup")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 3. REASONING BACKENDS
# ══════════════════════════════════════════════════════════════
def test_reasoning_backends():
    print("\n═══ REASONING BACKENDS ═══")

    from config.settings import get_settings
    settings = get_settings()

    # 3a. Base configuration
    ok("Ollama host", settings.ollama_host)
    ok("Ollama model", settings.ollama_model)
    ok("Ollama timeout", f"{settings.ollama_timeout_sec}s")
    if settings.nvidia_nim_api_key:
        ok("NVIDIA NIM configured", settings.nvidia_nim_model)
    else:
        warn("NVIDIA NIM not configured", "fallback disabled")

    ollama_available = False
    nim_available = False
    debater_path_available = False
    debater_provider = ""
    models: list[str] = []

    # 3b. Ollama health check
    try:
        import urllib.request
        req = urllib.request.Request(f"{settings.ollama_host}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            ok("Ollama /api/tags", f"models={models}")
    except Exception as exc:
        warn("Ollama health check", str(exc))

    # 3c. Model available
    if models and any(settings.ollama_model in m for m in models):
        ok(f"Model '{settings.ollama_model}' available")
    else:
        warn(f"Model '{settings.ollama_model}' NOT found", f"available={models}")

    # 3d. Generate endpoint (short test prompt)
    if models and any(settings.ollama_model in m for m in models):
        try:
            import urllib.request
            payload = json.dumps({
                "model": settings.ollama_model,
                "prompt": "Reply with exactly: OK",
                "stream": False,
                "options": {"num_predict": 10},
            }).encode()
            req = urllib.request.Request(
                f"{settings.ollama_host}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                response_text = data.get("response", "")
                assert len(response_text) > 0
                ollama_available = True
                ok("Ollama generate", f"response={response_text[:60]}...")
        except Exception as exc:
            warn("Ollama generate", str(exc))

    # 3e. Async queries via debater helpers
    try:
        from agents.debater_agent import DebaterAgent, _parse_llm_response, _query_nvidia_nim, _query_ollama

        async def _test_ollama_async():
            return await _query_ollama(
                "Reply with exactly: {\"test\": true}",
                settings.ollama_model,
                settings.ollama_host,
            )

        if models and any(settings.ollama_model in m for m in models):
            result = asyncio.run(_test_ollama_async())
            if result:
                ollama_available = True
                ok("_query_ollama async", f"len={len(result)}")
            else:
                warn("_query_ollama returned empty", "Ollama may be slow or unavailable")

        if settings.nvidia_nim_api_key:
            async def _test_nim_async():
                return await _query_nvidia_nim(
                    'Reply with exactly: {"test": true}',
                    settings.nvidia_nim_model,
                    settings.nvidia_nim_base_url,
                    settings.nvidia_nim_api_key,
                )

            nim_result = asyncio.run(_test_nim_async())
            if nim_result:
                nim_available = True
                ok("_query_nvidia_nim async", f"len={len(nim_result)}")
            else:
                warn("_query_nvidia_nim returned empty", "Fallback backend did not answer")

        good = _parse_llm_response('Some text {"consensus_direction": "LONG", "verdict": "AGREE", "conviction": 0.8, "counter_arguments": [], "summary": "test"} extra')
        assert good["verdict"] == "AGREE"
        ok("_parse_llm_response (valid JSON)")

        bad = _parse_llm_response("This is not JSON at all")
        assert bad["verdict"] == "NEUTRAL"
        ok("_parse_llm_response (fallback on bad input)")

        debater = DebaterAgent()
        debater.set_other_signals(
            {
                "oracle": {"direction": "LONG", "confidence": 0.82, "reasoning": "Trend remains constructive"},
                "sentinel": {"direction": "LONG", "confidence": 0.71, "reasoning": "Sentiment is supportive"},
                "arbiter": {"direction": "NEUTRAL", "confidence": 0.55, "reasoning": "Order flow mixed"},
            }
        )
        debater_signal = asyncio.run(debater.analyze("BTCUSDT"))
        assert debater_signal.direction in ("LONG", "SHORT", "NEUTRAL")
        debater_provider = str(debater_signal.metadata.get("llm_provider", "rule_based") or "rule_based")
        debater_path_available = True
        if debater_provider == "rule_based":
            ok("Debater rule-based fallback", debater_signal.reasoning[:140])
        else:
            ok("Debater reasoning signal", f"provider={debater_provider}, direction={debater_signal.direction}")
    except Exception as exc:
        fail("Reasoning helper tests", str(exc))

    if ollama_available:
        ok("Primary reasoning backend", "Ollama available")
    elif nim_available:
        ok("Reasoning backend fallback", "NVIDIA NIM available while Ollama is unavailable")
    elif debater_path_available:
        ok("Reasoning fallback path", f"provider={debater_provider or 'rule_based'}")
    else:
        fail("No reasoning backend available", "Ollama unavailable and NVIDIA NIM fallback not working")



# ══════════════════════════════════════════════════════════════
# 4. DASHBOARD ↔ BACKEND WIRING
# ══════════════════════════════════════════════════════════════
def test_dashboard_wiring():
    print("\n═══ DASHBOARD ↔ BACKEND WIRING ═══")

    # 4a. DashboardState singleton
    try:
        from dashboard.state import get_dashboard_state, DashboardState
        state = get_dashboard_state()
        assert isinstance(state, DashboardState)
        ok("DashboardState singleton")
    except Exception as exc:
        fail("DashboardState singleton", str(exc))
        return

    # 4b. StateWriter → JSON file → Dashboard state
    try:
        from data.state_writer import StateWriter
        writer = StateWriter()
        test_state = writer.build_state(
            paper_engine=_mock_paper_engine(),
            last_decisions={},
            prices={"BTCUSDT": 50000.0},
            cycle_count=1,
            start_time=time.time() - 60,
            kill_switch=False,
        )
        writer.write(test_state)

        from dashboard.state import _load_live_state
        live = _load_live_state()
        assert live is not None
        assert live.get("balance") is not None
        ok("StateWriter → JSON → _load_live_state", f"balance={live.get('balance')}")
    except Exception as exc:
        fail("StateWriter → Dashboard pipeline", str(exc))

    # 4c. refresh_live_data updates state
    try:
        from dashboard.state import refresh_live_data
        refresh_live_data(state)
        ok("refresh_live_data executed", f"running={state.system_running}, balance={state.balance}")
    except Exception as exc:
        fail("refresh_live_data", str(exc))

    # 4d. Charts module importable
    try:
        from dashboard.charts import (
            build_equity_curve,
            build_pnl_histogram,
            build_agent_radar,
            build_composite_gauge,
            build_weight_bar_chart,
        )
        ok("Dashboard charts module (5 chart builders)")
    except Exception as exc:
        fail("Dashboard charts import", str(exc))

    # 4e. Desktop launcher importable
    try:
        import run_desktop
        ok("Desktop launcher module")
    except Exception as exc:
        fail("Desktop launcher import", str(exc))

    # 4f. Settings properly exposed to dashboard
    try:
        from config.settings import get_settings
        settings = get_settings()
        assert settings.database_url
        assert settings.redis_url
        assert settings.ollama_host
        ok("Settings available to dashboard", f"db={settings.database_url.split('@')[-1]}")
    except Exception as exc:
        fail("Settings for dashboard", str(exc))


def _mock_paper_engine():
    """Create a minimal paper engine for test purposes."""
    from decimal import Decimal
    from execution.paper_engine import PaperTradingEngine
    engine = PaperTradingEngine(Decimal("10000"))
    return engine


# ══════════════════════════════════════════════════════════════
# 5. END-TO-END PIPELINE
# ══════════════════════════════════════════════════════════════
def test_pipeline():
    print("\n═══ END-TO-END PIPELINE ═══")

    # 5a. TradingOrchestrator instantiation (wires everything)
    try:
        from council.orchestrator import TradingOrchestrator
        orch = TradingOrchestrator()
        assert orch.paper_engine is not None
        assert orch.state_writer is not None
        assert orch.journal is not None
        assert orch.council is not None
        ok("TradingOrchestrator created", "paper_engine + journal + state_writer")
    except Exception as exc:
        fail("TradingOrchestrator init", str(exc))
        return

    # 5b. Journal is connected to DB
    try:
        assert orch.journal._available is True
        ok("Journal connected to PostgreSQL")
    except Exception as exc:
        fail("Journal DB connection", str(exc))

    # 5c. State writer connected to Redis
    try:
        assert orch.state_writer._redis is not None
        ok("StateWriter connected to Redis")
    except Exception as exc:
        warn("StateWriter Redis not connected", str(exc))

    # 5d. Simulate a trade and verify journal persistence
    try:
        from decimal import Decimal

        # Open + close a paper position
        orch.paper_engine.place_market_order("TEST_PIPELINE", "BUY", 0.01, 50000.0)
        assert "TEST_PIPELINE" in orch.paper_engine.positions
        ok("Paper engine: position opened")

        orch.paper_engine.place_market_order("TEST_PIPELINE", "SELL", 0.01, 51000.0)
        assert "TEST_PIPELINE" not in orch.paper_engine.positions
        ok("Paper engine: position closed")

        recent_before = orch.journal.get_recent_trades(10)
        orch._persist_new_trades()
        trades = orch.journal.get_recent_trades(10)

        if orch.settings.is_paper:
            assert any(t["symbol"] == "TEST_PIPELINE" for t in trades)
            ok("Trade persisted to PostgreSQL journal")
        else:
            assert len(trades) == len(recent_before)
            ok(
                "Trade persistence skipped outside paper mode",
                f"mode={orch.settings.trading_mode}",
            )

        # Cleanup
        from execution.trade_journal import TradeRecord
        with orch.journal._session_factory() as session:
            session.query(TradeRecord).filter(TradeRecord.symbol == "TEST_PIPELINE").delete()
            session.commit()
        ok("Pipeline test cleanup")
    except Exception as exc:
        fail("Trade persistence pipeline", str(exc))

    # 5e. Write state includes journal stats
    try:
        orch._prices = {"BTCUSDT": 50000.0}
        orch._write_state()
        ok("_write_state with journal stats")
    except Exception as exc:
        fail("_write_state", str(exc))


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  PRADY TRADER — Backend Integration Test")
    print("=" * 60)

    test_postgresql()
    test_redis()
    test_reasoning_backends()
    test_dashboard_wiring()
    test_pipeline()

    try:
        from data.free_apis import close_session_sync

        close_session_sync()
        ok("Free API session shutdown")
    except Exception as exc:
        warn("Free API session shutdown", str(exc))

    print("\n" + "=" * 60)
    print(f"  RESULTS: {PASS} passed, {FAIL} failed, {WARN} warnings")
    print("=" * 60)

    if FAIL > 0:
        print("\n  FAILED TESTS:")
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"    ❌ {name}: {detail}")
        sys.exit(1)
    else:
        print("\n  🎉 All backend integration tests PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
