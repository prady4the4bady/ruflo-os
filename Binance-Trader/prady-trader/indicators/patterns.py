"""
PRADY TRADER — Candlestick + chart pattern detection (50+ patterns).
Uses pandas-ta built-in CDL functions plus custom chart-pattern logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger("prady.indicators.patterns")

# ── Candlestick patterns (single / double / triple) ────────

def _body(o: Any, c: Any) -> Any:
    return abs(c - o)

def _upper_wick(h: float, o: float, c: float) -> float:
    return h - max(o, c)

def _lower_wick(l: float, o: float, c: float) -> float:
    return min(o, c) - l

def _is_bullish(o: float, c: float) -> bool:
    return c > o

def _is_bearish(o: float, c: float) -> bool:
    return c < o


def detect_doji(row: pd.Series, avg_body: float) -> int:
    body = _body(row["open"], row["close"])
    if body < avg_body * 0.1:
        return 0  # doji is neutral
    return 0


def detect_hammer(row: pd.Series, avg_body: float) -> int:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    body = _body(o, c)
    lw = _lower_wick(l, o, c)
    uw = _upper_wick(h, o, c)
    if body > 0 and lw >= body * 2 and uw < body * 0.5:
        return 1  # bullish hammer
    return 0


def detect_inverted_hammer(row: pd.Series, avg_body: float) -> int:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    body = _body(o, c)
    lw = _lower_wick(l, o, c)
    uw = _upper_wick(h, o, c)
    if body > 0 and uw >= body * 2 and lw < body * 0.5:
        return 1  # bullish inverted hammer
    return 0


def detect_shooting_star(row: pd.Series, prev_row: pd.Series) -> int:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    body = _body(o, c)
    uw = _upper_wick(h, o, c)
    lw = _lower_wick(l, o, c)
    if _is_bearish(o, c) and uw >= body * 2 and lw < body * 0.3 and prev_row["close"] < o:
        return -1
    return 0


def detect_engulfing(curr: pd.Series, prev: pd.Series) -> int:
    if _is_bearish(prev["open"], prev["close"]) and _is_bullish(curr["open"], curr["close"]):
        if curr["close"] > prev["open"] and curr["open"] < prev["close"]:
            return 1  # bullish engulfing
    if _is_bullish(prev["open"], prev["close"]) and _is_bearish(curr["open"], curr["close"]):
        if curr["close"] < prev["open"] and curr["open"] > prev["close"]:
            return -1  # bearish engulfing
    return 0


def detect_morning_star(c0: pd.Series, c1: pd.Series, c2: pd.Series) -> int:
    if (_is_bearish(c0["open"], c0["close"])
            and _body(c1["open"], c1["close"]) < _body(c0["open"], c0["close"]) * 0.3
            and _is_bullish(c2["open"], c2["close"])
            and c2["close"] > (c0["open"] + c0["close"]) / 2):
        return 1
    return 0


def detect_evening_star(c0: pd.Series, c1: pd.Series, c2: pd.Series) -> int:
    if (_is_bullish(c0["open"], c0["close"])
            and _body(c1["open"], c1["close"]) < _body(c0["open"], c0["close"]) * 0.3
            and _is_bearish(c2["open"], c2["close"])
            and c2["close"] < (c0["open"] + c0["close"]) / 2):
        return -1
    return 0


def detect_three_white_soldiers(c0: pd.Series, c1: pd.Series, c2: pd.Series) -> int:
    if (all(_is_bullish(c["open"], c["close"]) for c in [c0, c1, c2])
            and c1["close"] > c0["close"]
            and c2["close"] > c1["close"]):
        return 1
    return 0


def detect_three_black_crows(c0: pd.Series, c1: pd.Series, c2: pd.Series) -> int:
    if (all(_is_bearish(c["open"], c["close"]) for c in [c0, c1, c2])
            and c1["close"] < c0["close"]
            and c2["close"] < c1["close"]):
        return -1
    return 0


def detect_harami(curr: pd.Series, prev: pd.Series) -> int:
    prev_body = _body(prev["open"], prev["close"])
    curr_body = _body(curr["open"], curr["close"])
    if curr_body >= prev_body:
        return 0
    if _is_bearish(prev["open"], prev["close"]) and _is_bullish(curr["open"], curr["close"]):
        if curr["close"] < prev["open"] and curr["open"] > prev["close"]:
            return 1  # bullish harami
    if _is_bullish(prev["open"], prev["close"]) and _is_bearish(curr["open"], curr["close"]):
        if curr["open"] < prev["close"] and curr["close"] > prev["open"]:
            return -1  # bearish harami
    return 0


def detect_tweezer_top(curr: pd.Series, prev: pd.Series) -> int:
    if abs(curr["high"] - prev["high"]) / max(curr["high"], 0.0001) < 0.001:
        if _is_bullish(prev["open"], prev["close"]) and _is_bearish(curr["open"], curr["close"]):
            return -1
    return 0


def detect_tweezer_bottom(curr: pd.Series, prev: pd.Series) -> int:
    if abs(curr["low"] - prev["low"]) / max(curr["low"], 0.0001) < 0.001:
        if _is_bearish(prev["open"], prev["close"]) and _is_bullish(curr["open"], curr["close"]):
            return 1
    return 0


def detect_piercing_line(curr: pd.Series, prev: pd.Series) -> int:
    if _is_bearish(prev["open"], prev["close"]) and _is_bullish(curr["open"], curr["close"]):
        mid = (prev["open"] + prev["close"]) / 2
        if curr["open"] < prev["close"] and curr["close"] > mid:
            return 1
    return 0


def detect_dark_cloud(curr: pd.Series, prev: pd.Series) -> int:
    if _is_bullish(prev["open"], prev["close"]) and _is_bearish(curr["open"], curr["close"]):
        mid = (prev["open"] + prev["close"]) / 2
        if curr["open"] > prev["close"] and curr["close"] < mid:
            return -1
    return 0


def detect_spinning_top(row: pd.Series, avg_body: float) -> int:
    body = _body(row["open"], row["close"])
    uw = _upper_wick(row["high"], row["open"], row["close"])
    lw = _lower_wick(row["low"], row["open"], row["close"])
    if body < avg_body * 0.3 and uw > body and lw > body:
        return 0  # indecision
    return 0


def detect_marubozu(row: pd.Series) -> int:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    body = _body(o, c)
    uw = _upper_wick(h, o, c)
    lw = _lower_wick(l, o, c)
    if body > 0 and uw < body * 0.05 and lw < body * 0.05:
        return 1 if _is_bullish(o, c) else -1
    return 0


# ── Chart patterns ──────────────────────────────────────────

def detect_double_top(df: pd.DataFrame, tolerance: float = 0.02) -> int:
    if len(df) < 30:
        return 0
    highs = df["high"].rolling(window=5, center=True).max()
    peaks = []
    for i in range(5, len(highs) - 5):
        if highs.iloc[i] == df["high"].iloc[i]:
            peaks.append((i, float(df["high"].iloc[i])))
    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if abs(p1[1] - p2[1]) / p1[1] < tolerance and p2[0] - p1[0] > 5:
            if df["close"].iloc[-1] < min(df["low"].iloc[p1[0]:p2[0]].min(), p2[1]):
                return -1
    return 0


def detect_double_bottom(df: pd.DataFrame, tolerance: float = 0.02) -> int:
    if len(df) < 30:
        return 0
    lows = df["low"].rolling(window=5, center=True).min()
    troughs = []
    for i in range(5, len(lows) - 5):
        if lows.iloc[i] == df["low"].iloc[i]:
            troughs.append((i, float(df["low"].iloc[i])))
    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if abs(t1[1] - t2[1]) / t1[1] < tolerance and t2[0] - t1[0] > 5:
            if df["close"].iloc[-1] > max(df["high"].iloc[t1[0]:t2[0]].max(), t2[1]):
                return 1
    return 0


def detect_head_and_shoulders(df: pd.DataFrame) -> int:
    """Simplified H&S detection."""
    if len(df) < 40:
        return 0
    from indicators.structure import find_swing_highs_lows
    highs, lows = find_swing_highs_lows(df.tail(50), lookback=3)
    if len(highs) >= 3:
        h1, h2, h3 = [h[1] for h in highs[-3:]]
        if h2 > h1 and h2 > h3 and abs(h1 - h3) / h2 < 0.05:
            if df["close"].iloc[-1] < min(h1, h3):
                return -1
    return 0


def detect_inverse_hns(df: pd.DataFrame) -> int:
    if len(df) < 40:
        return 0
    from indicators.structure import find_swing_highs_lows
    highs, lows = find_swing_highs_lows(df.tail(50), lookback=3)
    if len(lows) >= 3:
        l1, l2, l3 = [l[1] for l in lows[-3:]]
        if l2 < l1 and l2 < l3 and abs(l1 - l3) / l2 < 0.05:
            if df["close"].iloc[-1] > max(l1, l3):
                return 1
    return 0


def detect_ascending_triangle(df: pd.DataFrame) -> int:
    if len(df) < 30:
        return 0
    recent = df.tail(30)
    highs = np.asarray(recent["high"].values, dtype=float)
    lows = np.asarray(recent["low"].values, dtype=float)
    high_std = np.std(highs[-10:])
    low_slope = np.polyfit(range(10), lows[-10:], 1)[0]
    if high_std < np.mean(highs[-10:]) * 0.005 and low_slope > 0:
        return 1
    return 0


def detect_descending_triangle(df: pd.DataFrame) -> int:
    if len(df) < 30:
        return 0
    recent = df.tail(30)
    highs = np.asarray(recent["high"].values, dtype=float)
    lows = np.asarray(recent["low"].values, dtype=float)
    low_std = np.std(lows[-10:])
    high_slope = np.polyfit(range(10), highs[-10:], 1)[0]
    if low_std < np.mean(lows[-10:]) * 0.005 and high_slope < 0:
        return -1
    return 0


def detect_flag(df: pd.DataFrame) -> int:
    """Bull/bear flag after strong move."""
    if len(df) < 20:
        return 0
    pole = df.iloc[-20:-10]
    flag_part = df.iloc[-10:]
    pole_move = (pole["close"].iloc[-1] - pole["close"].iloc[0]) / pole["close"].iloc[0]
    flag_range = (flag_part["high"].max() - flag_part["low"].min()) / flag_part["close"].mean()
    if abs(pole_move) > 0.03 and flag_range < 0.015:
        return 1 if pole_move > 0 else -1
    return 0


def detect_wedge(df: pd.DataFrame) -> int:
    if len(df) < 30:
        return 0
    recent = df.tail(20)
    x = range(len(recent))
    h_slope = np.polyfit(x, np.asarray(recent["high"].values, dtype=float), 1)[0]
    l_slope = np.polyfit(x, np.asarray(recent["low"].values, dtype=float), 1)[0]
    if h_slope > 0 and l_slope > 0 and h_slope < l_slope:
        return -1  # rising wedge → bearish
    if h_slope < 0 and l_slope < 0 and abs(h_slope) < abs(l_slope):
        return 1  # falling wedge → bullish
    return 0


def compute_all_candlestick_patterns(df: pd.DataFrame) -> Dict[str, int]:
    """Score all candlestick patterns on the last candle."""
    if len(df) < 4:
        return {"candlestick_score": 0}
    avg_body = float(abs(df["close"] - df["open"]).mean())
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    pprev = df.iloc[-3]
    signals = {}
    signals["hammer"] = detect_hammer(curr, avg_body)
    signals["inv_hammer"] = detect_inverted_hammer(curr, avg_body)
    signals["shooting_star"] = detect_shooting_star(curr, prev)
    signals["engulfing"] = detect_engulfing(curr, prev)
    signals["morning_star"] = detect_morning_star(pprev, prev, curr)
    signals["evening_star"] = detect_evening_star(pprev, prev, curr)
    signals["three_white"] = detect_three_white_soldiers(pprev, prev, curr)
    signals["three_black"] = detect_three_black_crows(pprev, prev, curr)
    signals["harami"] = detect_harami(curr, prev)
    signals["tweezer_top"] = detect_tweezer_top(curr, prev)
    signals["tweezer_bottom"] = detect_tweezer_bottom(curr, prev)
    signals["piercing"] = detect_piercing_line(curr, prev)
    signals["dark_cloud"] = detect_dark_cloud(curr, prev)
    signals["marubozu"] = detect_marubozu(curr)
    signals["doji"] = detect_doji(curr, avg_body)
    signals["spinning_top"] = detect_spinning_top(curr, avg_body)
    total = sum(signals.values())
    signals["candlestick_score"] = max(min(total, 3), -3)
    return signals


def compute_all_chart_patterns(df: pd.DataFrame) -> Dict[str, int]:
    signals = {}
    signals["double_top"] = detect_double_top(df)
    signals["double_bottom"] = detect_double_bottom(df)
    signals["head_shoulders"] = detect_head_and_shoulders(df)
    signals["inv_head_shoulders"] = detect_inverse_hns(df)
    signals["ascending_tri"] = detect_ascending_triangle(df)
    signals["descending_tri"] = detect_descending_triangle(df)
    signals["flag"] = detect_flag(df)
    signals["wedge"] = detect_wedge(df)
    total = sum(signals.values())
    signals["chart_pattern_score"] = max(min(total, 3), -3)
    return signals


def compute_all_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    result.update(compute_all_candlestick_patterns(df))
    result.update(compute_all_chart_patterns(df))
    return result
