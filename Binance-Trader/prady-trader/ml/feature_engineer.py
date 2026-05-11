"""
PRADY TRADER — Feature engineering: 200+ features from raw OHLCV data.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*copy_on_write.*")
    import pandas_ta as ta

logger = logging.getLogger("prady.ml.feature_engineer")


def add_price_action_features(df: pd.DataFrame) -> pd.DataFrame:
    """Candle body ratio, wick ratios, gap, etc."""
    df = df.copy()
    df["body"] = (df["close"] - df["open"]).abs()
    df["body_ratio"] = df["body"] / (df["high"] - df["low"]).replace(0, np.nan)
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["upper_wick_ratio"] = df["upper_wick"] / (df["high"] - df["low"]).replace(0, np.nan)
    df["lower_wick_ratio"] = df["lower_wick"] / (df["high"] - df["low"]).replace(0, np.nan)
    df["is_bullish"] = (df["close"] > df["open"]).astype(int)
    df["candle_range"] = df["high"] - df["low"]
    df["gap"] = df["open"] - df["close"].shift(1)
    return df


def add_lag_features(df: pd.DataFrame, lags: List[int] | None = None) -> pd.DataFrame:
    if lags is None:
        lags = [1, 2, 3, 5, 10, 20]
    df = df.copy()
    for lag in lags:
        df[f"close_lag_{lag}"] = df["close"].shift(lag)
        df[f"volume_lag_{lag}"] = df["volume"].shift(lag)
        df[f"return_lag_{lag}"] = df["close"].pct_change(periods=lag)
        df[f"high_low_range_lag_{lag}"] = (df["high"] - df["low"]).shift(lag)
    return df


def add_rolling_features(df: pd.DataFrame, windows: List[int] | None = None) -> pd.DataFrame:
    if windows is None:
        windows = [5, 10, 20, 50]
    df = df.copy()
    for w in windows:
        df[f"close_mean_{w}"] = df["close"].rolling(w).mean()
        df[f"close_std_{w}"] = df["close"].rolling(w).std()
        df[f"close_skew_{w}"] = df["close"].rolling(w).skew()
        df[f"close_kurt_{w}"] = df["close"].rolling(w).kurt()
        df[f"volume_mean_{w}"] = df["volume"].rolling(w).mean()
        df[f"volume_std_{w}"] = df["volume"].rolling(w).std()
        df[f"return_mean_{w}"] = df["close"].pct_change().rolling(w).mean()
        df[f"return_std_{w}"] = df["close"].pct_change().rolling(w).std()
        df[f"high_rolling_max_{w}"] = df["high"].rolling(w).max()
        df[f"low_rolling_min_{w}"] = df["low"].rolling(w).min()
        df[f"close_to_high_{w}"] = df["close"] / df[f"high_rolling_max_{w}"].replace(0, np.nan)
        df[f"close_to_low_{w}"] = df["close"] / df[f"low_rolling_min_{w}"].replace(0, np.nan)
    return df


def add_indicator_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicator values as features."""
    df = df.copy()
    # RSI
    rsi = ta.rsi(df["close"], length=14)
    if rsi is not None:
        df["rsi_14"] = rsi
    rsi_7 = ta.rsi(df["close"], length=7)
    if rsi_7 is not None:
        df["rsi_7"] = rsi_7
    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        for col in macd.columns:
            df[col.replace(" ", "_").lower()] = macd[col]
    # Bollinger
    bb = ta.bbands(df["close"], length=20, lower_std=2.0, upper_std=2.0)
    if bb is not None:
        for col in bb.columns:
            df[f"bb_{col.replace(' ', '_').lower()}"] = bb[col]
    # ATR
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    if atr is not None:
        df["atr_14"] = atr
    # OBV
    obv = ta.obv(df["close"], df["volume"])
    if obv is not None:
        df["obv"] = obv
    # CCI
    cci = ta.cci(df["high"], df["low"], df["close"], length=20)
    if cci is not None:
        df["cci_20"] = cci
    # Stochastic RSI
    stoch = ta.stochrsi(df["close"], length=14)
    if stoch is not None:
        for col in stoch.columns:
            df[f"stochrsi_{col.replace(' ', '_').lower()}"] = stoch[col]
    # Williams %R
    wr = ta.willr(df["high"], df["low"], df["close"], length=14)
    if wr is not None:
        df["willr_14"] = wr
    # MFI
    mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=14)
    if mfi is not None:
        df["mfi_14"] = mfi
    # ADX
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx is not None:
        for col in adx.columns:
            df[f"adx_{col.replace(' ', '_').lower()}"] = adx[col]
    # EMA
    for period in [8, 21, 55, 200]:
        ema = ta.ema(df["close"], length=period)
        if ema is not None:
            df[f"ema_{period}"] = ema
            df[f"close_vs_ema_{period}"] = (df["close"] - ema) / ema.replace(0, np.nan)
    # Supertrend
    st = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3.0)
    if st is not None:
        for col in st.columns:
            df[f"st_{col.replace(' ', '_').lower()}"] = st[col]
    return df


def add_volume_profile_features(df: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    df = df.copy()
    if len(df) < bins:
        return df
    recent = df.tail(50)
    price_min = recent["low"].min()
    price_max = recent["high"].max()
    if price_max == price_min:
        df["vol_profile_position"] = 0.5
        return df
    bin_edges = np.linspace(price_min, price_max, bins + 1)
    vol_at_price = np.zeros(bins)
    for _, row in recent.iterrows():
        for b in range(bins):
            if bin_edges[b] <= row["close"] <= bin_edges[b + 1]:
                vol_at_price[b] += row["volume"]
                break
    poc_idx = np.argmax(vol_at_price)
    poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2
    df["vol_profile_poc"] = poc_price
    df["vol_profile_position"] = (df["close"] - poc_price) / (price_max - price_min)
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
        df["hour"] = ts.dt.hour
        df["day_of_week"] = ts.dt.dayofweek
        df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    return df


def engineer_features(df: pd.DataFrame, drop_na: bool = True) -> pd.DataFrame:
    """Full pipeline: generate 200+ features from raw OHLCV."""
    if df.empty:
        return df
    result = df.copy()
    result = add_price_action_features(result)
    result = add_lag_features(result)
    result = add_rolling_features(result)
    result = add_indicator_features(result)
    result = add_volume_profile_features(result)
    result = add_time_features(result)
    # Macro features (DXY, Gold, SP500) — safe to fail
    try:
        from data.macro_feeds import add_macro_features
        result = add_macro_features(result)
    except Exception as exc:
        logger.debug("Macro features skipped: %s", exc)
    # Target: 1 if close goes up in next candle
    result["target"] = (result["close"].shift(-1) > result["close"]).astype(int)
    if drop_na:
        # Forward-fill then back-fill indicator warmup NaNs
        # This preserves rows while filling in indicator warmup periods
        feature_cols = [c for c in result.columns if c not in {"open", "high", "low", "close", "volume", "timestamp", "target", "closed"}]
        result[feature_cols] = result[feature_cols].ffill().bfill()
        # Drop rows that still have NaN (shouldn't happen after ffill+bfill)
        result = result.dropna(subset=feature_cols)
        # Also drop the last row where target is NaN from the shift
        result = result.iloc[:-1] if len(result) > 0 else result
    logger.info("Engineered %d features, %d rows", len(result.columns), len(result))
    return result


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    exclude = {"open", "high", "low", "close", "volume", "timestamp", "target", "closed"}
    return [c for c in df.columns if c not in exclude]
