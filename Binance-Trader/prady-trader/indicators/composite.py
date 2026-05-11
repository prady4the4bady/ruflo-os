"""
PRADY TRADER — Composite multi-indicator scoring engine.
Aggregates all indicator modules into a single 0-100 bull/bear score.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd

from config.constants import TIMEFRAME_WEIGHTS, TIMEFRAMES
from indicators.trend import compute_all_trend
from indicators.momentum import compute_all_momentum
from indicators.volatility import compute_all_volatility
from indicators.volume import compute_all_volume
from indicators.structure import compute_all_structure
from indicators.patterns import compute_all_patterns

logger = logging.getLogger("prady.indicators.composite")


def _extract_signal_values(signals: Dict[str, Any]) -> list[int]:
    """Pull out integer signal values from a mixed dict."""
    out = []
    for k, v in signals.items():
        if isinstance(v, int) and "signal" in k or k.endswith("_signal"):
            out.append(v)
        elif isinstance(v, int) and k in (
            "dema", "tema", "zlema", "hma", "supertrend",
            "ichimoku", "psar", "aroon", "vwap",
        ):
            out.append(v)
    return out


def score_single_timeframe(df: pd.DataFrame) -> Dict[str, Any]:
    """Run all indicators on a single timeframe DataFrame and return score 0-100."""
    if df.empty or len(df) < 30:
        return {
            "score": 50,
            "direction": "WAIT",
            "confidence": 0.0,
            "bull_count": 0,
            "bear_count": 0,
            "neutral_count": 0,
            "signals": {},
        }

    all_signals: Dict[str, Any] = {}
    all_signals.update(compute_all_trend(df))
    all_signals.update(compute_all_momentum(df))
    all_signals.update(compute_all_volatility(df))
    all_signals.update(compute_all_volume(df))
    all_signals.update(compute_all_structure(df))
    all_signals.update(compute_all_patterns(df))

    signal_values = _extract_signal_values(all_signals)
    # Also count named directional signals
    for k, v in all_signals.items():
        if isinstance(v, int) and k not in ("candlestick_score", "chart_pattern_score") and "_value" not in k:
            if v not in signal_values:
                signal_values.append(v)

    bull_count = sum(1 for s in signal_values if s > 0)
    bear_count = sum(1 for s in signal_values if s < 0)
    neutral_count = sum(1 for s in signal_values if s == 0)
    total = len(signal_values)
    if total == 0:
        return {
            "score": 50, "direction": "WAIT", "confidence": 0.0,
            "bull_count": 0, "bear_count": 0, "neutral_count": 0,
            "signals": all_signals,
        }

    # net signal: +1 each bull, -1 each bear → map to 0-100
    net = sum(signal_values)
    score = 50 + (net / total) * 50
    score = max(0, min(100, score))

    if score > 60:
        direction = "LONG"
    elif score < 40:
        direction = "SHORT"
    else:
        direction = "WAIT"

    active_signals = bull_count + bear_count
    agreement = max(bull_count, bear_count) / max(active_signals, 1)
    confidence = agreement * (active_signals / max(total, 1))

    return {
        "score": round(score, 2),
        "direction": direction,
        "confidence": round(confidence, 4),
        "bull_count": bull_count,
        "bear_count": bear_count,
        "neutral_count": neutral_count,
        "signals": all_signals,
    }


def compute_composite_score(
    dataframes: Dict[str, pd.DataFrame],
    timeframe_weights: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """Multi-timeframe composite scoring.
    
    Args:
        dataframes: mapping of timeframe → OHLCV DataFrame
        timeframe_weights: optional override for weighting
    
    Returns:
        Combined score 0-100 with direction and confidence.
    """
    weights = timeframe_weights or TIMEFRAME_WEIGHTS
    total_weight = 0.0
    weighted_score = 0.0
    per_tf: Dict[str, Dict[str, Any]] = {}

    for tf, df in dataframes.items():
        w = weights.get(tf, 0.0)
        if w == 0 or df.empty:
            continue
        tf_result = score_single_timeframe(df)
        per_tf[tf] = tf_result
        weighted_score += tf_result["score"] * w
        total_weight += w

    if total_weight == 0:
        return {
            "score": 50,
            "direction": "WAIT",
            "confidence": 0.0,
            "per_timeframe": per_tf,
        }

    final_score = weighted_score / total_weight
    final_score = max(0, min(100, final_score))

    if final_score > 60:
        direction = "LONG"
    elif final_score < 40:
        direction = "SHORT"
    else:
        direction = "WAIT"

    confidences = [r["confidence"] for r in per_tf.values() if r["confidence"] > 0]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    agreement = sum(1 for r in per_tf.values() if r["direction"] == direction) / max(len(per_tf), 1)
    composite_confidence = avg_conf * agreement

    return {
        "score": round(final_score, 2),
        "direction": direction,
        "confidence": round(composite_confidence, 4),
        "per_timeframe": per_tf,
    }
