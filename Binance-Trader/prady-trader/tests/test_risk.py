"""
PRADY TRADER — Unit tests for risk manager.
Tests daily loss limits, position sizing, drawdown, stop-loss, take-profit,
trailing stops, time/confidence exits, and full pre-trade checks.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from execution.risk_manager import RiskManager


class TestRiskManagerDailyLoss(unittest.TestCase):
    """Tests for daily loss limit checks."""

    def setUp(self):
        self.rm = RiskManager()

    def test_allowed_when_no_losses(self):
        allowed, reason = self.rm.check_daily_loss_limit(Decimal("10000"))
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_blocked_after_limit(self):
        balance = Decimal("10000")
        # max_daily_loss default = 0.05 = $500
        self.rm.record_loss(Decimal("-300"))
        allowed, _ = self.rm.check_daily_loss_limit(balance)
        self.assertTrue(allowed)

        self.rm.record_loss(Decimal("-250"))
        allowed, reason = self.rm.check_daily_loss_limit(balance)
        self.assertFalse(allowed)
        self.assertIn("limit", reason.lower())

    def test_reset_daily(self):
        self.rm.record_loss(Decimal("-5000"))
        allowed, _ = self.rm.check_daily_loss_limit(Decimal("10000"))
        self.assertFalse(allowed)

        self.rm.reset_daily()
        allowed, _ = self.rm.check_daily_loss_limit(Decimal("10000"))
        self.assertTrue(allowed)


class TestRiskManagerPositionSize(unittest.TestCase):
    """Tests for position size checks."""

    def setUp(self):
        self.rm = RiskManager()

    def test_small_position_allowed(self):
        allowed, reason = self.rm.check_position_size(Decimal("500"), Decimal("10000"))
        self.assertTrue(allowed)

    def test_large_position_blocked(self):
        # MAX_POSITION_PCT = 0.10 → $1000 max on $10000
        allowed, reason = self.rm.check_position_size(Decimal("1500"), Decimal("10000"))
        self.assertFalse(allowed)
        self.assertIn("exceeds", reason.lower())


class TestRiskManagerLeverage(unittest.TestCase):
    """Tests for leverage checks."""

    def setUp(self):
        self.rm = RiskManager()

    def test_safe_leverage(self):
        allowed, _ = self.rm.check_leverage(5)
        self.assertTrue(allowed)

    def test_max_leverage_allowed(self):
        allowed, _ = self.rm.check_leverage(10)
        self.assertTrue(allowed)

    def test_excessive_leverage_blocked(self):
        allowed, reason = self.rm.check_leverage(25)
        self.assertFalse(allowed)
        self.assertIn("exceeds", reason.lower())


class TestRiskManagerDrawdown(unittest.TestCase):
    """Tests for drawdown checks."""

    def setUp(self):
        self.rm = RiskManager()

    def test_no_drawdown(self):
        self.rm.update_equity(Decimal("10000"))
        allowed, _ = self.rm.check_drawdown(Decimal("10000"))
        self.assertTrue(allowed)

    def test_small_drawdown_allowed(self):
        self.rm.update_equity(Decimal("10000"))
        allowed, _ = self.rm.check_drawdown(Decimal("9500"))
        self.assertTrue(allowed)

    def test_large_drawdown_blocked(self):
        self.rm.update_equity(Decimal("10000"))
        allowed, reason = self.rm.check_drawdown(Decimal("8000"))
        self.assertFalse(allowed)
        self.assertIn("drawdown", reason.lower())


class TestRiskManagerStopLoss(unittest.TestCase):
    """Tests for stop-loss computation."""

    def setUp(self):
        self.rm = RiskManager()

    def test_long_stop_below_entry(self):
        sl = self.rm.compute_stop_loss(Decimal("50000"), "LONG")
        self.assertLess(sl, Decimal("50000"))

    def test_short_stop_above_entry(self):
        sl = self.rm.compute_stop_loss(Decimal("50000"), "SHORT")
        self.assertGreater(sl, Decimal("50000"))

    def test_atr_based_stop(self):
        sl = self.rm.compute_stop_loss(Decimal("50000"), "LONG", atr=Decimal("500"))
        self.assertLess(sl, Decimal("50000"))
        # ATR stop: 500 * 1.5 = 750 → SL = 50000 - 750 = 49250
        self.assertLessEqual(sl, Decimal("49250"))

    def test_atr_zero_falls_back_to_pct(self):
        sl_atr = self.rm.compute_stop_loss(Decimal("50000"), "LONG", atr=Decimal("0"))
        sl_no = self.rm.compute_stop_loss(Decimal("50000"), "LONG")
        self.assertEqual(sl_atr, sl_no)


class TestRiskManagerTakeProfit(unittest.TestCase):
    """Tests for take-profit computation."""

    def setUp(self):
        self.rm = RiskManager()

    def test_long_tp_above_entry(self):
        tp = self.rm.compute_take_profit(Decimal("50000"), "LONG")
        self.assertGreater(tp, Decimal("50000"))

    def test_short_tp_below_entry(self):
        tp = self.rm.compute_take_profit(Decimal("50000"), "SHORT")
        self.assertLess(tp, Decimal("50000"))

    def test_rr_ratio_applied(self):
        sl = Decimal("49000")
        tp = self.rm.compute_take_profit(
            Decimal("50000"), "LONG",
            risk_reward_ratio=Decimal("2.0"),
            stop_loss=sl,
        )
        risk = Decimal("50000") - sl
        expected_tp = Decimal("50000") + risk * Decimal("2.0")
        self.assertEqual(tp, expected_tp)


class TestRiskManagerTrailingStop(unittest.TestCase):
    """Tests for trailing stop computation."""

    def setUp(self):
        self.rm = RiskManager()

    def test_long_trailing_below_price(self):
        ts = self.rm.compute_trailing_stop(Decimal("55000"), "LONG")
        self.assertLess(ts, Decimal("55000"))

    def test_short_trailing_above_price(self):
        ts = self.rm.compute_trailing_stop(Decimal("55000"), "SHORT")
        self.assertGreater(ts, Decimal("55000"))


class TestRiskManagerExitConditions(unittest.TestCase):
    """Tests for time and confidence exit checks."""

    def setUp(self):
        self.rm = RiskManager()

    def test_time_exit_not_triggered(self):
        self.assertFalse(self.rm.should_exit_on_time(100))

    def test_time_exit_triggered(self):
        self.assertTrue(self.rm.should_exit_on_time(300))

    def test_confidence_exit_not_triggered(self):
        self.assertFalse(self.rm.should_exit_on_confidence(0.8))

    def test_confidence_exit_triggered(self):
        self.assertTrue(self.rm.should_exit_on_confidence(0.4))


class TestRiskManagerFullCheck(unittest.TestCase):
    """Tests for full_pre_trade_check()."""

    def setUp(self):
        self.rm = RiskManager()

    def test_all_clear(self):
        self.rm.update_equity(Decimal("10000"))
        allowed, reason = self.rm.full_pre_trade_check(
            balance=Decimal("10000"),
            equity=Decimal("10000"),
            size_usdt=Decimal("500"),
            leverage=5,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_blocked_by_leverage(self):
        self.rm.update_equity(Decimal("10000"))
        allowed, reason = self.rm.full_pre_trade_check(
            balance=Decimal("10000"),
            equity=Decimal("10000"),
            size_usdt=Decimal("500"),
            leverage=25,
        )
        self.assertFalse(allowed)
        self.assertIn("leverage", reason.lower())

    def test_blocked_by_position_size(self):
        self.rm.update_equity(Decimal("10000"))
        allowed, reason = self.rm.full_pre_trade_check(
            balance=Decimal("10000"),
            equity=Decimal("10000"),
            size_usdt=Decimal("5000"),
            leverage=5,
        )
        self.assertFalse(allowed)
        self.assertIn("exceeds", reason.lower())


if __name__ == "__main__":
    unittest.main()
