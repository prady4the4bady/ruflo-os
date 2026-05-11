"""
PRADY TRADER — Arbiter Agent (weight: 0.15).
Cross-pair correlation and regime analyser.
Detects market regime (trending / ranging / volatile) and inter-asset correlations.
"""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent, AgentSignal
from config.constants import AGENT_WEIGHTS
from config.settings import get_settings
from data.data_store import get_data_store

logger = logging.getLogger("prady.agents.arbiter")


def _classify_regime(df: pd.DataFrame) -> str:
    """Classify the current market regime from price action."""
    if df is None or len(df) < 50:
        return "unknown"
    close = np.asarray(df["close"].values[-50:], dtype=float)
    returns = np.diff(close) / close[:-1]  # type: ignore[arg-type]

    vol = np.std(returns)
    trend = (close[-1] - close[0]) / close[0]
    adx_proxy = abs(trend) / (vol + 1e-10)

    if vol > 0.03:
        return "volatile"
    elif adx_proxy > 2.0:
        return "trending"
    else:
        return "ranging"


def _compute_correlation(df1: pd.DataFrame, df2: pd.DataFrame, window: int = 50) -> float:
    """Rolling correlation between two close price series."""
    if df1 is None or df2 is None:
        return 0.0
    min_len = min(len(df1), len(df2), window)
    if min_len < 10:
        return 0.0
    c1 = np.asarray(df1["close"].values[-min_len:], dtype=float)
    c2 = np.asarray(df2["close"].values[-min_len:], dtype=float)
    r1 = np.diff(c1) / c1[:-1]  # type: ignore[arg-type]
    r2 = np.diff(c2) / c2[:-1]  # type: ignore[arg-type]
    if len(r1) < 5:
        return 0.0
    corr = np.corrcoef(r1, r2)[0, 1]
    return 0.0 if np.isnan(corr) else float(corr)


def _compute_market_breadth(pair_frames: Dict[str, pd.DataFrame], lookback: int = 24) -> tuple[float, Dict[str, float]]:
    """Heatmap-style breadth score using 24h peer returns."""
    moves: Dict[str, float] = {}
    bullish = 0
    bearish = 0

    for pair, df in pair_frames.items():
        if df is None or len(df) <= lookback:
            continue
        close = np.asarray(df["close"].values[-(lookback + 1):], dtype=float)
        start = float(close[0])
        end = float(close[-1])
        if start <= 0:
            continue
        change = (end - start) / start
        moves[pair] = change
        if change >= 0.01:
            bullish += 1
        elif change <= -0.01:
            bearish += 1

    total = bullish + bearish
    if total <= 0:
        return 0.0, moves
    return (bullish - bearish) / total, moves


class ArbiterAgent(BaseAgent):
    """
    Cross-pair regime and correlation analyser.
    Provides context about whether broad market conditions favour the trade.
    """

    def __init__(self):
        super().__init__(name="arbiter", weight=AGENT_WEIGHTS["arbiter"])

    async def analyze(self, symbol: str) -> AgentSignal:
        store = get_data_store()
        settings = get_settings()

        # Regime detection for the target symbol across timeframes
        hourly = store.get_dataframe(symbol, "1h")
        regime = _classify_regime(hourly)

        # Cross-pair correlation with BTC (market leader)
        correlations: Dict[str, float] = {}
        peer_frames: Dict[str, pd.DataFrame] = {}
        btc_df = store.get_dataframe("BTCUSDT", "1h") if symbol != "BTCUSDT" else hourly
        for pair in settings.trading_pairs:
            if pair == symbol:
                continue
            pair_df = store.get_dataframe(pair, "1h")
            peer_frames[pair] = pair_df
            correlations[pair] = _compute_correlation(hourly, pair_df)

        btc_corr = correlations.get("BTCUSDT", _compute_correlation(hourly, btc_df))
        breadth_score, peer_moves = _compute_market_breadth(peer_frames)

        # BTC regime influences altcoin trades
        btc_regime = _classify_regime(btc_df) if symbol != "BTCUSDT" else regime

        # Scoring logic
        score = 0.0
        reasons: List[str] = []

        # Regime contribution
        if regime == "trending":
            score += 25.0
            reasons.append(f"{symbol} trending")
        elif regime == "volatile":
            score -= 15.0
            reasons.append(f"{symbol} volatile (risk)")
        else:
            score += 5.0
            reasons.append(f"{symbol} ranging")

        # BTC alignment for altcoins
        if symbol != "BTCUSDT":
            if btc_regime == "trending" and btc_corr > 0.6:
                score += 20.0
                reasons.append(f"BTC trending, corr={btc_corr:.2f} (aligned)")
            elif btc_regime == "volatile":
                score -= 20.0
                reasons.append("BTC volatile (risk-off)")

        # High correlation cluster warning
        high_corr = [p for p, c in correlations.items() if abs(c) > 0.8]
        if len(high_corr) > 3:
            score -= 10.0
            reasons.append(f"Highly correlated with {len(high_corr)} pairs (crowded)")

        if breadth_score >= 0.5:
            score += 15.0
            reasons.append(f"Heatmap breadth supportive ({breadth_score:+.2f})")
        elif breadth_score <= -0.5:
            score -= 15.0
            reasons.append(f"Heatmap breadth weak ({breadth_score:+.2f})")

        score = max(-100.0, min(100.0, score))

        if score > 15:
            direction = "LONG"
        elif score < -15:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        confidence = min(abs(score) / 80.0, 1.0)

        reasoning = f"Regime={regime}. BTC regime={btc_regime}. " + "; ".join(reasons)

        return AgentSignal(
            agent_name=self.name,
            direction=direction,
            confidence=round(confidence, 4),
            score=round(score, 2),
            reasoning=reasoning,
            metadata={
                "regime": regime,
                "btc_regime": btc_regime,
                "btc_correlation": btc_corr,
                "market_breadth": breadth_score,
                "peer_moves": peer_moves,
                "correlations": correlations,
            },
        )
