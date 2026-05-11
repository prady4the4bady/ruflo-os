"""
PRADY TRADER — Market structure indicators.
Support/Resistance, Pivot Points, Fibonacci levels,
Break of Structure (BOS), Change of Character (CHoCH).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from config.constants import FIBONACCI_LEVELS, STRUCTURE_LOOKBACK

logger = logging.getLogger("prady.indicators.structure")


def find_swing_highs_lows(
    df: pd.DataFrame, lookback: int = 5
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Identify swing highs and swing lows using rolling window."""
    highs: List[Tuple[int, float]] = []
    lows: List[Tuple[int, float]] = []
    high_vals = df["high"].values
    low_vals = df["low"].values
    n = len(df)
    for i in range(lookback, n - lookback):
        is_high = True
        is_low = True
        for j in range(1, lookback + 1):
            if high_vals[i] <= high_vals[i - j] or high_vals[i] <= high_vals[i + j]:
                is_high = False
            if low_vals[i] >= low_vals[i - j] or low_vals[i] >= low_vals[i + j]:
                is_low = False
        if is_high:
            highs.append((i, float(high_vals[i])))
        if is_low:
            lows.append((i, float(low_vals[i])))
    return highs, lows


def compute_support_resistance(df: pd.DataFrame, lookback: int = STRUCTURE_LOOKBACK) -> Dict[str, Any]:
    """Find key support/resistance levels from swing points."""
    if len(df) < lookback:
        return {"support_levels": [], "resistance_levels": [], "sr_signal": 0}
    recent = df.tail(lookback).copy()
    highs, lows = find_swing_highs_lows(recent)
    close = df["close"].iloc[-1]
    resistance = sorted(set(h[1] for h in highs), reverse=True)[:5]
    support = sorted(set(l[1] for l in lows))[:5]
    sig = 0
    if support:
        nearest_sup = min(support, key=lambda s: abs(s - close))
        if close <= nearest_sup * 1.005:
            sig = 1  # near support → bounce expected
    if resistance:
        nearest_res = min(resistance, key=lambda r: abs(r - close))
        if close >= nearest_res * 0.995:
            sig = -1  # near resistance → rejection expected
    return {
        "support_levels": support,
        "resistance_levels": resistance,
        "sr_signal": sig,
    }


def compute_pivot_points(df: pd.DataFrame) -> Dict[str, Any]:
    """Classic pivot points from previous candle."""
    if len(df) < 2:
        return {"pivot": 0.0, "pivot_signal": 0}
    prev = df.iloc[-2]
    h, l, c = float(prev["high"]), float(prev["low"]), float(prev["close"])
    pivot = (h + l + c) / 3
    r1 = 2 * pivot - l
    s1 = 2 * pivot - h
    r2 = pivot + (h - l)
    s2 = pivot - (h - l)
    close = float(df["close"].iloc[-1])
    sig = 0
    if close > r1:
        sig = 1
    elif close < s1:
        sig = -1
    return {
        "pivot": pivot,
        "r1": r1, "r2": r2,
        "s1": s1, "s2": s2,
        "pivot_signal": sig,
    }


def compute_fibonacci_levels(df: pd.DataFrame, lookback: int = STRUCTURE_LOOKBACK) -> Dict[str, Any]:
    """Fibonacci retracement from recent high/low range."""
    recent = df.tail(lookback)
    high = float(recent["high"].max())
    low = float(recent["low"].min())
    diff = high - low
    if diff == 0:
        return {"fib_levels": {}, "fib_signal": 0}
    levels = {}
    for fib in FIBONACCI_LEVELS:
        levels[f"fib_{fib}"] = high - diff * fib
    close = float(df["close"].iloc[-1])
    sig = 0
    fib_618 = levels.get("fib_0.618", 0)
    fib_382 = levels.get("fib_0.382", 0)
    if abs(close - fib_618) / close < 0.005:
        sig = 1  # at golden ratio support
    elif abs(close - fib_382) / close < 0.005:
        sig = -1  # at 38.2% resistance
    return {"fib_levels": levels, "fib_signal": sig}


def detect_bos(df: pd.DataFrame, lookback: int = 20) -> Dict[str, Any]:
    """Break of Structure detection.
    Bullish BOS: price breaks above the most recent swing high.
    Bearish BOS: price breaks below the most recent swing low.
    """
    if len(df) < lookback + 10:
        return {"bos_signal": 0, "bos_type": "none"}
    recent = df.tail(lookback + 10).copy()
    highs, lows = find_swing_highs_lows(recent, lookback=3)
    close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else close
    if highs:
        last_sh = highs[-1][1]
        if prev_close <= last_sh and close > last_sh:
            return {"bos_signal": 1, "bos_type": "bullish"}
    if lows:
        last_sl = lows[-1][1]
        if prev_close >= last_sl and close < last_sl:
            return {"bos_signal": -1, "bos_type": "bearish"}
    return {"bos_signal": 0, "bos_type": "none"}


def detect_choch(df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
    """Change of Character detection.
    CHoCH = first break against the prevailing trend.
    In an uptrend: a break below the last higher-low is bearish CHoCH.
    In a downtrend: a break above the last lower-high is bullish CHoCH.
    """
    if len(df) < lookback + 10:
        return {"choch_signal": 0, "choch_type": "none"}
    recent = df.tail(lookback + 10).copy()
    highs, lows = find_swing_highs_lows(recent, lookback=3)
    if len(highs) < 2 or len(lows) < 2:
        return {"choch_signal": 0, "choch_type": "none"}
    close = float(df["close"].iloc[-1])
    # Uptrend: higher highs
    last_two_highs = [h[1] for h in highs[-2:]]
    last_two_lows = [l[1] for l in lows[-2:]]
    in_uptrend = last_two_highs[1] > last_two_highs[0] and last_two_lows[1] > last_two_lows[0]
    in_downtrend = last_two_highs[1] < last_two_highs[0] and last_two_lows[1] < last_two_lows[0]
    if in_uptrend:
        last_hl = last_two_lows[1]
        if close < last_hl:
            return {"choch_signal": -1, "choch_type": "bearish"}
    elif in_downtrend:
        last_lh = last_two_highs[1]
        if close > last_lh:
            return {"choch_signal": 1, "choch_type": "bullish"}
    return {"choch_signal": 0, "choch_type": "none"}


def compute_all_structure(df: pd.DataFrame) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}
    signals.update(compute_support_resistance(df))
    signals.update(compute_pivot_points(df))
    signals.update(compute_fibonacci_levels(df))
    signals.update(detect_bos(df))
    signals.update(detect_choch(df))
    return signals
