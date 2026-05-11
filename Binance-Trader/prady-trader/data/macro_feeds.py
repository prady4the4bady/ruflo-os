"""
PRADY TRADER — Macro / alt-data features via yfinance (FREE).

Fetches DXY (US Dollar Index), Gold (GC=F), and S&P 500 (^GSPC)
to provide cross-market correlation features for crypto models.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger("prady.data.macro_feeds")


def _safe_download(ticker: str, period: str = "5d", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Download ticker data via yfinance. Returns None on failure."""
    try:
        import yfinance as yf

        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df is None or df.empty:
            return None
        return df
    except Exception as exc:
        logger.warning("yfinance download failed for %s: %s", ticker, exc)
        return None


def fetch_macro_snapshot() -> Dict[str, Optional[float]]:
    """
    Return latest close prices for DXY, Gold, and S&P 500.
    All FREE via yfinance — no API key needed.
    Returns dict with keys: dxy, gold, sp500 (None if unavailable).
    """
    result: Dict[str, Optional[float]] = {"dxy": None, "gold": None, "sp500": None}

    tickers = {"dxy": "DX-Y.NYB", "gold": "GC=F", "sp500": "^GSPC"}
    for key, ticker in tickers.items():
        df = _safe_download(ticker, period="5d", interval="1d")
        if df is not None and len(df) > 0:
            close_col = "Close"
            if isinstance(df.columns, pd.MultiIndex):
                # yfinance sometimes returns multi-index columns
                df.columns = df.columns.get_level_values(0)
            if close_col in df.columns:
                result[key] = float(df[close_col].iloc[-1])
    return result


def fetch_macro_series(period: str = "60d", interval: str = "1d") -> pd.DataFrame:
    """
    Return a DataFrame with Date index and columns: dxy, gold, sp500.
    Used for correlation analysis with crypto prices.
    """
    tickers = {"dxy": "DX-Y.NYB", "gold": "GC=F", "sp500": "^GSPC"}
    frames = {}
    for key, ticker in tickers.items():
        df = _safe_download(ticker, period=period, interval=interval)
        if df is not None and len(df) > 0:
            close_col = "Close"
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if close_col in df.columns:
                frames[key] = df[close_col]

    if not frames:
        return pd.DataFrame()

    combined = pd.DataFrame(frames)
    combined.index.name = "date"
    return combined


def add_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add macro correlation features to a crypto OHLCV DataFrame.
    Fetches DXY, Gold, SP500 and computes rolling correlation.
    Safe to call even if yfinance is unavailable — returns df unchanged.
    """
    snapshot = fetch_macro_snapshot()
    df = df.copy()

    # Add current macro levels as static features
    for key in ("dxy", "gold", "sp500"):
        val = snapshot.get(key)
        df[f"macro_{key}"] = val if val is not None else 0.0

    return df
