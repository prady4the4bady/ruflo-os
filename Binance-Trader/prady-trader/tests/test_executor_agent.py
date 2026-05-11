from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from execution.paper_engine import PaperTradingEngine
from execution.position_tracker import PositionTracker


class TestExecutorAgent(TestCase):
    def _settings(self):
        return SimpleNamespace(
            trading_mode="testnet",
            execution_environment="testnet",
            is_paper=False,
            default_leverage=1,
            kelly_fraction=Decimal("0.25"),
            harvest_threshold=Decimal("0.003"),
            max_concurrent_positions=3,
            enable_safe_reserve_conversion=True,
            safe_reserve_asset="USDT",
        )

    def _paper_settings(self):
        return SimpleNamespace(
            trading_mode="paper",
            execution_environment="paper",
            is_paper=True,
            default_leverage=1,
            kelly_fraction=Decimal("0.25"),
            harvest_threshold=Decimal("0.003"),
            max_concurrent_positions=3,
            enable_safe_reserve_conversion=False,
            safe_reserve_asset="USDT",
        )

    def test_live_long_entry_tracks_position_and_journals(self):
        fake_client = MagicMock()
        fake_client.get_usdt_balance.return_value = 100.0
        fake_client.get_ticker_price.return_value = {"lastPrice": "50.0"}
        fake_client.normalize_quantity.side_effect = lambda symbol, quantity: quantity
        fake_client.place_market_order.return_value = {"orderId": 12345}
        fake_client.get_symbol_base_balance.return_value = 0.0
        fake_client.execution_environment = "testnet"

        tracker = PositionTracker()
        journal = MagicMock()
        journal.record_entry.return_value = 77

        with patch("agents.executor_agent.get_settings", return_value=self._settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(position_tracker=tracker, journal=journal)
            result = asyncio.run(
                agent.execute_entry(
                    "BTCUSDT",
                    "LONG",
                    0.9,
                    decision_context={"decision_action": "LONG", "agent_snapshot": {"oracle": {"direction": "LONG"}}},
                )
            )

        self.assertEqual(result["status"], "filled")
        self.assertTrue(tracker.has_position("BTCUSDT"))
        self.assertEqual(tracker.get_position("BTCUSDT").trade_id, 77)
        self.assertEqual(tracker.get_position("BTCUSDT").metadata["decision_action"], "LONG")
        journal.record_entry.assert_called_once()

    def test_live_short_without_tracked_position_skips(self):
        fake_client = MagicMock()
        fake_client.get_ticker_price.return_value = {"lastPrice": "50.0"}
        fake_client.get_symbol_base_balance.return_value = 0.0
        fake_client.execution_environment = "testnet"

        with patch("agents.executor_agent.get_settings", return_value=self._settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(position_tracker=PositionTracker(), journal=MagicMock())
            result = asyncio.run(agent.execute_entry("BTCUSDT", "SHORT", 0.9))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "no_tracked_spot_position")

    def test_live_long_entry_skips_when_exchange_inventory_exists(self):
        fake_client = MagicMock()
        fake_client.get_usdt_balance.return_value = 100.0
        fake_client.get_ticker_price.return_value = {"lastPrice": "50.0"}
        fake_client.normalize_quantity.side_effect = lambda symbol, quantity: quantity
        fake_client.get_symbol_base_balance.return_value = 0.25
        fake_client.estimate_spot_entry_price.return_value = 48.0
        fake_client.execution_environment = "testnet"

        tracker = PositionTracker()

        with patch("agents.executor_agent.get_settings", return_value=self._settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(position_tracker=tracker, journal=MagicMock())
            result = asyncio.run(agent.execute_entry("BTCUSDT", "LONG", 0.9))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "exchange_inventory_exists")
        self.assertTrue(tracker.has_position("BTCUSDT"))
        self.assertEqual(tracker.get_position("BTCUSDT").source, "exchange_sync")

    def test_live_short_signal_closes_untracked_exchange_inventory(self):
        fake_client = MagicMock()
        fake_client.get_ticker_price.return_value = {"lastPrice": "50.0"}
        fake_client.get_symbol_base_balance.return_value = 1.0
        fake_client.normalize_quantity.side_effect = lambda symbol, quantity: quantity
        fake_client.place_market_order.return_value = {"orderId": 54321}
        fake_client.cancel_all_orders.return_value = {"count": 0}
        fake_client.estimate_spot_entry_price.return_value = 47.5
        fake_client.execution_environment = "testnet"

        tracker = PositionTracker()

        with patch("agents.executor_agent.get_settings", return_value=self._settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(position_tracker=tracker, journal=MagicMock())
            result = asyncio.run(agent.execute_entry("BTCUSDT", "SHORT", 0.9))

        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["reason"], "signal_reverse")
        self.assertFalse(tracker.has_position("BTCUSDT"))
        fake_client.place_market_order.assert_called_once_with("BTCUSDT", "SELL", 1.0)

    def test_signal_reverse_close_skips_fresh_unprofitable_churn(self):
        fake_client = MagicMock()
        fake_client.get_symbol_base_balance.return_value = 1.0
        fake_client.normalize_quantity.side_effect = lambda symbol, quantity: quantity
        fake_client.get_ticker_price.return_value = {"lastPrice": "49.9"}
        fake_client.place_market_order.return_value = {"orderId": 54321}
        fake_client.cancel_all_orders.return_value = {"count": 0}
        fake_client.park_quote_in_safe_reserve.return_value = {"status": "skipped", "reason": "not_called"}
        fake_client.execution_environment = "testnet"

        tracker = PositionTracker()
        tracker.open_position(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=50.0,
            quantity=1.0,
            leverage=1,
            stop_loss=48.0,
            take_profit=55.0,
            trade_id=88,
            paper=False,
        )

        with patch("agents.executor_agent.get_settings", return_value=self._settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(position_tracker=tracker, journal=MagicMock())
            result = asyncio.run(agent.close_position("BTCUSDT", reason="signal_reverse"))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "signal_reverse_guard")
        self.assertTrue(tracker.has_position("BTCUSDT"))
        fake_client.cancel_all_orders.assert_not_called()

    def test_signal_reverse_close_forces_exit_on_strong_reverse_signal(self):
        fake_client = MagicMock()
        fake_client.get_symbol_base_balance.return_value = 1.0
        fake_client.normalize_quantity.side_effect = lambda symbol, quantity: quantity
        fake_client.get_ticker_price.return_value = {"lastPrice": "49.9"}
        fake_client.place_market_order.return_value = {"orderId": 54321}
        fake_client.cancel_all_orders.return_value = {"count": 0}
        fake_client.park_quote_in_safe_reserve.return_value = {"status": "skipped", "reason": "quote_already_safe_reserve"}
        fake_client.execution_environment = "testnet"

        tracker = PositionTracker()
        tracker.open_position(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=50.0,
            quantity=1.0,
            leverage=1,
            stop_loss=48.0,
            take_profit=55.0,
            trade_id=88,
            paper=False,
        )

        with patch("agents.executor_agent.get_settings", return_value=self._settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(position_tracker=tracker, journal=MagicMock())
            result = asyncio.run(agent.close_position("BTCUSDT", reason="signal_reverse", signal_confidence=0.95))

        self.assertEqual(result["status"], "closed")
        self.assertFalse(tracker.has_position("BTCUSDT"))
        fake_client.park_quote_in_safe_reserve.assert_called_once_with("BTCUSDT")

    def test_live_close_uses_tracked_position_and_records_exit(self):
        fake_client = MagicMock()
        fake_client.get_symbol_base_balance.return_value = 1.0
        fake_client.normalize_quantity.side_effect = lambda symbol, quantity: quantity
        fake_client.get_ticker_price.return_value = {"lastPrice": "55.0"}
        fake_client.place_market_order.return_value = {"orderId": 54321}
        fake_client.cancel_all_orders.return_value = {"count": 0}
        fake_client.park_quote_in_safe_reserve.return_value = {"status": "skipped", "reason": "quote_already_safe_reserve"}
        fake_client.execution_environment = "testnet"

        tracker = PositionTracker()
        tracker.open_position(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=50.0,
            quantity=1.0,
            leverage=1,
            stop_loss=48.0,
            take_profit=55.0,
            trade_id=88,
            paper=False,
            metadata={"decision_action": "LONG", "agent_snapshot": {"oracle": {"direction": "LONG"}}},
        )
        journal = MagicMock()

        with patch("agents.executor_agent.get_settings", return_value=self._settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(position_tracker=tracker, journal=journal)
            result = asyncio.run(agent.close_position("BTCUSDT", reason="take_profit"))

        self.assertEqual(result["status"], "closed")
        self.assertFalse(tracker.has_position("BTCUSDT"))
        self.assertEqual(result["closed_trade"]["metadata"]["decision_action"], "LONG")
        journal.record_exit.assert_called_once()
        fake_client.park_quote_in_safe_reserve.assert_called_once_with("BTCUSDT")

    def test_paper_entry_places_stop_and_take_profit_brackets(self):
        fake_client = MagicMock()
        fake_client.get_ticker_price.return_value = {"lastPrice": "50.0"}

        paper_engine = PaperTradingEngine(Decimal("10000"))

        with patch("agents.executor_agent.get_settings", return_value=self._paper_settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(paper_engine=paper_engine)
            result = asyncio.run(agent.execute_entry("BTCUSDT", "LONG", 0.9))

        self.assertEqual(result["status"], "paper_filled")
        pending = [order for order in paper_engine._pending_orders if order.symbol == "BTCUSDT"]
        self.assertEqual(len(pending), 2)

    def test_paper_entry_skips_duplicate_same_side_position(self):
        fake_client = MagicMock()
        fake_client.get_ticker_price.return_value = {"lastPrice": "50.0"}

        paper_engine = PaperTradingEngine(Decimal("10000"))
        paper_engine.place_market_order("BTCUSDT", "BUY", 1.0, 50.0)

        with patch("agents.executor_agent.get_settings", return_value=self._paper_settings()), patch(
            "agents.executor_agent.get_binance_client", return_value=fake_client
        ):
            from agents.executor_agent import ExecutorAgent

            agent = ExecutorAgent(paper_engine=paper_engine)
            result = asyncio.run(agent.execute_entry("BTCUSDT", "LONG", 0.9))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "paper_position_exists")