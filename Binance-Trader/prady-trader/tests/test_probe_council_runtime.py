from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def test_run_paper_probe_skips_all_symbols_when_none_are_active():
    from scripts.probe_council_runtime import run_paper_probe

    args = SimpleNamespace(
        symbols=["BTCUSDT", "ETHUSDT"],
        intervals=["5m"],
        candle_limit=50,
        cycles=1,
        paper_min_confidence=0.60,
    )

    fake_settings = SimpleNamespace(min_confidence=Decimal("0.60"))
    fake_decision = SimpleNamespace(agent_signals={})
    fake_state_writer = MagicMock()
    fake_state_writer.read_state.return_value = {
        "active_symbols": [],
        "runtime_guard": {},
        "last_decisions": {},
        "closed_trades": [],
    }
    fake_paper_engine = MagicMock()
    fake_paper_engine.get_stats.return_value = {
        "balance": 10000.0,
        "total_return_pct": 0.0,
        "total_trades": 0,
        "win_rate": 0.0,
    }
    fake_paper_engine.positions = {}
    fake_paper_engine.get_equity.return_value = Decimal("10000")
    fake_orchestrator = MagicMock()
    fake_orchestrator._cycle_count = 0
    fake_orchestrator._prices = {}
    fake_orchestrator._agent_signals = {}
    fake_orchestrator._refresh_prices = AsyncMock()
    fake_orchestrator._check_position_limits = AsyncMock()
    fake_orchestrator._sync_execution_positions = MagicMock()
    fake_orchestrator._check_pending_orders = MagicMock()
    fake_orchestrator._evaluate_runtime_guard = MagicMock(return_value=True)
    fake_orchestrator._active_symbols = MagicMock(return_value=[])
    fake_orchestrator._write_state = MagicMock()
    fake_orchestrator._persist_new_trades = MagicMock()
    fake_orchestrator.state_writer = fake_state_writer
    fake_orchestrator.paper_engine = fake_paper_engine
    fake_orchestrator.council = MagicMock()
    fake_orchestrator.council.run_cycle = AsyncMock(return_value=fake_decision)

    with patch("scripts.probe_council_runtime._configure_runtime"), patch(
        "scripts.probe_council_runtime.get_settings", return_value=fake_settings
    ), patch("scripts.probe_council_runtime.BinanceClientWrapper"), patch(
        "scripts.probe_council_runtime.TradingOrchestrator", return_value=fake_orchestrator
    ), patch("scripts.probe_council_runtime._seed_symbol_context") as seed_context:
        payload = asyncio.run(run_paper_probe(args))

    seed_context.assert_not_called()
    fake_orchestrator.council.run_cycle.assert_not_called()
    assert payload["active_symbols"] == []


def test_run_paper_probe_only_runs_active_symbols():
    from scripts.probe_council_runtime import run_paper_probe

    args = SimpleNamespace(
        symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        intervals=["5m"],
        candle_limit=50,
        cycles=1,
        paper_min_confidence=0.60,
    )

    fake_settings = SimpleNamespace(min_confidence=Decimal("0.60"))
    fake_decision = SimpleNamespace(agent_signals={})
    fake_state_writer = MagicMock()
    fake_state_writer.read_state.return_value = {
        "active_symbols": ["ETHUSDT"],
        "runtime_guard": {},
        "last_decisions": {},
        "closed_trades": [],
    }
    fake_paper_engine = MagicMock()
    fake_paper_engine.get_stats.return_value = {
        "balance": 10000.0,
        "total_return_pct": 0.0,
        "total_trades": 0,
        "win_rate": 0.0,
    }
    fake_paper_engine.positions = {}
    fake_paper_engine.get_equity.return_value = Decimal("10000")
    fake_orchestrator = MagicMock()
    fake_orchestrator._cycle_count = 0
    fake_orchestrator._prices = {}
    fake_orchestrator._agent_signals = {}
    fake_orchestrator._refresh_prices = AsyncMock()
    fake_orchestrator._check_position_limits = AsyncMock()
    fake_orchestrator._sync_execution_positions = MagicMock()
    fake_orchestrator._check_pending_orders = MagicMock()
    fake_orchestrator._evaluate_runtime_guard = MagicMock(return_value=True)
    fake_orchestrator._active_symbols = MagicMock(return_value=["ETHUSDT"])
    fake_orchestrator._write_state = MagicMock()
    fake_orchestrator._persist_new_trades = MagicMock()
    fake_orchestrator.state_writer = fake_state_writer
    fake_orchestrator.paper_engine = fake_paper_engine
    fake_orchestrator.council = MagicMock()
    fake_orchestrator.council.run_cycle = AsyncMock(return_value=fake_decision)

    with patch("scripts.probe_council_runtime._configure_runtime"), patch(
        "scripts.probe_council_runtime.get_settings", return_value=fake_settings
    ), patch("scripts.probe_council_runtime.BinanceClientWrapper"), patch(
        "scripts.probe_council_runtime.TradingOrchestrator", return_value=fake_orchestrator
    ), patch("scripts.probe_council_runtime._seed_symbol_context") as seed_context:
        payload = asyncio.run(run_paper_probe(args))

    seed_context.assert_called_once()
    fake_orchestrator.council.run_cycle.assert_awaited_once_with("ETHUSDT")
    assert payload["active_symbols"] == ["ETHUSDT"]