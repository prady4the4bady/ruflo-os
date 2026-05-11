"""
PRADY TRADER — Trend indicators.
EMA, SMA, DEMA, TEMA, ZLEMA, HMA, Supertrend, MACD, ADX,
Ichimoku, Parabolic SAR, Aroon, VWAP.
Each function returns a signal: +1 BULL, -1 BEAR, 0 NEUTRAL.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import warnings

import numpy as np
import pandas as pd

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*copy_on_write.*")
    import pandas_ta as ta

from config.constants import (
    ADX_PERIOD,
    ADX_STRONG_TREND,
    EMA_PERIODS,
    ICHIMOKU_KIJUN,
    ICHIMOKU_SENKOU,
    ICHIMOKU_TENKAN,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    SUPERTREND_ATR_MULT,
    SUPERTREND_ATR_PERIOD,
)

logger = logging.getLogger("prady.indicators.trend")


def compute_ema_signals(df: pd.DataFrame) -> Dict[str, int]:
    signals: Dict[str, int] = {}
    close = df["close"]
    for period in EMA_PERIODS:
        ema = ta.ema(close, length=period)
        if ema is None or ema.empty:
            signals[f"ema_{period}"] = 0
            continue
        last_close = close.iloc[-1]
        last_ema = ema.iloc[-1]
        if pd.isna(last_ema):
            signals[f"ema_{period}"] = 0
        elif last_close > last_ema:
            signals[f"ema_{period}"] = 1
        elif last_close < last_ema:
            signals[f"ema_{period}"] = -1
        else:
            signals[f"ema_{period}"] = 0
    return signals


def compute_dema_signal(df: pd.DataFrame, period: int = 21) -> int:
    dema = ta.dema(df["close"], length=period)
    if dema is None or dema.empty or pd.isna(dema.iloc[-1]):
        return 0
    return 1 if df["close"].iloc[-1] > dema.iloc[-1] else -1


def compute_tema_signal(df: pd.DataFrame, period: int = 21) -> int:
    tema = ta.tema(df["close"], length=period)
    if tema is None or tema.empty or pd.isna(tema.iloc[-1]):
        return 0
    return 1 if df["close"].iloc[-1] > tema.iloc[-1] else -1


def compute_zlema_signal(df: pd.DataFrame, period: int = 21) -> int:
    lag = (period - 1) // 2
    adjusted = 2 * df["close"] - df["close"].shift(lag)
    zlema = adjusted.ewm(span=period, adjust=False).mean()
    if zlema.empty or pd.isna(zlema.iloc[-1]):
        return 0
    return 1 if df["close"].iloc[-1] > zlema.iloc[-1] else -1


def compute_hma_signal(df: pd.DataFrame, period: int = 21) -> int:
    hma = ta.hma(df["close"], length=period)
    if hma is None or hma.empty or pd.isna(hma.iloc[-1]):
        return 0
    if len(hma.dropna()) < 2:
        return 0
    valid = hma.dropna()
    if valid.iloc[-1] > valid.iloc[-2]:
        return 1
    elif valid.iloc[-1] < valid.iloc[-2]:
        return -1
    return 0


def compute_supertrend_signal(df: pd.DataFrame) -> int:
    st = ta.supertrend(
        df["high"], df["low"], df["close"],
        length=SUPERTREND_ATR_PERIOD,
        multiplier=SUPERTREND_ATR_MULT,
    )
    if st is None or st.empty:
        return 0
    direction_col = [c for c in st.columns if "SUPERTd" in c]
    if not direction_col:
        return 0
    last = st[direction_col[0]].iloc[-1]
    if pd.isna(last):
        return 0
    return 1 if last == 1 else -1


def compute_macd_signal(df: pd.DataFrame) -> Dict[str, Any]:
    macd_df = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    if macd_df is None or macd_df.empty:
        return {"macd_signal": 0, "macd_histogram": 0.0}
    cols = macd_df.columns.tolist()
    macd_col = [c for c in cols if "MACD_" in c and "MACDs" not in c and "MACDh" not in c]
    signal_col = [c for c in cols if "MACDs" in c]
    hist_col = [c for c in cols if "MACDh" in c]
    if not macd_col or not signal_col:
        return {"macd_signal": 0, "macd_histogram": 0.0}
    m = macd_df[macd_col[0]].iloc[-1]
    s = macd_df[signal_col[0]].iloc[-1]
    h = macd_df[hist_col[0]].iloc[-1] if hist_col else 0.0
    if pd.isna(m) or pd.isna(s):
        return {"macd_signal": 0, "macd_histogram": 0.0}
    sig = 1 if m > s else (-1 if m < s else 0)
    return {"macd_signal": sig, "macd_histogram": float(h)}


def compute_adx_signal(df: pd.DataFrame) -> Dict[str, Any]:
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=ADX_PERIOD)
    if adx_df is None or adx_df.empty:
        return {"adx_value": 0.0, "adx_trending": False}
    adx_col = [c for c in adx_df.columns if c.startswith("ADX_")]
    dmp_col = [c for c in adx_df.columns if c.startswith("DMP_")]
    dmn_col = [c for c in adx_df.columns if c.startswith("DMN_")]
    if not adx_col:
        return {"adx_value": 0.0, "adx_trending": False}
    adx_val = adx_df[adx_col[0]].iloc[-1]
    if pd.isna(adx_val):
        return {"adx_value": 0.0, "adx_trending": False}
    trending = adx_val >= ADX_STRONG_TREND
    direction = 0
    if dmp_col and dmn_col:
        dmp = adx_df[dmp_col[0]].iloc[-1]
        dmn = adx_df[dmn_col[0]].iloc[-1]
        if not pd.isna(dmp) and not pd.isna(dmn):
            direction = 1 if dmp > dmn else -1
    return {"adx_value": float(adx_val), "adx_trending": trending, "adx_direction": direction}


def compute_ichimoku_signal(df: pd.DataFrame) -> int:
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*'d' is deprecated.*", category=FutureWarning)
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        ichi = ta.ichimoku(
            df["high"], df["low"], df["close"],
            tenkan=ICHIMOKU_TENKAN, kijun=ICHIMOKU_KIJUN, senkou=ICHIMOKU_SENKOU,
        )
    if ichi is None or (isinstance(ichi, tuple) and len(ichi) == 0):
        return 0
    if isinstance(ichi, tuple):
        ichi_df = ichi[0]
    else:
        ichi_df = ichi
    if ichi_df is None or ichi_df.empty:
        return 0
    tenkan_col = [c for c in ichi_df.columns if "ITS" in c or "ISA" in c.upper() or "tenkan" in c.lower()]
    kijun_col = [c for c in ichi_df.columns if "IKS" in c or "ISB" in c.upper() or "kijun" in c.lower()]
    if not tenkan_col or not kijun_col:
        close = df["close"].iloc[-1]
        sa_cols = [c for c in ichi_df.columns if "ISA" in c]
        sb_cols = [c for c in ichi_df.columns if "ISB" in c]
        if sa_cols and sb_cols:
            sa = ichi_df[sa_cols[0]].iloc[-1]
            sb = ichi_df[sb_cols[0]].iloc[-1]
            if not pd.isna(sa) and not pd.isna(sb):
                cloud_top = max(sa, sb)
                cloud_bot = min(sa, sb)
                if close > cloud_top:
                    return 1
                elif close < cloud_bot:
                    return -1
        return 0
    t = ichi_df[tenkan_col[0]].iloc[-1]
    k = ichi_df[kijun_col[0]].iloc[-1]
    if pd.isna(t) or pd.isna(k):
        return 0
    return 1 if t > k else (-1 if t < k else 0)


def compute_psar_signal(df: pd.DataFrame) -> int:
    psar = ta.psar(df["high"], df["low"], df["close"])
    if psar is None or psar.empty:
        return 0
    long_col = [c for c in psar.columns if "PSARl" in c]
    short_col = [c for c in psar.columns if "PSARs" in c]
    close = df["close"].iloc[-1]
    if long_col and not pd.isna(psar[long_col[0]].iloc[-1]):
        return 1
    if short_col and not pd.isna(psar[short_col[0]].iloc[-1]):
        return -1
    return 0


def compute_aroon_signal(df: pd.DataFrame, period: int = 25) -> int:
    aroon = ta.aroon(df["high"], df["low"], length=period)
    if aroon is None or aroon.empty:
        return 0
    up_col = [c for c in aroon.columns if "AROONU" in c]
    dn_col = [c for c in aroon.columns if "AROOND" in c]
    if not up_col or not dn_col:
        return 0
    up = aroon[up_col[0]].iloc[-1]
    dn = aroon[dn_col[0]].iloc[-1]
    if pd.isna(up) or pd.isna(dn):
        return 0
    if up > 70 and dn < 30:
        return 1
    elif dn > 70 and up < 30:
        return -1
    return 0


def compute_vwap_signal(df: pd.DataFrame) -> int:
    if "volume" not in df.columns:
        return 0
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_tp_vol = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    if vwap.empty or pd.isna(vwap.iloc[-1]):
        return 0
    close = df["close"].iloc[-1]
    std = (df["close"] - vwap).std()
    if pd.isna(std) or std == 0:
        return 1 if close > vwap.iloc[-1] else -1
    upper = vwap.iloc[-1] + 2 * std
    lower = vwap.iloc[-1] - 2 * std
    if close > upper:
        return 1
    elif close < lower:
        return -1
    elif close > vwap.iloc[-1]:
        return 1
    elif close < vwap.iloc[-1]:
        return -1
    return 0


def compute_all_trend(df: pd.DataFrame) -> Dict[str, Any]:
    """Run all trend indicators and return signal dict."""
    if df.empty:
        return {}
    signals: Dict[str, Any] = {}
    signals.update(compute_ema_signals(df))
    signals["dema"] = compute_dema_signal(df)
    signals["tema"] = compute_tema_signal(df)
    signals["zlema"] = compute_zlema_signal(df)
    signals["hma"] = compute_hma_signal(df)
    signals["supertrend"] = compute_supertrend_signal(df)
    signals.update(compute_macd_signal(df))
    signals.update(compute_adx_signal(df))
    signals["ichimoku"] = compute_ichimoku_signal(df)
    signals["psar"] = compute_psar_signal(df)
    signals["aroon"] = compute_aroon_signal(df)
    signals["vwap"] = compute_vwap_signal(df)
    return signals
