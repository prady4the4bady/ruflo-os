from __future__ import annotations

import pandas as pd

from data.orderflow import OrderFlowMetrics
from execution.strategies import (
    StrategySignal,
    build_advanced_quant_analysis_signal,
    build_core_financial_strength_signal,
    build_dual_mode_financial_intelligence_signal,
    build_cumulative_volume_delta_reversal_signal,
    build_failed_auction_delta_signal,
    build_liquidity_sweep_reclaim_signal,
    fuse_strategy_signals,
)


def _build_bullish_sweep_frame() -> pd.DataFrame:
    candles = []
    price = 100.0

    for index in range(30):
        open_price = price
        close_price = price + (0.2 if index % 2 == 0 else -0.1)
        high = max(open_price, close_price) + 0.6
        low = min(open_price, close_price) - 0.6
        candles.append(
            {
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close_price, 4),
                "volume": 1000 + (index % 5) * 40,
            }
        )
        price = close_price

    candles.extend(
        [
            {"open": 100.5, "high": 101.0, "low": 99.8, "close": 100.2, "volume": 1000},
            {"open": 100.2, "high": 100.5, "low": 99.4, "close": 99.8, "volume": 980},
            {"open": 99.8, "high": 100.1, "low": 98.9, "close": 99.3, "volume": 1010},
            {"open": 99.3, "high": 99.6, "low": 98.3, "close": 98.8, "volume": 1050},
            {"open": 98.8, "high": 99.3, "low": 97.4, "close": 98.9, "volume": 1200},
            {"open": 98.9, "high": 100.0, "low": 98.7, "close": 99.7, "volume": 1100},
            {"open": 99.7, "high": 100.4, "low": 99.5, "close": 100.0, "volume": 1150},
            {"open": 100.0, "high": 100.2, "low": 99.3, "close": 99.6, "volume": 1080},
            {"open": 99.6, "high": 99.9, "low": 99.1, "close": 99.4, "volume": 1020},
            {"open": 99.6, "high": 101.7, "low": 96.8, "close": 101.3, "volume": 2600},
        ]
    )
    return pd.DataFrame(candles)


def _build_bullish_failed_auction_frame() -> pd.DataFrame:
    candles = []
    price = 105.0

    for index in range(26):
        open_price = price
        close_price = price - (0.35 if index % 2 == 0 else 0.2)
        high = max(open_price, close_price) + 0.45
        low = min(open_price, close_price) - 0.5
        candles.append(
            {
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close_price, 4),
                "volume": 950 + (index % 4) * 25,
            }
        )
        price = close_price

    candles.extend(
        [
            {"open": 96.8, "high": 97.0, "low": 95.9, "close": 96.2, "volume": 920},
            {"open": 96.2, "high": 96.4, "low": 95.4, "close": 95.7, "volume": 910},
            {"open": 95.7, "high": 95.9, "low": 94.9, "close": 95.1, "volume": 900},
            {"open": 95.1, "high": 95.4, "low": 94.5, "close": 94.8, "volume": 905},
            {"open": 94.8, "high": 95.0, "low": 93.8, "close": 94.4, "volume": 910},
            {"open": 94.4, "high": 96.9, "low": 92.6, "close": 96.6, "volume": 2200},
        ]
    )
    return pd.DataFrame(candles)


def _build_bullish_cvd_divergence_frame() -> pd.DataFrame:
    candles = []
    price = 108.0

    for index in range(22):
        open_price = price
        close_price = price - (0.28 if index % 2 == 0 else 0.16)
        high = max(open_price, close_price) + 0.4
        low = min(open_price, close_price) - 0.45
        candles.append(
            {
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close_price, 4),
                "volume": 940 + (index % 4) * 20,
            }
        )
        price = close_price

    candles.extend(
        [
            {"open": 101.0, "high": 101.2, "low": 100.0, "close": 100.2, "volume": 1180},
            {"open": 100.2, "high": 100.4, "low": 99.2, "close": 99.4, "volume": 1220},
            {"open": 99.4, "high": 99.6, "low": 98.4, "close": 98.7, "volume": 1240},
            {"open": 98.7, "high": 98.9, "low": 97.6, "close": 97.9, "volume": 1260},
            {"open": 97.9, "high": 98.0, "low": 96.7, "close": 97.1, "volume": 1280},
            {"open": 97.1, "high": 97.3, "low": 96.0, "close": 96.3, "volume": 1300},
            {"open": 96.3, "high": 96.5, "low": 95.3, "close": 95.7, "volume": 1320},
            {"open": 95.7, "high": 95.9, "low": 94.8, "close": 95.0, "volume": 1340},
            {"open": 95.0, "high": 95.2, "low": 94.3, "close": 94.5, "volume": 1360},
            {"open": 94.4, "high": 95.1, "low": 94.0, "close": 94.9, "volume": 1700},
            {"open": 94.9, "high": 95.5, "low": 94.6, "close": 95.3, "volume": 1750},
            {"open": 95.3, "high": 95.8, "low": 94.9, "close": 95.6, "volume": 1680},
            {"open": 95.6, "high": 95.9, "low": 95.1, "close": 95.4, "volume": 820},
            {"open": 95.4, "high": 95.9, "low": 95.1, "close": 95.8, "volume": 1720},
            {"open": 95.8, "high": 96.2, "low": 95.4, "close": 96.0, "volume": 1760},
            {"open": 96.0, "high": 96.2, "low": 94.7, "close": 95.8, "volume": 840},
            {"open": 95.8, "high": 96.6, "low": 95.5, "close": 96.4, "volume": 1820},
            {"open": 96.1, "high": 97.5, "low": 95.4, "close": 97.2, "volume": 2300},
        ]
    )
    return pd.DataFrame(candles)


def _build_structural_bull_frame() -> pd.DataFrame:
    candles = []
    price = 100.0

    for index in range(64):
        open_price = price + (0.05 if index % 3 == 0 else -0.03)
        close_price = open_price + 0.34 + (0.02 if index % 5 == 0 else 0.0)
        high = close_price + 0.28
        low = open_price - 0.18
        candles.append(
            {
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close_price, 4),
                "volume": 950 + index * 12 + (180 if index >= 56 else 0),
            }
        )
        price = close_price

    return pd.DataFrame(candles)


def test_build_liquidity_sweep_reclaim_signal_detects_bullish_setup():
    frame = _build_bullish_sweep_frame()
    orderflow = OrderFlowMetrics(
        imbalance=0.22,
        weighted_imbalance=0.26,
        top_level_imbalance=0.19,
        microprice_delta_bps=3.2,
        spread_bps=1.4,
        score=28.0,
        direction="LONG",
        confidence=0.62,
    )

    signal = build_liquidity_sweep_reclaim_signal("BTCUSDT", "5m", frame, orderflow)

    assert signal.direction == "LONG"
    assert signal.score >= 44.0
    assert signal.metadata["bullish_setup"]["sweep"] is True
    assert signal.metadata["bullish_setup"]["reclaim"] is True


def test_build_liquidity_sweep_reclaim_signal_requires_orderflow_confirmation():
    frame = _build_bullish_sweep_frame()

    signal = build_liquidity_sweep_reclaim_signal("BTCUSDT", "5m", frame, None)

    assert signal.direction == "NEUTRAL"
    assert "No confirmed" in signal.reasoning


def test_build_failed_auction_delta_signal_detects_bullish_reversal():
    frame = _build_bullish_failed_auction_frame()
    orderflow = OrderFlowMetrics(
        imbalance=0.18,
        weighted_imbalance=0.23,
        top_level_imbalance=0.17,
        microprice_delta_bps=2.5,
        spread_bps=1.2,
        score=24.0,
        direction="LONG",
        confidence=0.58,
    )

    signal = build_failed_auction_delta_signal("BTCUSDT", "5m", frame, orderflow)

    assert signal.direction == "LONG"
    assert signal.score >= 42.0
    assert signal.metadata["bullish_setup"]["failed_auction"] is True
    assert signal.metadata["bullish_setup"]["delta_divergence"] is True


def test_build_cumulative_volume_delta_reversal_signal_detects_bullish_reversal():
    frame = _build_bullish_cvd_divergence_frame()
    orderflow = OrderFlowMetrics(
        imbalance=0.19,
        weighted_imbalance=0.24,
        top_level_imbalance=0.18,
        microprice_delta_bps=2.8,
        spread_bps=1.3,
        score=26.0,
        direction="LONG",
        confidence=0.6,
    )

    signal = build_cumulative_volume_delta_reversal_signal("BTCUSDT", "5m", frame, orderflow)

    assert signal.direction == "LONG"
    assert signal.score >= 40.0
    assert signal.metadata["bullish_setup"]["cvd_divergence"] is True
    assert signal.metadata["bullish_setup"]["reclaim"] is True


def test_build_core_financial_strength_signal_detects_bullish_structure():
    frame = _build_structural_bull_frame()

    signal = build_core_financial_strength_signal("BTCUSDT", "1h", frame)

    assert signal.direction == "LONG"
    assert signal.score >= 18.0
    assert signal.metadata["trend_efficiency"] >= 0.55


def test_build_advanced_quant_analysis_signal_detects_bullish_factor_alignment():
    frame = _build_structural_bull_frame()

    signal = build_advanced_quant_analysis_signal("BTCUSDT", "1h", frame)

    assert signal.direction == "LONG"
    assert signal.score >= 18.0
    assert signal.metadata["consistency"] >= 0.55


def test_build_dual_mode_financial_intelligence_prefers_tactical_mode_with_orderflow():
    frame = _build_structural_bull_frame()
    frame.loc[len(frame) - 1, "open"] = float(frame.iloc[-2]["close"]) + 0.15
    frame.loc[len(frame) - 1, "close"] = float(frame.iloc[-2]["high"]) + 0.9
    frame.loc[len(frame) - 1, "high"] = float(frame.iloc[-1]["close"]) + 0.3
    frame.loc[len(frame) - 1, "low"] = float(frame.iloc[-1]["open"]) - 0.2
    frame.loc[len(frame) - 1, "volume"] = int(float(frame.iloc[-2]["volume"]) * 2.2)

    orderflow = OrderFlowMetrics(
        imbalance=0.27,
        weighted_imbalance=0.31,
        top_level_imbalance=0.22,
        microprice_delta_bps=4.2,
        spread_bps=1.1,
        score=34.0,
        direction="LONG",
        confidence=0.71,
    )

    signal = build_dual_mode_financial_intelligence_signal("BTCUSDT", "5m", frame, orderflow)

    assert signal.direction == "LONG"
    assert signal.score >= 25.0
    assert signal.metadata["selected_mode"] == "tactical"


def test_fuse_strategy_signals_ignores_flat_neutral_signals():
    result = fuse_strategy_signals(
        [
            StrategySignal(name="liquidity_sweep_avwap", direction="LONG", confidence=0.75, score=60.0),
            StrategySignal(name="news_velocity", direction="NEUTRAL", confidence=0.0, score=0.0),
            StrategySignal(name="failed_auction_delta", direction="NEUTRAL", confidence=0.0, score=0.0),
        ]
    )

    assert result.direction == "LONG"
    assert result.fused_score >= 59.0
    assert result.active_count == 1
    assert result.contributing_count == 1


def test_fuse_strategy_signals_prioritizes_confirmed_local_setups():
    result = fuse_strategy_signals(
        [
            StrategySignal(name="liquidity_sweep_avwap", direction="LONG", confidence=0.78, score=52.0),
            StrategySignal(name="news_velocity", direction="SHORT", confidence=0.68, score=-40.0),
            StrategySignal(name="derivatives_divergence", direction="SHORT", confidence=0.62, score=-38.0),
        ]
    )

    assert result.direction == "LONG"
    assert result.fused_score > 15.0
    assert result.confidence >= 0.6


def test_fuse_strategy_signals_compounds_aligned_local_setups():
    result = fuse_strategy_signals(
        [
            StrategySignal(name="liquidity_sweep_avwap", direction="LONG", confidence=0.78, score=52.0),
            StrategySignal(name="cumulative_volume_delta_reversal", direction="LONG", confidence=0.74, score=48.0),
            StrategySignal(name="news_velocity", direction="SHORT", confidence=0.68, score=-40.0),
            StrategySignal(name="derivatives_divergence", direction="SHORT", confidence=0.62, score=-38.0),
        ]
    )

    assert result.direction == "LONG"
    assert result.fused_score > 20.0
    assert result.confidence >= 0.7


def test_fuse_strategy_signals_adds_core_intelligence_alignment_bias():
    result = fuse_strategy_signals(
        [
            StrategySignal(name="core_financial_strength", direction="LONG", confidence=0.74, score=32.0),
            StrategySignal(name="advanced_quant_analysis", direction="LONG", confidence=0.71, score=28.0),
            StrategySignal(name="dual_mode_financial_intelligence", direction="LONG", confidence=0.76, score=35.0),
            StrategySignal(name="news_velocity", direction="SHORT", confidence=0.65, score=-30.0),
            StrategySignal(name="derivatives_divergence", direction="SHORT", confidence=0.62, score=-28.0),
        ]
    )

    assert result.direction == "LONG"
    assert result.fused_score > 15.0
    assert result.confidence >= 0.6
    assert "core_bias=" in result.reasoning