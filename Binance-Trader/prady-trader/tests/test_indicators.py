"""
PRADY TRADER — Unit tests for indicator modules.
Tests trend, momentum, volatility, volume, structure, patterns, and composite.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from indicators.trend import (
    compute_ema_signals,
    compute_macd_signal,
    compute_adx_signal,
    compute_supertrend_signal,
    compute_all_trend,
)
from indicators.momentum import (
    compute_rsi_signal,
    compute_stoch_rsi_signal,
    compute_cci_signal,
    compute_all_momentum,
)
from indicators.volatility import (
    compute_bollinger_signal,
    compute_atr,
    compute_all_volatility,
)
from indicators.volume import (
    compute_obv_signal,
    compute_all_volume,
)
from indicators.structure import (
    find_swing_highs_lows,
    compute_support_resistance,
    compute_all_structure,
)
from indicators.patterns import compute_all_patterns
from indicators.composite import score_single_timeframe, compute_composite_score


def make_ohlcv(n: int = 300, base_price: float = 100.0, trend: float = 0.001) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame for testing."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = base_price * np.cumprod(1 + np.random.randn(n) * 0.01 + trend)
    high = close * (1 + np.abs(np.random.randn(n)) * 0.005)
    low = close * (1 - np.abs(np.random.randn(n)) * 0.005)
    open_ = (close + np.roll(close, 1)) / 2
    open_[0] = base_price
    volume = np.random.uniform(1000, 10000, size=n)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)


class TestTrendIndicators(unittest.TestCase):
    """Tests for indicators/trend.py."""

    def setUp(self):
        self.df = make_ohlcv()

    def test_ema_signals_returns_dict(self):
        result = compute_ema_signals(self.df)
        self.assertIsInstance(result, dict)
        for v in result.values():
            self.assertIn(v, (-1, 0, 1))

    def test_macd_signal_returns_dict(self):
        result = compute_macd_signal(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("macd_signal", result)
        self.assertIn(result["macd_signal"], (-1, 0, 1))

    def test_adx_signal_returns_dict(self):
        result = compute_adx_signal(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("adx_direction", result)
        self.assertIn(result["adx_direction"], (-1, 0, 1))

    def test_supertrend_returns_valid(self):
        result = compute_supertrend_signal(self.df)
        self.assertIn(result, (-1, 0, 1))

    def test_compute_all_trend_returns_dict(self):
        result = compute_all_trend(self.df)
        self.assertIsInstance(result, dict)
        self.assertTrue(len(result) > 0)

    def test_compute_all_trend_empty_df(self):
        result = compute_all_trend(pd.DataFrame())
        self.assertIsInstance(result, dict)


class TestMomentumIndicators(unittest.TestCase):
    """Tests for indicators/momentum.py."""

    def setUp(self):
        self.df = make_ohlcv()

    def test_rsi_signal_returns_dict(self):
        result = compute_rsi_signal(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("rsi_signal", result)
        self.assertIn(result["rsi_signal"], (-1, 0, 1))

    def test_stochrsi_signal_returns_dict(self):
        result = compute_stoch_rsi_signal(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("stoch_rsi_signal", result)
        self.assertIn(result["stoch_rsi_signal"], (-1, 0, 1))

    def test_cci_signal_returns_dict(self):
        result = compute_cci_signal(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("cci_signal", result)

    def test_compute_all_momentum_returns_dict(self):
        result = compute_all_momentum(self.df)
        self.assertIsInstance(result, dict)
        self.assertTrue(len(result) > 0)


class TestVolatilityIndicators(unittest.TestCase):
    """Tests for indicators/volatility.py."""

    def setUp(self):
        self.df = make_ohlcv()

    def test_bollinger_signal_returns_dict(self):
        result = compute_bollinger_signal(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("bb_signal", result)
        self.assertIn(result["bb_signal"], (-1, 0, 1))

    def test_atr_returns_dict(self):
        result = compute_atr(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("atr_value", result)
        self.assertGreaterEqual(result["atr_value"], 0.0)

    def test_compute_all_volatility_returns_dict(self):
        result = compute_all_volatility(self.df)
        self.assertIsInstance(result, dict)


class TestVolumeIndicators(unittest.TestCase):
    """Tests for indicators/volume.py."""

    def setUp(self):
        self.df = make_ohlcv()

    def test_obv_signal_returns_dict(self):
        result = compute_obv_signal(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn("obv_signal", result)
        self.assertIn(result["obv_signal"], (-1, 0, 1))

    def test_compute_all_volume_returns_dict(self):
        result = compute_all_volume(self.df)
        self.assertIsInstance(result, dict)


class TestStructureIndicators(unittest.TestCase):
    """Tests for indicators/structure.py."""

    def setUp(self):
        self.df = make_ohlcv()

    def test_find_swing_highs_lows_returns_tuple(self):
        highs, lows = find_swing_highs_lows(self.df)
        self.assertIsInstance(highs, list)
        self.assertIsInstance(lows, list)

    def test_support_resistance_returns_dict(self):
        result = compute_support_resistance(self.df)
        self.assertIsInstance(result, dict)

    def test_compute_all_structure_returns_dict(self):
        result = compute_all_structure(self.df)
        self.assertIsInstance(result, dict)


class TestPatternIndicators(unittest.TestCase):
    """Tests for indicators/patterns.py."""

    def setUp(self):
        self.df = make_ohlcv()

    def test_compute_all_patterns_returns_dict(self):
        result = compute_all_patterns(self.df)
        self.assertIsInstance(result, dict)

    def test_compute_all_patterns_has_scores(self):
        result = compute_all_patterns(self.df)
        self.assertIn("candlestick_score", result)


class TestCompositeScoring(unittest.TestCase):
    """Tests for indicators/composite.py."""

    def setUp(self):
        self.df = make_ohlcv()

    def test_score_single_timeframe_range(self):
        result = score_single_timeframe(self.df)
        self.assertIn("score", result)
        self.assertIn("direction", result)
        self.assertIn("confidence", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_score_single_timeframe_direction(self):
        result = score_single_timeframe(self.df)
        self.assertIn(result["direction"], ("LONG", "SHORT", "WAIT"))

    def test_score_empty_df(self):
        result = score_single_timeframe(pd.DataFrame())
        self.assertEqual(result["score"], 50)
        self.assertEqual(result["direction"], "WAIT")

    def test_score_short_df(self):
        result = score_single_timeframe(self.df.head(5))
        self.assertEqual(result["score"], 50)

    def test_composite_multi_timeframe(self):
        dfs = {
            "1h": self.df,
            "4h": make_ohlcv(n=200, base_price=100, trend=0.002),
            "1d": make_ohlcv(n=100, base_price=100, trend=-0.001),
        }
        result = compute_composite_score(dfs)
        self.assertIn("score", result)
        self.assertIn("direction", result)
        self.assertIn("per_timeframe", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_composite_empty_dfs(self):
        result = compute_composite_score({})
        self.assertEqual(result["score"], 50)
        self.assertEqual(result["direction"], "WAIT")


if __name__ == "__main__":
    unittest.main()
