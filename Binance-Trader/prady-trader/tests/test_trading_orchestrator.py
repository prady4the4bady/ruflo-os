from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch


class FakeStateWriter:
    def __init__(self, persisted_state=None):
        self.persisted_state = persisted_state or {}
        self.last_written = None

    def read_state(self, runtime_mode=None):
        return dict(self.persisted_state)

    def build_state(self, **kwargs):
        return {
            "system_running": True,
            "trading_mode": "testnet",
            "runtime_mode": "testnet",
            "mode_label": "TESTNET",
            "mode_policy": {},
            "mode_policies": {},
            "execution_environment": "testnet",
            "cycle_count": kwargs["cycle_count"],
            "uptime_seconds": 0.0,
            "balance": 0.0,
            "equity": 0.0,
            "initial_balance": 0.0,
            "total_return_pct": 0.0,
            "total_pnl": 0.0,
            "daily_pnl": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "open_positions": [],
            "closed_trades": [],
            "last_decisions": {},
            "agent_signals": {},
            "prices": kwargs["prices"],
            "kill_switch": kwargs["kill_switch"],
        }

    def write(self, state):
        self.last_written = state


class TestTradingOrchestrator(TestCase):
    def _settings(self):
        return SimpleNamespace(
            trading_mode="testnet",
            runtime_mode="testnet",
            execution_environment="testnet",
            uses_binance_execution=True,
            is_paper=False,
            is_live=False,
            mode_label="TESTNET",
            trading_pairs=["BTCUSDT"],
            max_hold_minutes=240,
            max_daily_loss=Decimal("0.05"),
            max_consecutive_losses=3,
            live_min_rehearsal_trades=20,
            live_min_rehearsal_win_rate=Decimal("0.55"),
            live_require_positive_rehearsal_pnl=True,
        )

    def test_hydrates_execution_baseline_from_persisted_state(self):
        persisted = {"execution_baseline_balance": 406495.0551995262}
        fake_writer = FakeStateWriter(persisted_state=persisted)
        fake_client = MagicMock()
        fake_client.get_execution_account_info.return_value = {
            "positions": [],
            "account_summary": {
                "free_usdt": 5930.25632699,
                "estimated_total_usdt": 403402.7265381882,
            },
        }

        fake_council = MagicMock()
        fake_council.last_decisions = {}

        with patch("council.orchestrator.get_settings", return_value=self._settings()), patch(
            "data.state_writer.StateWriter", return_value=fake_writer
        ), patch("data.binance_client.get_binance_client", return_value=fake_client), patch(
            "execution.trade_journal.TradeJournal", return_value=MagicMock()
        ), patch("council.orchestrator.CouncilOrchestrator", return_value=fake_council), patch(
            "council.orchestrator.ExecutorAgent", return_value=MagicMock()
        ):
            from council.orchestrator import TradingOrchestrator

            orchestrator = TradingOrchestrator()

        self.assertAlmostEqual(orchestrator._execution_initial_balance, persisted["execution_baseline_balance"])

    def test_write_state_preserves_persisted_execution_baseline(self):
        persisted = {"execution_baseline_balance": 406495.0551995262}
        fake_writer = FakeStateWriter(persisted_state=persisted)
        fake_client = MagicMock()
        fake_client.get_execution_account_info.return_value = {
            "positions": [],
            "account_summary": {
                "free_usdt": 5930.25632699,
                "estimated_total_usdt": 403402.7265381882,
            },
        }

        fake_council = MagicMock()
        fake_council.last_decisions = {}

        with patch("council.orchestrator.get_settings", return_value=self._settings()), patch(
            "data.state_writer.StateWriter", return_value=fake_writer
        ), patch("data.binance_client.get_binance_client", return_value=fake_client), patch(
            "execution.trade_journal.TradeJournal", return_value=MagicMock()
        ), patch("council.orchestrator.CouncilOrchestrator", return_value=fake_council), patch(
            "council.orchestrator.ExecutorAgent", return_value=MagicMock()
        ):
            from council.orchestrator import TradingOrchestrator

            orchestrator = TradingOrchestrator()
            orchestrator._write_state()

        expected_pnl = 403402.7265381882 - persisted["execution_baseline_balance"]
        self.assertIsNotNone(fake_writer.last_written)
        self.assertAlmostEqual(fake_writer.last_written["initial_balance"], persisted["execution_baseline_balance"])
        self.assertAlmostEqual(fake_writer.last_written["execution_baseline_balance"], persisted["execution_baseline_balance"])
        self.assertAlmostEqual(fake_writer.last_written["total_pnl"], expected_pnl)

    def test_runtime_guard_pauses_after_consecutive_losses(self):
        persisted = {"execution_baseline_balance": 1000.0}
        fake_writer = FakeStateWriter(persisted_state=persisted)
        fake_client = MagicMock()
        fake_client.get_execution_account_info.return_value = {
            "positions": [],
            "account_summary": {
                "free_usdt": 940.0,
                "estimated_total_usdt": 940.0,
            },
        }

        fake_council = MagicMock()
        fake_council.last_decisions = {}

        with patch("council.orchestrator.get_settings", return_value=self._settings()), patch(
            "data.state_writer.StateWriter", return_value=fake_writer
        ), patch("data.binance_client.get_binance_client", return_value=fake_client), patch(
            "execution.trade_journal.TradeJournal", return_value=MagicMock()
        ), patch("council.orchestrator.CouncilOrchestrator", return_value=fake_council), patch(
            "council.orchestrator.ExecutorAgent", return_value=MagicMock()
        ):
            from council.orchestrator import TradingOrchestrator

            orchestrator = TradingOrchestrator()

        orchestrator.position_tracker._closed.extend(
            [
                {"symbol": "BTCUSDT", "pnl": -10.0},
                {"symbol": "ETHUSDT", "pnl": -7.5},
                {"symbol": "SOLUSDT", "pnl": -5.0},
            ]
        )

        allowed = orchestrator._evaluate_runtime_guard()

        self.assertFalse(allowed)
        self.assertEqual(orchestrator._runtime_guard["status"], "paused")
        reasons = " ".join(orchestrator._runtime_guard["reasons"])
        self.assertIn("Consecutive loss streak", reasons)

    def test_write_state_includes_runtime_guard_status(self):
        persisted = {"execution_baseline_balance": 1000.0}
        fake_writer = FakeStateWriter(persisted_state=persisted)
        fake_client = MagicMock()
        fake_client.get_execution_account_info.return_value = {
            "positions": [],
            "account_summary": {
                "free_usdt": 990.0,
                "estimated_total_usdt": 990.0,
            },
        }

        fake_council = MagicMock()
        fake_council.last_decisions = {}

        with patch("council.orchestrator.get_settings", return_value=self._settings()), patch(
            "data.state_writer.StateWriter", return_value=fake_writer
        ), patch("data.binance_client.get_binance_client", return_value=fake_client), patch(
            "execution.trade_journal.TradeJournal", return_value=MagicMock()
        ), patch("council.orchestrator.CouncilOrchestrator", return_value=fake_council), patch(
            "council.orchestrator.ExecutorAgent", return_value=MagicMock()
        ):
            from council.orchestrator import TradingOrchestrator

            orchestrator = TradingOrchestrator()
            orchestrator._runtime_guard = {
                "allowed": False,
                "status": "paused",
                "reasons": ["example reason"],
                "metrics": {"consecutive_losses": 3},
            }
            orchestrator._write_state()

        self.assertIsNotNone(fake_writer.last_written)
        self.assertEqual(fake_writer.last_written["runtime_guard"]["status"], "paused")
        self.assertEqual(fake_writer.last_written["runtime_guard"]["reasons"], ["example reason"])

    def test_active_symbols_come_from_selection_manager(self):
        persisted = {"execution_baseline_balance": 1000.0}
        fake_writer = FakeStateWriter(persisted_state=persisted)
        fake_client = MagicMock()
        fake_client.get_execution_account_info.return_value = {
            "positions": [],
            "account_summary": {
                "free_usdt": 990.0,
                "estimated_total_usdt": 990.0,
            },
        }

        fake_council = MagicMock()
        fake_council.last_decisions = {}
        fake_selector = MagicMock()
        fake_selector.active_symbols.return_value = ["ETHUSDT"]
        fake_council.symbol_selector = fake_selector

        settings = self._settings()
        settings.trading_pairs = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        with patch("council.orchestrator.get_settings", return_value=settings), patch(
            "data.state_writer.StateWriter", return_value=fake_writer
        ), patch("data.binance_client.get_binance_client", return_value=fake_client), patch(
            "execution.trade_journal.TradeJournal", return_value=MagicMock()
        ), patch("council.orchestrator.CouncilOrchestrator", return_value=fake_council), patch(
            "council.orchestrator.ExecutorAgent", return_value=MagicMock()
        ):
            from council.orchestrator import TradingOrchestrator

            orchestrator = TradingOrchestrator()

        self.assertEqual(orchestrator._active_symbols(), ["ETHUSDT"])