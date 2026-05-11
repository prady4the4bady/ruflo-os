"""
PRADY TRADER — Momentum indicators.
RSI, Stoch RSI, CCI, Williams %R, MFI, ROC, TSI, PPO, DPO, Ultimate Oscillator.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import warnings

import pandas as pd

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*copy_on_write.*")
    import pandas_ta as ta

from config.constants import (
    CCI_PERIOD,
    MFI_PERIOD,
    ROC_PERIOD,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    RSI_PERIOD,
    STOCH_RSI_PERIOD,
    STOCH_RSI_SMOOTH_D,
    STOCH_RSI_SMOOTH_K,
    TSI_LONG,
    TSI_SHORT,
    WILLIAMS_PERIOD,
)

logger = logging.getLogger("prady.indicators.momentum")


def compute_rsi_signal(df: pd.DataFrame) -> Dict[str, Any]:
    rsi = ta.rsi(df["close"], length=RSI_PERIOD)
    if rsi is None or rsi.empty or pd.isna(rsi.iloc[-1]):
        return {"rsi_value": 50.0, "rsi_signal": 0}
    val = float(rsi.iloc[-1])
    if val < RSI_OVERSOLD:
        sig = 1  # oversold → bullish
    elif val > RSI_OVERBOUGHT:
        sig = -1  # overbought → bearish
    else:
        sig = 0
    return {"rsi_value": val, "rsi_signal": sig}


def compute_stoch_rsi_signal(df: pd.DataFrame) -> Dict[str, Any]:
    stoch = ta.stochrsi(
        df["close"],
        length=STOCH_RSI_PERIOD,
        rsi_length=STOCH_RSI_PERIOD,
        k=STOCH_RSI_SMOOTH_K,
        d=STOCH_RSI_SMOOTH_D,
    )
    if stoch is None or stoch.empty:
        return {"stoch_rsi_k": 50.0, "stoch_rsi_d": 50.0, "stoch_rsi_signal": 0}
    k_col = [c for c in stoch.columns if "STOCHRSIk" in c]
    d_col = [c for c in stoch.columns if "STOCHRSId" in c]
    if not k_col or not d_col:
        return {"stoch_rsi_k": 50.0, "stoch_rsi_d": 50.0, "stoch_rsi_signal": 0}
    k = stoch[k_col[0]].iloc[-1]
    d = stoch[d_col[0]].iloc[-1]
    if pd.isna(k) or pd.isna(d):
        return {"stoch_rsi_k": 50.0, "stoch_rsi_d": 50.0, "stoch_rsi_signal": 0}
    sig = 0
    if k < 20 and k > d:
        sig = 1
    elif k > 80 and k < d:
        sig = -1
    return {"stoch_rsi_k": float(k), "stoch_rsi_d": float(d), "stoch_rsi_signal": sig}


def compute_cci_signal(df: pd.DataFrame) -> Dict[str, Any]:
    cci = ta.cci(df["high"], df["low"], df["close"], length=CCI_PERIOD)
    if cci is None or cci.empty or pd.isna(cci.iloc[-1]):
        return {"cci_value": 0.0, "cci_signal": 0}
    val = float(cci.iloc[-1])
    if val < -100:
        sig = 1
    elif val > 100:
        sig = -1
    else:
        sig = 0
    return {"cci_value": val, "cci_signal": sig}


def compute_williams_signal(df: pd.DataFrame) -> Dict[str, Any]:
    wr = ta.willr(df["high"], df["low"], df["close"], length=WILLIAMS_PERIOD)
    if wr is None or wr.empty or pd.isna(wr.iloc[-1]):
        return {"williams_value": -50.0, "williams_signal": 0}
    val = float(wr.iloc[-1])
    if val < -80:
        sig = 1  # oversold
    elif val > -20:
        sig = -1  # overbought
    else:
        sig = 0
    return {"williams_value": val, "williams_signal": sig}


def compute_mfi_signal(df: pd.DataFrame) -> Dict[str, Any]:
    mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=MFI_PERIOD)
    if mfi is None or mfi.empty or pd.isna(mfi.iloc[-1]):
        return {"mfi_value": 50.0, "mfi_signal": 0}
    val = float(mfi.iloc[-1])
    if val < 20:
        sig = 1
    elif val > 80:
        sig = -1
    else:
        sig = 0
    return {"mfi_value": val, "mfi_signal": sig}


def compute_roc_signal(df: pd.DataFrame) -> Dict[str, Any]:
    roc = ta.roc(df["close"], length=ROC_PERIOD)
    if roc is None or roc.empty or pd.isna(roc.iloc[-1]):
        return {"roc_value": 0.0, "roc_signal": 0}
    val = float(roc.iloc[-1])
    if val > 2:
        sig = 1
    elif val < -2:
        sig = -1
    else:
        sig = 0
    return {"roc_value": val, "roc_signal": sig}


def compute_tsi_signal(df: pd.DataFrame) -> Dict[str, Any]:
    tsi = ta.tsi(df["close"], fast=TSI_SHORT, slow=TSI_LONG)
    if tsi is None or tsi.empty:
        return {"tsi_value": 0.0, "tsi_signal": 0}
    tsi_cols = [c for c in tsi.columns if "TSI_" in c and "TSIs" not in c]
    if not tsi_cols:
        return {"tsi_value": 0.0, "tsi_signal": 0}
    val = tsi[tsi_cols[0]].iloc[-1]
    if pd.isna(val):
        return {"tsi_value": 0.0, "tsi_signal": 0}
    sig = 1 if val > 0 else (-1 if val < 0 else 0)
    return {"tsi_value": float(val), "tsi_signal": sig}


def compute_ppo_signal(df: pd.DataFrame) -> Dict[str, Any]:
    ppo = ta.ppo(df["close"])
    if ppo is None or ppo.empty:
        return {"ppo_value": 0.0, "ppo_signal": 0}
    ppo_cols = [c for c in ppo.columns if "PPO_" in c and "PPOs" not in c and "PPOh" not in c]
    sig_cols = [c for c in ppo.columns if "PPOs" in c]
    if not ppo_cols or not sig_cols:
        return {"ppo_value": 0.0, "ppo_signal": 0}
    p = ppo[ppo_cols[0]].iloc[-1]
    s = ppo[sig_cols[0]].iloc[-1]
    if pd.isna(p) or pd.isna(s):
        return {"ppo_value": 0.0, "ppo_signal": 0}
    sig = 1 if p > s else (-1 if p < s else 0)
    return {"ppo_value": float(p), "ppo_signal": sig}


def compute_dpo_signal(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    shift = period // 2 + 1
    sma = df["close"].rolling(window=period).mean()
    dpo = df["close"].shift(shift) - sma
    if dpo.empty or pd.isna(dpo.iloc[-1]):
        return {"dpo_value": 0.0, "dpo_signal": 0}
    val = float(dpo.iloc[-1])
    sig = 1 if val > 0 else (-1 if val < 0 else 0)
    return {"dpo_value": val, "dpo_signal": sig}


def compute_ultimate_signal(df: pd.DataFrame) -> Dict[str, Any]:
    uo = ta.uo(df["high"], df["low"], df["close"])
    if uo is None or uo.empty or pd.isna(uo.iloc[-1]):
        return {"ultimate_value": 50.0, "ultimate_signal": 0}
    val = float(uo.iloc[-1])
    if val < 30:
        sig = 1
    elif val > 70:
        sig = -1
    else:
        sig = 0
    return {"ultimate_value": val, "ultimate_signal": sig}


def compute_all_momentum(df: pd.DataFrame) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}
    signals.update(compute_rsi_signal(df))
    signals.update(compute_stoch_rsi_signal(df))
    signals.update(compute_cci_signal(df))
    signals.update(compute_williams_signal(df))
    signals.update(compute_mfi_signal(df))
    signals.update(compute_roc_signal(df))
    signals.update(compute_tsi_signal(df))
    signals.update(compute_ppo_signal(df))
    signals.update(compute_dpo_signal(df))
    signals.update(compute_ultimate_signal(df))
    return signals
