"""
PRADY TRADER — Volume indicators.
OBV, VWAP deviation, CMF, A/D Line, Elder Force Index,
Klinger Volume Oscillator, VROC (Volume Rate of Change).
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

from config.constants import CMF_PERIOD

logger = logging.getLogger("prady.indicators.volume")


def compute_obv_signal(df: pd.DataFrame) -> Dict[str, Any]:
    obv = ta.obv(df["close"], df["volume"])
    if obv is None or obv.empty:
        return {"obv_signal": 0, "obv_value": 0.0}
    if len(obv.dropna()) < 10:
        return {"obv_signal": 0, "obv_value": float(obv.iloc[-1]) if not pd.isna(obv.iloc[-1]) else 0.0}
    obv_sma = obv.rolling(window=10).mean()
    last_obv = obv.iloc[-1]
    last_sma = obv_sma.iloc[-1]
    if pd.isna(last_obv) or pd.isna(last_sma):
        return {"obv_signal": 0, "obv_value": 0.0}
    sig = 1 if last_obv > last_sma else (-1 if last_obv < last_sma else 0)
    return {"obv_signal": sig, "obv_value": float(last_obv)}


def compute_vwap_deviation(df: pd.DataFrame) -> Dict[str, Any]:
    if "volume" not in df.columns or df["volume"].sum() == 0:
        return {"vwap_dev": 0.0, "vwap_signal": 0}
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_tp_vol = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    vwap = cum_tp_vol / cum_vol
    if vwap.empty or pd.isna(vwap.iloc[-1]):
        return {"vwap_dev": 0.0, "vwap_signal": 0}
    close = df["close"].iloc[-1]
    dev = (close - vwap.iloc[-1]) / vwap.iloc[-1] * 100 if vwap.iloc[-1] != 0 else 0.0
    sig = 0
    if dev > 1.5:
        sig = -1  # overbought vs VWAP
    elif dev < -1.5:
        sig = 1  # oversold vs VWAP
    return {"vwap_dev": float(dev), "vwap_signal": sig}


def compute_cmf_signal(df: pd.DataFrame) -> Dict[str, Any]:
    cmf = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=CMF_PERIOD)
    if cmf is None or cmf.empty or pd.isna(cmf.iloc[-1]):
        return {"cmf_value": 0.0, "cmf_signal": 0}
    val = float(cmf.iloc[-1])
    if val > 0.1:
        sig = 1
    elif val < -0.1:
        sig = -1
    else:
        sig = 0
    return {"cmf_value": val, "cmf_signal": sig}


def compute_ad_line_signal(df: pd.DataFrame) -> Dict[str, Any]:
    ad = ta.ad(df["high"], df["low"], df["close"], df["volume"])
    if ad is None or ad.empty:
        return {"ad_signal": 0}
    if len(ad.dropna()) < 10:
        return {"ad_signal": 0}
    ad_sma = ad.rolling(window=10).mean()
    last_ad = ad.iloc[-1]
    last_sma = ad_sma.iloc[-1]
    if pd.isna(last_ad) or pd.isna(last_sma):
        return {"ad_signal": 0}
    return {"ad_signal": 1 if last_ad > last_sma else -1}


def compute_elder_force(df: pd.DataFrame, period: int = 13) -> Dict[str, Any]:
    close_diff = df["close"].diff()
    force = close_diff * df["volume"]
    ema_force = force.ewm(span=period, adjust=False).mean()
    if ema_force.empty or pd.isna(ema_force.iloc[-1]):
        return {"elder_force": 0.0, "elder_signal": 0}
    val = float(ema_force.iloc[-1])
    sig = 1 if val > 0 else (-1 if val < 0 else 0)
    return {"elder_force": val, "elder_signal": sig}


def compute_klinger_signal(df: pd.DataFrame) -> Dict[str, Any]:
    """Klinger Volume Oscillator approximation."""
    hlc = df["high"] + df["low"] + df["close"]
    dm = hlc.diff()
    trend = pd.Series(np.where(dm > 0, 1, -1), index=df.index)
    sv = trend * df["volume"]
    kvo = sv.ewm(span=34, adjust=False).mean() - sv.ewm(span=55, adjust=False).mean()
    signal_line = kvo.ewm(span=13, adjust=False).mean()
    if kvo.empty or pd.isna(kvo.iloc[-1]) or pd.isna(signal_line.iloc[-1]):
        return {"klinger_signal": 0}
    sig = 1 if kvo.iloc[-1] > signal_line.iloc[-1] else -1
    return {"klinger_signal": sig}


def compute_vroc(df: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
    vroc = df["volume"].pct_change(periods=period) * 100  # type: ignore[annotation-unchecked]
    if vroc.empty or pd.isna(vroc.iloc[-1]):
        return {"vroc_value": 0.0, "vroc_signal": 0}
    val = float(vroc.iloc[-1])
    sig = 0
    if val > 50:
        close_change = df["close"].iloc[-1] - df["close"].iloc[-2] if len(df) > 1 else 0
        sig = 1 if close_change > 0 else -1
    return {"vroc_value": val, "vroc_signal": sig}


def compute_all_volume(df: pd.DataFrame) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}
    signals.update(compute_obv_signal(df))
    signals.update(compute_vwap_deviation(df))
    signals.update(compute_cmf_signal(df))
    signals.update(compute_ad_line_signal(df))
    signals.update(compute_elder_force(df))
    signals.update(compute_klinger_signal(df))
    signals.update(compute_vroc(df))
    return signals
