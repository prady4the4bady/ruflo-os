"""
PRADY TRADER — Volatility indicators.
Bollinger Bands, ATR, Keltner Channel, Donchian Channel,
Chaikin Volatility, Historical Volatility, VIX-style index.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np
import warnings

import pandas as pd

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*copy_on_write.*")
    import pandas_ta as ta

from config.constants import (
    ATR_PERIOD,
    BOLLINGER_PERIOD,
    BOLLINGER_STD,
    DONCHIAN_PERIOD,
    KELTNER_MULT,
    KELTNER_PERIOD,
)

logger = logging.getLogger("prady.indicators.volatility")


def compute_bollinger_signal(df: pd.DataFrame) -> Dict[str, Any]:
    bb = ta.bbands(df["close"], length=BOLLINGER_PERIOD, lower_std=BOLLINGER_STD, upper_std=BOLLINGER_STD)
    if bb is None or bb.empty:
        return {"bb_signal": 0, "bb_position": 0.5, "bb_width": 0.0}
    lower_col = [c for c in bb.columns if "BBL_" in c]
    mid_col = [c for c in bb.columns if "BBM_" in c]
    upper_col = [c for c in bb.columns if "BBU_" in c]
    bw_col = [c for c in bb.columns if "BBB_" in c]
    if not lower_col or not upper_col or not mid_col:
        return {"bb_signal": 0, "bb_position": 0.5, "bb_width": 0.0}
    lower = bb[lower_col[0]].iloc[-1]
    upper = bb[upper_col[0]].iloc[-1]
    mid = bb[mid_col[0]].iloc[-1]
    bw = bb[bw_col[0]].iloc[-1] if bw_col else 0.0
    close = df["close"].iloc[-1]
    if pd.isna(lower) or pd.isna(upper):
        return {"bb_signal": 0, "bb_position": 0.5, "bb_width": 0.0}
    band_range = upper - lower
    position = (close - lower) / band_range if band_range > 0 else 0.5
    sig = 0
    if close <= lower:
        sig = 1  # price at lower band → bullish bounce
    elif close >= upper:
        sig = -1  # price at upper band → bearish pullback
    return {
        "bb_signal": sig,
        "bb_position": float(position),
        "bb_width": float(bw) if not pd.isna(bw) else 0.0,
    }


def compute_atr(df: pd.DataFrame) -> Dict[str, Any]:
    atr = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)
    if atr is None or atr.empty or pd.isna(atr.iloc[-1]):
        return {"atr_value": 0.0, "atr_pct": 0.0}
    val = float(atr.iloc[-1])
    close = df["close"].iloc[-1]
    pct = (val / close * 100) if close > 0 else 0.0
    return {"atr_value": val, "atr_pct": pct}


def compute_keltner_signal(df: pd.DataFrame) -> Dict[str, Any]:
    kc = ta.kc(
        df["high"], df["low"], df["close"],
        length=KELTNER_PERIOD, scalar=KELTNER_MULT,
    )
    if kc is None or kc.empty:
        return {"keltner_signal": 0}
    lower_col = [c for c in kc.columns if "KCL" in c]
    upper_col = [c for c in kc.columns if "KCU" in c]
    if not lower_col or not upper_col:
        return {"keltner_signal": 0}
    lower = kc[lower_col[0]].iloc[-1]
    upper = kc[upper_col[0]].iloc[-1]
    close = df["close"].iloc[-1]
    if pd.isna(lower) or pd.isna(upper):
        return {"keltner_signal": 0}
    if close <= lower:
        return {"keltner_signal": 1}
    elif close >= upper:
        return {"keltner_signal": -1}
    return {"keltner_signal": 0}


def compute_donchian_signal(df: pd.DataFrame) -> Dict[str, Any]:
    dc = ta.donchian(df["high"], df["low"], lower_length=DONCHIAN_PERIOD, upper_length=DONCHIAN_PERIOD)
    if dc is None or dc.empty:
        return {"donchian_signal": 0}
    lower_col = [c for c in dc.columns if "DCL" in c]
    upper_col = [c for c in dc.columns if "DCU" in c]
    mid_col = [c for c in dc.columns if "DCM" in c]
    if not lower_col or not upper_col:
        return {"donchian_signal": 0}
    lower = dc[lower_col[0]].iloc[-1]
    upper = dc[upper_col[0]].iloc[-1]
    close = df["close"].iloc[-1]
    if pd.isna(lower) or pd.isna(upper):
        return {"donchian_signal": 0}
    if close >= upper:
        return {"donchian_signal": 1}  # breakout up
    elif close <= lower:
        return {"donchian_signal": -1}  # breakout down
    return {"donchian_signal": 0}


def compute_chaikin_volatility(df: pd.DataFrame, period: int = 10) -> Dict[str, Any]:
    hl_diff = df["high"] - df["low"]
    ema_hl = hl_diff.ewm(span=period, adjust=False).mean()
    cv: pd.Series = ema_hl.pct_change(periods=period) * 100
    if cv.empty or pd.isna(cv.iloc[-1]):
        return {"chaikin_vol": 0.0}
    return {"chaikin_vol": float(cv.iloc[-1])}


def compute_historical_volatility(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    log_returns = np.log(df["close"] / df["close"].shift(1))  # type: ignore[assignment]
    hv = log_returns.rolling(window=period).std() * np.sqrt(252) * 100
    if hv.empty or pd.isna(hv.iloc[-1]):
        return {"hist_vol": 0.0}
    return {"hist_vol": float(hv.iloc[-1])}


def compute_vix_style_index(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    """Simple VIX-like index based on ATR percentage expansion."""
    atr = ta.atr(df["high"], df["low"], df["close"], length=period)
    if atr is None or atr.empty:
        return {"vix_index": 0.0, "vix_signal": 0}
    avg_atr = atr.rolling(window=50).mean()
    if avg_atr.empty or pd.isna(avg_atr.iloc[-1]) or avg_atr.iloc[-1] == 0:
        return {"vix_index": 0.0, "vix_signal": 0}
    ratio = float(atr.iloc[-1] / avg_atr.iloc[-1])
    vix = ratio * 50
    sig = 0
    if vix > 80:
        sig = 1  # extreme vol → contrarian bullish
    elif vix < 20:
        sig = -1  # low vol → complacency → bearish
    return {"vix_index": vix, "vix_signal": sig}


def compute_all_volatility(df: pd.DataFrame) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}
    signals.update(compute_bollinger_signal(df))
    signals.update(compute_atr(df))
    signals.update(compute_keltner_signal(df))
    signals.update(compute_donchian_signal(df))
    signals.update(compute_chaikin_volatility(df))
    signals.update(compute_historical_volatility(df))
    signals.update(compute_vix_style_index(df))
    return signals
