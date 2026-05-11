"""
PRADY TRADER — 16 Trading Strategies.
Each strategy is a standalone async function that returns a StrategySignal.
Strategies consume local market structure, free APIs, technical indicators,
and orderflow to generate directional signals.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from data.data_store import get_data_store
from data.free_apis import (
    async_fetch_coingecko_global,
    async_fetch_coingecko_market_chart,
    async_fetch_coingecko_price,
    async_fetch_blockchain_mempool,
    async_fetch_blockchain_stats,
    async_fetch_cryptocompare_social,
    async_fetch_fear_greed,
    async_fetch_fear_greed_history,
    async_fetch_all_news,
    async_fetch_bitquery_whale_transfers,
)
from data.crypto_indicators_api import (
    async_fetch_multi_exchange_price,
    async_fetch_taapi_rsi,
    async_fetch_taapi_macd,
    async_fetch_taapi_bbands,
    async_fetch_coincodex_prediction,
)
from data.freecrypto_api import get_technical_analysis, get_breakouts
from data.orderbook_feed import get_orderbook_feed
from data.orderflow import OrderFlowMetrics, analyze_order_flow
from indicators.structure import find_swing_highs_lows

logger = logging.getLogger("prady.execution.strategies")

# ── Signal dataclass ─────────────────────────────────────────────────
@dataclass
class StrategySignal:
    name: str
    direction: str          # LONG | SHORT | NEUTRAL
    confidence: float       # 0.0 – 1.0
    score: float            # -100 to 100
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────
_SYMBOL_TO_CG: Dict[str, str] = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana",
    "ADAUSDT": "cardano",
    "XRPUSDT": "ripple",
    "DOGEUSDT": "dogecoin",
    "DOTUSDT": "polkadot",
    "AVAXUSDT": "avalanche-2",
    "MATICUSDT": "matic-network",
}

LOCAL_SETUP_PRIORITY: Dict[str, float] = {
    "liquidity_sweep_avwap": 2.4,
    "failed_auction_delta": 2.1,
    "cumulative_volume_delta_reversal": 2.0,
}

CORE_INTELLIGENCE_NAMES = {
    "core_financial_strength",
    "advanced_quant_analysis",
    "dual_mode_financial_intelligence",
}


def _cg_id(symbol: str) -> str:
    return _SYMBOL_TO_CG.get(symbol.upper(), "bitcoin")


def _clamp(v: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _direction(score: float, threshold: float = 15.0) -> str:
    if score > threshold:
        return "LONG"
    elif score < -threshold:
        return "SHORT"
    return "NEUTRAL"


def _compute_signed_volume_delta(df: pd.DataFrame) -> pd.Series:
    signed_volume: List[float] = []
    prev_close: Optional[float] = None
    prev_sign = 0.0

    for row in df.itertuples(index=False):
        open_price = float(row.open)
        close_price = float(row.close)
        volume = float(row.volume)

        if close_price > open_price:
            sign = 1.0
        elif close_price < open_price:
            sign = -1.0
        elif prev_close is not None and close_price > prev_close:
            sign = 1.0
        elif prev_close is not None and close_price < prev_close:
            sign = -1.0
        else:
            sign = prev_sign

        signed_volume.append(sign * volume)
        prev_close = close_price
        prev_sign = sign

    return pd.Series(signed_volume, index=df.index, dtype=float)


def _compute_cumulative_volume_delta(df: pd.DataFrame) -> pd.Series:
    return _compute_signed_volume_delta(df).cumsum()


def _compute_anchored_vwap(df: pd.DataFrame, anchor_index: int) -> float:
    window = df.iloc[max(anchor_index, 0):].copy()
    if window.empty:
        return 0.0

    volume_total = float(window["volume"].sum())
    if volume_total <= 0:
        return float(window["close"].iloc[-1])

    typical_price = (window["high"] + window["low"] + window["close"]) / 3.0
    return float((typical_price * window["volume"]).sum() / volume_total)


def _rolling_efficiency_ratio(close: pd.Series) -> float:
    clean = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    if len(clean) < 2:
        return 0.0

    net_change = abs(float(clean.iloc[-1]) - float(clean.iloc[0]))
    gross_change = float(clean.diff().abs().dropna().sum())
    if gross_change <= 0:
        return 0.0
    return max(0.0, min(1.0, net_change / gross_change))


def _max_drawdown_pct(close: pd.Series) -> float:
    clean = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    if clean.empty:
        return 0.0

    peaks = clean.cummax()
    drawdowns = ((peaks - clean) / peaks.replace(0, pd.NA)).fillna(0.0)
    return max(0.0, float(drawdowns.max()))


def _series_zscore(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if len(clean) < 5:
        return 0.0

    std = float(clean.std(ddof=0))
    if std <= 1e-9:
        return 0.0
    return (float(clean.iloc[-1]) - float(clean.mean())) / std


def _pick_best_local_signal(signals: List[StrategySignal], fallback_name: str, fallback_reasoning: str) -> StrategySignal:
    if not signals:
        return StrategySignal(
            name=fallback_name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=fallback_reasoning,
        )

    directional = [signal for signal in signals if signal.direction != "NEUTRAL"]
    pool = directional or signals
    return max(pool, key=lambda signal: (abs(signal.score), signal.confidence))


def build_core_financial_strength_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
) -> StrategySignal:
    """Measure structural market strength using trend persistence, drawdown control, and volume sponsorship."""
    name = "core_financial_strength"
    required_cols = {"open", "high", "low", "close", "volume"}
    if df is None or len(df) < 40 or any(col not in df.columns for col in required_cols):
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient {timeframe} data for financial-strength analysis",
        )

    frame = df.dropna(subset=list(required_cols)).tail(96).reset_index(drop=True)
    if len(frame) < 40:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient clean {timeframe} candles for financial-strength analysis",
        )

    close = frame["close"].astype(float)
    volume = frame["volume"].astype(float)
    current_close = float(close.iloc[-1])

    return_6 = ((current_close / float(close.iloc[-7])) - 1.0) if len(close) > 6 and float(close.iloc[-7]) > 0 else 0.0
    return_24 = ((current_close / float(close.iloc[-25])) - 1.0) if len(close) > 24 and float(close.iloc[-25]) > 0 else 0.0
    efficiency = _rolling_efficiency_ratio(close.tail(24))
    drawdown_pct = _max_drawdown_pct(close.tail(24))

    volume_baseline = float(volume.iloc[-21:-1].median()) if len(volume) > 21 else float(volume.iloc[:-1].median()) if len(volume) > 1 else float(volume.iloc[-1])
    volume_ratio = float(volume.iloc[-1]) / volume_baseline if volume_baseline > 0 else 1.0

    recent_high = float(frame["high"].tail(20).max())
    recent_low = float(frame["low"].tail(20).min())
    range_size = max(recent_high - recent_low, 1e-9)
    range_location = (current_close - recent_low) / range_size

    score = 0.0
    score += max(min(return_24 * 900.0, 24.0), -24.0)
    score += max(min(return_6 * 550.0, 12.0), -12.0)
    score += (efficiency - 0.45) * 34.0
    score += (range_location - 0.5) * 24.0
    score += max(min((volume_ratio - 1.0) * 16.0, 10.0), -10.0)
    score -= drawdown_pct * 120.0
    score = _clamp(score)

    metadata = {
        "symbol": symbol,
        "timeframe": timeframe,
        "return_6_pct": round(return_6 * 100.0, 3),
        "return_24_pct": round(return_24 * 100.0, 3),
        "trend_efficiency": round(efficiency, 4),
        "drawdown_pct": round(drawdown_pct * 100.0, 3),
        "volume_ratio": round(volume_ratio, 3),
        "range_location": round(range_location, 3),
    }

    return StrategySignal(
        name=name,
        direction=_direction(score, threshold=12.0),
        confidence=min(abs(score) / 70.0, 1.0),
        score=score,
        reasoning=(
            f"{timeframe} strength ret24={return_24:+.2%}, ret6={return_6:+.2%}, "
            f"eff={efficiency:.2f}, dd={drawdown_pct:.2%}, vol x{volume_ratio:.2f}, range={range_location:.2f}"
        ),
        metadata=metadata,
    )


def build_advanced_quant_analysis_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
) -> StrategySignal:
    """Compute a compact quantitative factor stack using momentum, volatility, consistency, and efficiency."""
    name = "advanced_quant_analysis"
    required_cols = {"open", "high", "low", "close", "volume"}
    if df is None or len(df) < 40 or any(col not in df.columns for col in required_cols):
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient {timeframe} data for quant analysis",
        )

    frame = df.dropna(subset=list(required_cols)).tail(96).reset_index(drop=True)
    if len(frame) < 40:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient clean {timeframe} candles for quant analysis",
        )

    close = frame["close"].astype(float)
    returns = close.pct_change().dropna()
    if len(returns) < 24:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Not enough return history on {timeframe} for quant analysis",
        )

    current_close = float(close.iloc[-1])
    momentum_3 = ((current_close / float(close.iloc[-4])) - 1.0) if len(close) > 3 and float(close.iloc[-4]) > 0 else 0.0
    momentum_12 = ((current_close / float(close.iloc[-13])) - 1.0) if len(close) > 12 and float(close.iloc[-13]) > 0 else 0.0
    momentum_24 = ((current_close / float(close.iloc[-25])) - 1.0) if len(close) > 24 and float(close.iloc[-25]) > 0 else 0.0

    realized_vol_pct = float(returns.tail(24).std(ddof=0)) * 100.0
    risk_adjusted_momentum = (momentum_24 * 100.0) / max(realized_vol_pct, 0.35)
    consistency = float((returns.tail(18) > 0).mean())
    efficiency = _rolling_efficiency_ratio(close.tail(24))
    zscore = _series_zscore(close.tail(20))

    score = 0.0
    score += max(min(risk_adjusted_momentum * 9.0, 28.0), -28.0)
    if momentum_3 > 0 and momentum_12 > 0 and momentum_24 > 0:
        score += 14.0
    elif momentum_3 < 0 and momentum_12 < 0 and momentum_24 < 0:
        score -= 14.0
    score += (consistency - 0.5) * 28.0
    score += (efficiency - 0.45) * 26.0
    if score > 0 and zscore > 1.8:
        score -= 8.0
    elif score < 0 and zscore < -1.8:
        score += 8.0
    elif score > 0 and zscore < -0.9:
        score += 4.0
    elif score < 0 and zscore > 0.9:
        score -= 4.0
    score = _clamp(score)

    metadata = {
        "symbol": symbol,
        "timeframe": timeframe,
        "momentum_3_pct": round(momentum_3 * 100.0, 3),
        "momentum_12_pct": round(momentum_12 * 100.0, 3),
        "momentum_24_pct": round(momentum_24 * 100.0, 3),
        "realized_vol_pct": round(realized_vol_pct, 3),
        "risk_adjusted_momentum": round(risk_adjusted_momentum, 3),
        "consistency": round(consistency, 4),
        "trend_efficiency": round(efficiency, 4),
        "zscore": round(zscore, 4),
    }

    return StrategySignal(
        name=name,
        direction=_direction(score, threshold=10.0),
        confidence=min(abs(score) / 72.0, 1.0),
        score=score,
        reasoning=(
            f"{timeframe} quant ra={risk_adjusted_momentum:+.2f}, m3={momentum_3:+.2%}, "
            f"m12={momentum_12:+.2%}, vol={realized_vol_pct:.2f}%, cons={consistency:.2f}, z={zscore:+.2f}"
        ),
        metadata=metadata,
    )


def build_dual_mode_financial_intelligence_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    orderflow_metrics: Optional[OrderFlowMetrics],
) -> StrategySignal:
    """Switch between tactical microstructure and strategic quant/strength reasoning based on available market detail."""
    name = "dual_mode_financial_intelligence"
    required_cols = {"open", "high", "low", "close", "volume"}
    if df is None or len(df) < 40 or any(col not in df.columns for col in required_cols):
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient {timeframe} data for dual-mode intelligence",
        )

    frame = df.dropna(subset=list(required_cols)).tail(96).reset_index(drop=True)
    if len(frame) < 40:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient clean {timeframe} candles for dual-mode intelligence",
        )

    financial_strength = build_core_financial_strength_signal(symbol, timeframe, frame)
    quant_signal = build_advanced_quant_analysis_signal(symbol, timeframe, frame)
    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    volume_baseline = float(frame["volume"].iloc[-21:-1].median()) if len(frame) > 21 else float(frame["volume"].iloc[:-1].median()) if len(frame) > 1 else float(frame["volume"].iloc[-1])
    volume_ratio = float(current["volume"]) / volume_baseline if volume_baseline > 0 else 1.0

    orderflow_score = float(orderflow_metrics.score) if orderflow_metrics is not None else 0.0
    tactical_mode = (
        orderflow_metrics is not None
        and timeframe in {"5m", "15m"}
        and (abs(orderflow_score) >= 8.0 or volume_ratio >= 1.1)
    )

    breakout_up = float(current["close"]) > float(previous["high"])
    breakout_down = float(current["close"]) < float(previous["low"])

    if tactical_mode:
        score = orderflow_score * 0.9
        score += 10.0 if breakout_up else -10.0 if breakout_down else 0.0
        score += max(min((volume_ratio - 1.0) * 10.0, 6.0), -6.0)
        score += (financial_strength.score * 0.12) + (quant_signal.score * 0.12)
        selected_mode = "tactical"
    else:
        score = (quant_signal.score * 0.58) + (financial_strength.score * 0.42)
        if orderflow_metrics is not None:
            score += max(min(orderflow_score * 0.15, 6.0), -6.0)
        selected_mode = "strategic"

    score = _clamp(score)
    metadata = {
        "symbol": symbol,
        "timeframe": timeframe,
        "selected_mode": selected_mode,
        "orderflow_score": round(orderflow_score, 3),
        "volume_ratio": round(volume_ratio, 3),
        "breakout_up": breakout_up,
        "breakout_down": breakout_down,
        "financial_strength_score": round(financial_strength.score, 3),
        "advanced_quant_score": round(quant_signal.score, 3),
    }

    return StrategySignal(
        name=name,
        direction=_direction(score, threshold=12.0),
        confidence=min(abs(score) / 75.0, 1.0),
        score=score,
        reasoning=(
            f"{timeframe} {selected_mode} mode: orderflow={orderflow_score:+.1f}, vol x{volume_ratio:.2f}, "
            f"financial={financial_strength.score:+.1f}, quant={quant_signal.score:+.1f}"
        ),
        metadata=metadata,
    )


def _candle_rejection_metrics(candle: pd.Series) -> tuple[float, float, float, float]:
    open_price = float(candle["open"])
    close_price = float(candle["close"])
    high_price = float(candle["high"])
    low_price = float(candle["low"])
    body = abs(close_price - open_price) + 1e-9
    lower_wick = min(open_price, close_price) - low_price
    upper_wick = high_price - max(open_price, close_price)
    range_size = max(high_price - low_price, 1e-9)
    close_location = (close_price - low_price) / range_size
    return body, lower_wick, upper_wick, close_location


def build_liquidity_sweep_reclaim_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    orderflow_metrics: Optional[OrderFlowMetrics],
) -> StrategySignal:
    """Approximate a TradingView-style sweep, delta divergence, and AVWAP reclaim setup."""
    name = "liquidity_sweep_avwap"
    required_cols = {"open", "high", "low", "close", "volume"}
    if df is None or len(df) < 30 or any(col not in df.columns for col in required_cols):
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient {timeframe} data for sweep/AVWAP setup",
        )

    frame = df.dropna(subset=list(required_cols)).tail(90).reset_index(drop=True)
    if len(frame) < 30:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient clean {timeframe} candles for sweep/AVWAP setup",
        )

    reference = frame.iloc[:-1].copy().reset_index(drop=True)
    swing_highs, swing_lows = find_swing_highs_lows(reference, lookback=3)
    if reference.empty:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"No stable swing structure on {timeframe}",
        )

    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    if swing_highs:
        swing_high_index, swing_high = swing_highs[-1]
    else:
        recent_reference = reference.tail(24)
        swing_high_index = int(recent_reference["high"].idxmax())
        swing_high = float(reference.loc[swing_high_index, "high"])

    if swing_lows:
        swing_low_index, swing_low = swing_lows[-1]
    else:
        recent_reference = reference.tail(24)
        swing_low_index = int(recent_reference["low"].idxmin())
        swing_low = float(reference.loc[swing_low_index, "low"])

    bullish_avwap = _compute_anchored_vwap(frame, swing_low_index)
    bearish_avwap = _compute_anchored_vwap(frame, swing_high_index)

    body, lower_wick, upper_wick, _ = _candle_rejection_metrics(current)
    bullish_rejection = lower_wick > body * 1.1
    bearish_rejection = upper_wick > body * 1.1

    baseline_source = frame["volume"].iloc[-21:-1] if len(frame) > 21 else frame["volume"].iloc[:-1]
    volume_baseline = float(baseline_source.median()) if not baseline_source.empty else float(current["volume"])
    volume_spike = float(current["volume"]) / volume_baseline if volume_baseline > 0 else 1.0

    delta_window = _compute_signed_volume_delta(frame.tail(8))
    earlier_delta = float(delta_window.head(4).sum())
    recent_delta = float(delta_window.tail(4).sum())
    delta_change = recent_delta - earlier_delta

    bullish_sweep = (
        bullish_rejection
        and float(current["low"]) < float(swing_low)
        and float(current["close"]) > float(swing_low)
        and float(current["close"]) > float(current["open"])
    )
    bearish_sweep = (
        bearish_rejection
        and float(current["high"]) > float(swing_high)
        and float(current["close"]) < float(swing_high)
        and float(current["close"]) < float(current["open"])
    )

    bullish_reclaim = (
        float(current["close"]) >= bullish_avwap * 0.999
        and float(previous["close"]) <= bullish_avwap * 1.01
    )
    bearish_reclaim = (
        float(current["close"]) <= bearish_avwap * 1.001
        and float(previous["close"]) >= bearish_avwap * 0.99
    )
    bullish_delta = delta_change > 0
    bearish_delta = delta_change < 0

    orderflow_score = float(orderflow_metrics.score) if orderflow_metrics is not None else 0.0
    bullish_orderflow = orderflow_metrics is not None and (
        orderflow_metrics.direction == "LONG" or orderflow_score >= 10.0
    )
    bearish_orderflow = orderflow_metrics is not None and (
        orderflow_metrics.direction == "SHORT" or orderflow_score <= -10.0
    )

    bullish_score = 0.0
    bearish_score = 0.0
    if bullish_sweep:
        bullish_score += 22.0
    if bullish_reclaim:
        bullish_score += 18.0
    if bullish_delta:
        bullish_score += 10.0
    if volume_spike >= 1.15:
        bullish_score += 8.0
    if bullish_orderflow:
        bullish_score += min(22.0, max(10.0, abs(orderflow_score) * 0.55))

    if bearish_sweep:
        bearish_score -= 22.0
    if bearish_reclaim:
        bearish_score -= 18.0
    if bearish_delta:
        bearish_score -= 10.0
    if volume_spike >= 1.15:
        bearish_score -= 8.0
    if bearish_orderflow:
        bearish_score -= min(22.0, max(10.0, abs(orderflow_score) * 0.55))

    metadata = {
        "timeframe": timeframe,
        "swing_high": round(float(swing_high), 4),
        "swing_low": round(float(swing_low), 4),
        "bullish_avwap": round(float(bullish_avwap), 4),
        "bearish_avwap": round(float(bearish_avwap), 4),
        "delta_change": round(delta_change, 2),
        "volume_spike": round(volume_spike, 3),
        "orderflow": orderflow_metrics.to_dict() if orderflow_metrics is not None else {},
        "bullish_setup": {
            "sweep": bullish_sweep,
            "reclaim": bullish_reclaim,
            "delta": bullish_delta,
            "orderflow": bullish_orderflow,
        },
        "bearish_setup": {
            "sweep": bearish_sweep,
            "reclaim": bearish_reclaim,
            "delta": bearish_delta,
            "orderflow": bearish_orderflow,
        },
    }

    if bullish_sweep and bullish_reclaim and bullish_orderflow and bullish_score >= 44 and bullish_score >= abs(bearish_score) + 8:
        score = _clamp(bullish_score)
        return StrategySignal(
            name=name,
            direction="LONG",
            confidence=min(abs(score) / 80.0, 1.0),
            score=score,
            reasoning=(
                f"{timeframe} sweep below {float(swing_low):.2f} reclaimed AVWAP {bullish_avwap:.2f}; "
                f"delta Δ={delta_change:+.0f}, volume x{volume_spike:.2f}, orderflow {orderflow_score:+.1f}"
            ),
            metadata=metadata,
        )

    if bearish_sweep and bearish_reclaim and bearish_orderflow and abs(bearish_score) >= 44 and abs(bearish_score) >= bullish_score + 8:
        score = _clamp(bearish_score)
        return StrategySignal(
            name=name,
            direction="SHORT",
            confidence=min(abs(score) / 80.0, 1.0),
            score=score,
            reasoning=(
                f"{timeframe} sweep above {float(swing_high):.2f} lost AVWAP {bearish_avwap:.2f}; "
                f"delta Δ={delta_change:+.0f}, volume x{volume_spike:.2f}, orderflow {orderflow_score:+.1f}"
            ),
            metadata=metadata,
        )

    return StrategySignal(
        name=name,
        direction="NEUTRAL",
        confidence=0.0,
        score=0.0,
        reasoning=(
            f"No confirmed {timeframe} liquidity sweep/AVWAP reclaim. "
            f"Bull={bullish_sweep}/{bullish_reclaim}/{bullish_orderflow}, "
            f"Bear={bearish_sweep}/{bearish_reclaim}/{bearish_orderflow}"
        ),
        metadata=metadata,
    )


async def strategy_liquidity_sweep_avwap(symbol: str) -> StrategySignal:
    """Local-data setup inspired by public TradingView sweep, footprint, and AVWAP concepts."""
    name = "liquidity_sweep_avwap"
    try:
        store = get_data_store()
        snapshot = get_orderbook_feed().get_snapshot(symbol)
        orderflow_metrics = analyze_order_flow(snapshot) if snapshot is not None else None

        candidates: List[StrategySignal] = []
        for timeframe in ["5m", "15m", "1h"]:
            candidate = store.get_dataframe(symbol, timeframe, limit=180)
            if len(candidate) >= 40:
                candidates.append(
                    build_liquidity_sweep_reclaim_signal(
                        symbol,
                        timeframe,
                        candidate,
                        orderflow_metrics,
                    )
                )

        return _pick_best_local_signal(
            candidates,
            fallback_name=name,
            fallback_reasoning="No local candles available for sweep/AVWAP setup",
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


def build_failed_auction_delta_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    orderflow_metrics: Optional[OrderFlowMetrics],
) -> StrategySignal:
    """Approximate a footprint-style failed auction with delta divergence reversal."""
    name = "failed_auction_delta"
    required_cols = {"open", "high", "low", "close", "volume"}
    if df is None or len(df) < 24 or any(col not in df.columns for col in required_cols):
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient {timeframe} data for failed-auction setup",
        )

    frame = df.dropna(subset=list(required_cols)).tail(60).reset_index(drop=True)
    if len(frame) < 24:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient clean {timeframe} candles for failed-auction setup",
        )

    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    context = frame.iloc[-9:-1].copy()
    if context.empty:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Not enough context candles on {timeframe}",
        )

    recent_low = float(context["low"].min())
    recent_high = float(context["high"].max())
    body, lower_wick, upper_wick, close_location = _candle_rejection_metrics(current)
    volume_baseline = float(context["volume"].median()) if float(context["volume"].median()) > 0 else float(current["volume"])
    volume_spike = float(current["volume"]) / volume_baseline if volume_baseline > 0 else 1.0

    delta_series = _compute_signed_volume_delta(frame.tail(10))
    prior_delta = float(delta_series.iloc[:5].sum())
    recent_delta = float(delta_series.iloc[5:].sum())
    delta_change = recent_delta - prior_delta

    start_close = float(frame.iloc[-6]["close"])
    setup_close = float(previous["close"])
    price_move_pct = ((setup_close - start_close) / start_close) if start_close > 0 else 0.0

    orderflow_score = float(orderflow_metrics.score) if orderflow_metrics is not None else 0.0
    bullish_orderflow = orderflow_metrics is not None and (
        orderflow_metrics.direction == "LONG" or orderflow_score >= 8.0
    )
    bearish_orderflow = orderflow_metrics is not None and (
        orderflow_metrics.direction == "SHORT" or orderflow_score <= -8.0
    )

    bullish_failed_auction = (
        float(current["low"]) <= recent_low
        and float(current["close"]) > float(previous["close"])
        and close_location >= 0.65
        and lower_wick > body * 0.65
    )
    bearish_failed_auction = (
        float(current["high"]) >= recent_high
        and float(current["close"]) < float(previous["close"])
        and close_location <= 0.35
        and upper_wick > body * 0.65
    )

    bullish_delta_divergence = (
        price_move_pct <= -0.003
        and delta_change > volume_baseline * 0.5
        and recent_delta > prior_delta * 0.4
    )
    bearish_delta_divergence = (
        price_move_pct >= 0.003
        and abs(delta_change) > volume_baseline * 0.5
        and recent_delta < prior_delta * 0.4
    )

    bullish_score = 0.0
    bearish_score = 0.0
    if bullish_failed_auction:
        bullish_score += 20.0
    if bullish_delta_divergence:
        bullish_score += 18.0
    if close_location >= 0.75:
        bullish_score += 8.0
    if volume_spike >= 1.05:
        bullish_score += 6.0
    if bullish_orderflow:
        bullish_score += min(18.0, max(8.0, abs(orderflow_score) * 0.45))

    if bearish_failed_auction:
        bearish_score -= 20.0
    if bearish_delta_divergence:
        bearish_score -= 18.0
    if close_location <= 0.25:
        bearish_score -= 8.0
    if volume_spike >= 1.05:
        bearish_score -= 6.0
    if bearish_orderflow:
        bearish_score -= min(18.0, max(8.0, abs(orderflow_score) * 0.45))

    metadata = {
        "timeframe": timeframe,
        "recent_low": round(recent_low, 4),
        "recent_high": round(recent_high, 4),
        "close_location": round(close_location, 3),
        "price_move_pct": round(price_move_pct, 5),
        "recent_delta": round(recent_delta, 2),
        "prior_delta": round(prior_delta, 2),
        "delta_change": round(delta_change, 2),
        "volume_spike": round(volume_spike, 3),
        "orderflow": orderflow_metrics.to_dict() if orderflow_metrics is not None else {},
        "bullish_setup": {
            "failed_auction": bullish_failed_auction,
            "delta_divergence": bullish_delta_divergence,
            "orderflow": bullish_orderflow,
        },
        "bearish_setup": {
            "failed_auction": bearish_failed_auction,
            "delta_divergence": bearish_delta_divergence,
            "orderflow": bearish_orderflow,
        },
    }

    if bullish_failed_auction and bullish_delta_divergence and bullish_orderflow and bullish_score >= 42 and bullish_score >= abs(bearish_score) + 6:
        score = _clamp(bullish_score)
        return StrategySignal(
            name=name,
            direction="LONG",
            confidence=min(abs(score) / 75.0, 1.0),
            score=score,
            reasoning=(
                f"{timeframe} failed auction at lows with positive delta divergence; "
                f"price {price_move_pct:+.2%}, delta Δ={delta_change:+.0f}, orderflow {orderflow_score:+.1f}"
            ),
            metadata=metadata,
        )

    if bearish_failed_auction and bearish_delta_divergence and bearish_orderflow and abs(bearish_score) >= 42 and abs(bearish_score) >= bullish_score + 6:
        score = _clamp(bearish_score)
        return StrategySignal(
            name=name,
            direction="SHORT",
            confidence=min(abs(score) / 75.0, 1.0),
            score=score,
            reasoning=(
                f"{timeframe} failed auction at highs with negative delta divergence; "
                f"price {price_move_pct:+.2%}, delta Δ={delta_change:+.0f}, orderflow {orderflow_score:+.1f}"
            ),
            metadata=metadata,
        )

    return StrategySignal(
        name=name,
        direction="NEUTRAL",
        confidence=0.0,
        score=0.0,
        reasoning=(
            f"No confirmed {timeframe} failed-auction reversal. "
            f"Bull={bullish_failed_auction}/{bullish_delta_divergence}/{bullish_orderflow}, "
            f"Bear={bearish_failed_auction}/{bearish_delta_divergence}/{bearish_orderflow}"
        ),
        metadata=metadata,
    )


async def strategy_failed_auction_delta(symbol: str) -> StrategySignal:
    """Local-data reversal setup inspired by public TradingView footprint and delta-divergence guidance."""
    name = "failed_auction_delta"
    try:
        store = get_data_store()
        snapshot = get_orderbook_feed().get_snapshot(symbol)
        orderflow_metrics = analyze_order_flow(snapshot) if snapshot is not None else None

        candidates: List[StrategySignal] = []
        for timeframe in ["5m", "15m", "1h"]:
            candidate = store.get_dataframe(symbol, timeframe, limit=180)
            if len(candidate) >= 32:
                candidates.append(
                    build_failed_auction_delta_signal(
                        symbol,
                        timeframe,
                        candidate,
                        orderflow_metrics,
                    )
                )

        return _pick_best_local_signal(
            candidates,
            fallback_name=name,
            fallback_reasoning="No local candles available for failed-auction setup",
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


def build_cumulative_volume_delta_reversal_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    orderflow_metrics: Optional[OrderFlowMetrics],
) -> StrategySignal:
    """Approximate a TradingView-style CVD divergence and reclaim reversal setup."""
    name = "cumulative_volume_delta_reversal"
    required_cols = {"open", "high", "low", "close", "volume"}
    if df is None or len(df) < 28 or any(col not in df.columns for col in required_cols):
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient {timeframe} data for CVD reversal setup",
        )

    frame = df.dropna(subset=list(required_cols)).tail(72).reset_index(drop=True)
    if len(frame) < 28:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Insufficient clean {timeframe} candles for CVD reversal setup",
        )

    frame = frame.copy()
    frame["cvd"] = _compute_cumulative_volume_delta(frame)

    earlier = frame.iloc[-18:-9].copy()
    recent = frame.iloc[-9:].copy()
    if earlier.empty or recent.empty:
        return StrategySignal(
            name=name,
            direction="NEUTRAL",
            confidence=0.0,
            score=0.0,
            reasoning=f"Not enough context candles on {timeframe}",
        )

    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    body, lower_wick, upper_wick, close_location = _candle_rejection_metrics(current)

    recent_range = frame.tail(12)
    recent_range_low = float(recent_range["low"].min())
    recent_range_high = float(recent_range["high"].max())
    recent_range_size = max(recent_range_high - recent_range_low, 1e-9)

    baseline_source = frame["volume"].iloc[-21:-1] if len(frame) > 21 else frame["volume"].iloc[:-1]
    volume_baseline = float(baseline_source.median()) if not baseline_source.empty else float(current["volume"])
    volume_spike = float(current["volume"]) / volume_baseline if volume_baseline > 0 else 1.0
    cvd_unit = max(volume_baseline, 1.0)

    earlier_price_low = float(earlier["low"].min())
    recent_price_low = float(recent["low"].min())
    earlier_price_high = float(earlier["high"].max())
    recent_price_high = float(recent["high"].max())
    earlier_cvd_low = float(earlier["cvd"].min())
    recent_cvd_low = float(recent["cvd"].min())
    earlier_cvd_high = float(earlier["cvd"].max())
    recent_cvd_high = float(recent["cvd"].max())

    bullish_divergence = (
        recent_price_low < earlier_price_low * 0.998
        and recent_cvd_low > earlier_cvd_low + cvd_unit
    )
    bearish_divergence = (
        recent_price_high > earlier_price_high * 1.002
        and recent_cvd_high < earlier_cvd_high - cvd_unit
    )

    bullish_reclaim = (
        float(current["close"]) > float(previous["high"])
        and close_location >= 0.60
        and float(current["close"]) >= recent_range_low + (recent_range_size * 0.62)
    )
    bearish_reclaim = (
        float(current["close"]) < float(previous["low"])
        and close_location <= 0.40
        and float(current["close"]) <= recent_range_low + (recent_range_size * 0.38)
    )

    orderflow_score = float(orderflow_metrics.score) if orderflow_metrics is not None else 0.0
    bullish_orderflow = orderflow_metrics is not None and (
        orderflow_metrics.direction == "LONG" or orderflow_score >= 8.0
    )
    bearish_orderflow = orderflow_metrics is not None and (
        orderflow_metrics.direction == "SHORT" or orderflow_score <= -8.0
    )

    bullish_score = 0.0
    bearish_score = 0.0
    if bullish_divergence:
        bullish_score += 22.0
    if bullish_reclaim:
        bullish_score += 16.0
    if lower_wick > body * 0.5:
        bullish_score += 6.0
    if volume_spike >= 1.08:
        bullish_score += 6.0
    if bullish_orderflow:
        bullish_score += min(18.0, max(8.0, abs(orderflow_score) * 0.45))

    if bearish_divergence:
        bearish_score -= 22.0
    if bearish_reclaim:
        bearish_score -= 16.0
    if upper_wick > body * 0.5:
        bearish_score -= 6.0
    if volume_spike >= 1.08:
        bearish_score -= 6.0
    if bearish_orderflow:
        bearish_score -= min(18.0, max(8.0, abs(orderflow_score) * 0.45))

    metadata = {
        "timeframe": timeframe,
        "earlier_price_low": round(earlier_price_low, 4),
        "recent_price_low": round(recent_price_low, 4),
        "earlier_price_high": round(earlier_price_high, 4),
        "recent_price_high": round(recent_price_high, 4),
        "earlier_cvd_low": round(earlier_cvd_low, 2),
        "recent_cvd_low": round(recent_cvd_low, 2),
        "earlier_cvd_high": round(earlier_cvd_high, 2),
        "recent_cvd_high": round(recent_cvd_high, 2),
        "close_location": round(close_location, 3),
        "volume_spike": round(volume_spike, 3),
        "orderflow": orderflow_metrics.to_dict() if orderflow_metrics is not None else {},
        "bullish_setup": {
            "cvd_divergence": bullish_divergence,
            "reclaim": bullish_reclaim,
            "orderflow": bullish_orderflow,
        },
        "bearish_setup": {
            "cvd_divergence": bearish_divergence,
            "reclaim": bearish_reclaim,
            "orderflow": bearish_orderflow,
        },
    }

    if bullish_divergence and bullish_reclaim and bullish_orderflow and bullish_score >= 40 and bullish_score >= abs(bearish_score) + 6:
        score = _clamp(bullish_score)
        return StrategySignal(
            name=name,
            direction="LONG",
            confidence=min(abs(score) / 75.0, 1.0),
            score=score,
            reasoning=(
                f"{timeframe} CVD bullish divergence below {earlier_price_low:.2f}->{recent_price_low:.2f} "
                f"with reclaim; CVD {earlier_cvd_low:.0f}->{recent_cvd_low:.0f}, "
                f"volume x{volume_spike:.2f}, orderflow {orderflow_score:+.1f}"
            ),
            metadata=metadata,
        )

    if bearish_divergence and bearish_reclaim and bearish_orderflow and abs(bearish_score) >= 40 and abs(bearish_score) >= bullish_score + 6:
        score = _clamp(bearish_score)
        return StrategySignal(
            name=name,
            direction="SHORT",
            confidence=min(abs(score) / 75.0, 1.0),
            score=score,
            reasoning=(
                f"{timeframe} CVD bearish divergence above {earlier_price_high:.2f}->{recent_price_high:.2f} "
                f"with rejection; CVD {earlier_cvd_high:.0f}->{recent_cvd_high:.0f}, "
                f"volume x{volume_spike:.2f}, orderflow {orderflow_score:+.1f}"
            ),
            metadata=metadata,
        )

    return StrategySignal(
        name=name,
        direction="NEUTRAL",
        confidence=0.0,
        score=0.0,
        reasoning=(
            f"No confirmed {timeframe} CVD reversal. "
            f"Bull={bullish_divergence}/{bullish_reclaim}/{bullish_orderflow}, "
            f"Bear={bearish_divergence}/{bearish_reclaim}/{bearish_orderflow}"
        ),
        metadata=metadata,
    )


async def strategy_cumulative_volume_delta_reversal(symbol: str) -> StrategySignal:
    """Local-data reversal setup inspired by TradingView cumulative volume delta divergence."""
    name = "cumulative_volume_delta_reversal"
    try:
        store = get_data_store()
        snapshot = get_orderbook_feed().get_snapshot(symbol)
        orderflow_metrics = analyze_order_flow(snapshot) if snapshot is not None else None

        candidates: List[StrategySignal] = []
        for timeframe in ["5m", "15m", "1h"]:
            candidate = store.get_dataframe(symbol, timeframe, limit=180)
            if len(candidate) >= 36:
                candidates.append(
                    build_cumulative_volume_delta_reversal_signal(
                        symbol,
                        timeframe,
                        candidate,
                        orderflow_metrics,
                    )
                )

        return _pick_best_local_signal(
            candidates,
            fallback_name=name,
            fallback_reasoning="No local candles available for CVD reversal setup",
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 1: BTC Dominance Rotation
# When BTC dominance rises → capital flows to BTC → bullish BTC.
# When BTC dominance falls → alt season → bearish BTC, bullish alts.
# ═════════════════════════════════════════════════════════════════════
async def strategy_btc_dominance_rotation(symbol: str) -> StrategySignal:
    name = "btc_dominance_rotation"
    try:
        global_data = await async_fetch_coingecko_global()
        btc_dom = global_data.get("btc_dominance", 50.0)
        mcap_change = global_data.get("market_cap_change_24h_pct", 0.0)

        is_btc = symbol.upper().startswith("BTC")

        if btc_dom > 55:
            # BTC dominant — favour BTC, avoid alts
            score = 40.0 if is_btc else -30.0
        elif btc_dom < 42:
            # Alt season — favour alts, reduce BTC bias
            score = -25.0 if is_btc else 35.0
        else:
            score = mcap_change * 2.0

        score = _clamp(score)
        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=min(abs(score) / 100.0, 1.0),
            score=score,
            reasoning=f"BTC dom {btc_dom:.1f}%, mcap Δ {mcap_change:+.1f}%",
            metadata={"btc_dominance": btc_dom, "mcap_change": mcap_change},
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 2: Exchange Flow Divergence
# Compare price across multiple exchanges → detect divergence.
# ═════════════════════════════════════════════════════════════════════
async def strategy_exchange_flow_divergence(symbol: str) -> StrategySignal:
    name = "exchange_flow_divergence"
    try:
        data = await async_fetch_multi_exchange_price(symbol)
        spread = data.get("spread_pct", 0.0)
        avg_price = data.get("avg_price", 0.0)

        # Large spread suggests impending arbitrage correction
        if spread > 0.5:
            # Find which exchange is cheapest — buy there sentiment
            score = 30.0
        elif spread > 0.2:
            score = 15.0
        else:
            score = 0.0

        # Check if Binance is below average (buy signal)
        binance_p = data.get("prices", {}).get("binance", avg_price)
        if avg_price > 0 and binance_p > 0:
            binance_delta = ((binance_p - avg_price) / avg_price) * 100
            if binance_delta < -0.15:
                score = 25.0  # Binance lagging → expect catch-up rally
            elif binance_delta > 0.15:
                score = -20.0  # Binance leading → expect mean revert

        score = _clamp(score)
        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=min(abs(score) / 100.0, 1.0),
            score=score,
            reasoning=f"Spread {spread:.2f}%, Binance delta from avg {binance_delta:+.3f}%"
            if avg_price else f"Spread {spread:.2f}%",
            metadata=data,
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 3: Social Momentum
# CryptoCompare social stats — Reddit & Twitter activity spikes.
# ═════════════════════════════════════════════════════════════════════
async def strategy_social_momentum(symbol: str) -> StrategySignal:
    name = "social_momentum"
    try:
        cg_id = _cg_id(symbol)
        social = await async_fetch_cryptocompare_social(cg_id)
        reddit_active = social.get("reddit_active_users", 0)
        reddit_posts = social.get("reddit_posts_per_day", 0)
        twitter_followers = social.get("twitter_followers", 0)

        score = 0.0
        # Reddit momentum
        if reddit_active > 5000:
            score += 20.0
        elif reddit_active > 2000:
            score += 10.0

        if reddit_posts > 50:
            score += 10.0

        # Twitter momentum
        if twitter_followers > 1_000_000:
            score += 10.0

        # Cap and direction
        score = _clamp(score, 0, 50)  # social is long-biased by nature
        return StrategySignal(
            name=name,
            direction=_direction(score, threshold=10.0),
            confidence=min(score / 50.0, 1.0),
            score=score,
            reasoning=f"Reddit active={reddit_active}, posts/day={reddit_posts}, "
                      f"Twitter followers={twitter_followers}",
            metadata=social,
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 4: Multi-Exchange Arb Signal
# Price spread > threshold → arb pressure → mean reversion expected.
# ═════════════════════════════════════════════════════════════════════
async def strategy_multi_exchange_arb(symbol: str) -> StrategySignal:
    name = "multi_exchange_arb"
    try:
        data = await async_fetch_multi_exchange_price(symbol)
        spread = data.get("spread_pct", 0.0)
        prices = data.get("prices", {})

        if not prices or spread < 0.05:
            return StrategySignal(
                name=name, direction="NEUTRAL", confidence=0.0, score=0.0,
                reasoning=f"Spread {spread:.3f}% too tight")

        avg = data.get("avg_price", 0)
        binance_p = prices.get("binance", avg)

        # If Binance below avg → expect mean reversion UP (long)
        # If Binance above avg → expect mean reversion DOWN (short)
        delta_pct = ((binance_p - avg) / avg * 100) if avg > 0 else 0
        score = _clamp(-delta_pct * 40, -60, 60)

        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=min(abs(score) / 60.0, 1.0),
            score=score,
            reasoning=f"Binance vs avg delta {delta_pct:+.3f}%, spread {spread:.2f}%",
            metadata={"spread": spread, "delta_pct": delta_pct},
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 5: Mempool Congestion Play
# High mempool → network stress → potential volatility / dump risk.
# ═════════════════════════════════════════════════════════════════════
async def strategy_mempool_play(symbol: str) -> StrategySignal:
    name = "mempool_play"
    try:
        mempool = await async_fetch_blockchain_mempool()
        tx_count = mempool.get("unconfirmed_tx_count", 0)

        # High mempool = congestion = stress = bearish pressure (short-term)
        if tx_count > 150_000:
            score = -30.0
        elif tx_count > 100_000:
            score = -15.0
        elif tx_count < 30_000:
            score = 10.0  # very empty → calm market
        else:
            score = 0.0

        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=min(abs(score) / 30.0, 1.0),
            score=score,
            reasoning=f"Mempool tx={tx_count:,}",
            metadata=mempool,
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 6: News Velocity
# Sudden spike in article count across sources → event-driven move.
# ═════════════════════════════════════════════════════════════════════
async def strategy_news_velocity(symbol: str) -> StrategySignal:
    name = "news_velocity"
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        vader = SentimentIntensityAnalyzer()

        articles = await async_fetch_all_news()
        if not articles:
            return StrategySignal(
                name=name, direction="NEUTRAL", confidence=0.0, score=0.0,
                reasoning="No articles fetched")

        coin_kw = symbol[:3].lower()  # e.g., "btc" from "BTCUSDT"
        relevant = [
            a for a in articles
            if coin_kw in (a.get("title", "") + " " + (a.get("description") or "")).lower()
        ]

        count = len(relevant)
        if count < 3:
            return StrategySignal(
                name=name, direction="NEUTRAL", confidence=0.0, score=0.0,
                reasoning=f"Only {count} relevant articles")

        # VADER sentiment on relevant articles
        compounds = []
        for a in relevant:
            text = (a.get("title", "") + ". " + (a.get("description") or "")).strip()
            if text:
                compounds.append(vader.polarity_scores(text)["compound"])

        avg_sent = sum(compounds) / len(compounds) if compounds else 0.0

        # Velocity boost: more articles = stronger signal
        velocity_mult = min(count / 10.0, 2.0)
        score = _clamp(avg_sent * 40 * velocity_mult)

        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=min(abs(score) / 80.0, 1.0),
            score=score,
            reasoning=f"{count} articles, avg VADER={avg_sent:+.3f}, "
                      f"velocity_mult={velocity_mult:.1f}",
            metadata={"count": count, "avg_vader": avg_sent},
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 7: Derivatives Divergence
# RSI + MACD divergence from TAAPI.IO → detect trend exhaustion.
# ═════════════════════════════════════════════════════════════════════
async def strategy_derivatives_divergence(symbol: str) -> StrategySignal:
    name = "derivatives_divergence"
    try:
        pair = symbol.upper().replace("USDT", "/USDT")
        rsi_val, macd_data, bb_data = await asyncio.gather(
            async_fetch_taapi_rsi(pair),
            async_fetch_taapi_macd(pair),
            async_fetch_taapi_bbands(pair),
        )

        score = 0.0

        # RSI extremes — async_fetch_taapi_rsi returns a float
        rsi = float(rsi_val) if rsi_val else 50.0
        if rsi > 75:
            score -= 30.0   # overbought
        elif rsi > 65:
            score -= 10.0
        elif rsi < 25:
            score += 30.0   # oversold
        elif rsi < 35:
            score += 10.0

        # MACD histogram direction — wrapper returns "macd", "signal", "histogram"
        hist = macd_data.get("signal", 0.0)
        macd_val = macd_data.get("macd", 0.0)
        if macd_val - hist > 0:
            score += 10.0  # bullish cross
        elif macd_val - hist < 0:
            score -= 10.0  # bearish cross

        # Bollinger Band position — wrapper returns "upper", "middle", "lower"
        bb_upper = bb_data.get("upper", 0)
        bb_lower = bb_data.get("lower", 0)
        bb_mid = bb_data.get("middle", 0)
        if bb_upper and bb_lower and bb_mid:
            # If we had current price, we'd compare. Use middle band heuristic.
            band_width = (bb_upper - bb_lower) / bb_mid * 100 if bb_mid else 0
            if band_width > 8:
                score += 5.0 if score > 0 else -5.0  # amplify existing direction

        score = _clamp(score)
        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=min(abs(score) / 60.0, 1.0),
            score=score,
            reasoning=f"RSI={rsi:.1f}, MACD hist={hist:.4f}, BB width={band_width:.1f}%"
            if bb_mid else f"RSI={rsi:.1f}, MACD hist={hist:.4f}",
            metadata={"rsi": rsi, "macd_hist": hist, "bb_data": bb_data},
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 8: FreeCrypto TA Confluence
# FreeCryptoAPI technical analysis + breakout signals → conviction.
# ═════════════════════════════════════════════════════════════════════
async def strategy_freecrypto_ta(symbol: str) -> StrategySignal:
    name = "freecrypto_ta"
    try:
        coin = symbol.replace("USDT", "").upper()
        ta, breakouts = await asyncio.gather(
            get_technical_analysis(coin),
            get_breakouts(),
            return_exceptions=True,
        )

        score = 0.0

        # Technical analysis indicators
        if isinstance(ta, dict) and not isinstance(ta, Exception):
            rsi = ta.get("rsi") or ta.get("RSI")
            macd_sig = ta.get("macd_signal") or ta.get("MACD_Signal")
            if rsi is not None:
                rsi = float(rsi)
                if rsi > 70:
                    score -= min((rsi - 70) * 2, 40)
                elif rsi < 30:
                    score += min((30 - rsi) * 2, 40)
            if macd_sig is not None:
                score += max(min(float(macd_sig) * 10, 30), -30)

        # Breakout signals
        breakout_hit = False
        if isinstance(breakouts, dict) and not isinstance(breakouts, Exception):
            items = breakouts.get("data") or breakouts.get("breakouts") or []
            if isinstance(items, list):
                for item in items:
                    item_name = (item.get("symbol") or item.get("coin") or "").upper()
                    if coin in item_name:
                        direction = (item.get("direction") or "").lower()
                        if "bull" in direction or "up" in direction:
                            score += 20
                        elif "bear" in direction or "down" in direction:
                            score -= 20
                        breakout_hit = True
                        break

        score = _clamp(score)
        conf = min(abs(score) / 80, 1.0)
        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=conf,
            score=score,
            reasoning=f"FreeCryptoTA: score={score:.1f}, breakout={'yes' if breakout_hit else 'no'}",
            metadata={"ta": ta if isinstance(ta, dict) else {}, "breakout_hit": breakout_hit},
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 9: Hash Rate Momentum (BTC only)
# Rising hash rate → miners bullish → positive signal.
# ═════════════════════════════════════════════════════════════════════
async def strategy_hash_rate_momentum(symbol: str) -> StrategySignal:
    name = "hash_rate_momentum"
    try:
        stats = await async_fetch_blockchain_stats()
        hash_rate = stats.get("hash_rate", 0)
        difficulty = stats.get("difficulty", 0)

        if hash_rate <= 0:
            return StrategySignal(
                name=name, direction="NEUTRAL", confidence=0.0, score=0.0,
                reasoning="Hash rate data unavailable")

        # Compare hash rate to difficulty for miner profitability signal
        # Higher hash rate relative to difficulty → miners profitable → bullish
        # We use absolute hash rate as a trend proxy
        # >400 EH/s is very strong, <200 EH/s is concerning
        hr_eh = hash_rate / 1e18 if hash_rate > 1e15 else hash_rate  # normalize

        if hr_eh > 600:
            score = 25.0
        elif hr_eh > 400:
            score = 15.0
        elif hr_eh > 200:
            score = 5.0
        else:
            score = -10.0

        # Apply only to BTC-related pairs
        if not symbol.upper().startswith("BTC"):
            score *= 0.3  # reduced relevance for non-BTC

        score = _clamp(score)
        return StrategySignal(
            name=name,
            direction=_direction(score, threshold=10.0),
            confidence=min(abs(score) / 30.0, 1.0),
            score=score,
            reasoning=f"Hash rate={hr_eh:.0f} EH/s, difficulty={difficulty:.2e}",
            metadata={"hash_rate": hash_rate, "difficulty": difficulty},
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 10: Fear & Greed Contrarian
# Extreme fear → buy (contrarian), extreme greed → sell.
# Uses 7-day F&G history for momentum.
# ═════════════════════════════════════════════════════════════════════
async def strategy_fng_contrarian(symbol: str) -> StrategySignal:
    name = "fng_contrarian"
    try:
        current_data, history = await asyncio.gather(
            async_fetch_fear_greed(),
            async_fetch_fear_greed_history(days=7),
        )

        # async_fetch_fear_greed returns dict with "value" key
        current = int(current_data.get("value", 50)) if isinstance(current_data, dict) else 50

        if not isinstance(history, list) or len(history) == 0:
            history = [{"value": current}]

        values = [int(h.get("value", 50)) for h in history]
        avg_7d = sum(values) / len(values) if values else 50.0
        momentum = current - avg_7d  # positive = fear easing, negative = fear increasing

        # Contrarian logic
        score = 0.0
        if current <= 20:
            score = 45.0  # extreme fear → strong buy
        elif current <= 35:
            score = 20.0
        elif current >= 80:
            score = -45.0  # extreme greed → strong sell
        elif current >= 65:
            score = -20.0

        # Momentum modifier: if fear easing, amplify buy; if greed rising, amplify sell
        if momentum > 10 and score > 0:
            score += 10.0
        elif momentum < -10 and score < 0:
            score -= 10.0

        score = _clamp(score)
        return StrategySignal(
            name=name,
            direction=_direction(score),
            confidence=min(abs(score) / 50.0, 1.0),
            score=score,
            reasoning=f"FnG={current}, 7d avg={avg_7d:.0f}, momentum={momentum:+.0f}",
            metadata={"current": current, "avg_7d": avg_7d, "momentum": momentum},
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 11: Core Financial Strength
# Structural trend, drawdown control, and volume sponsorship.
# ═════════════════════════════════════════════════════════════════════
async def strategy_core_financial_strength(symbol: str) -> StrategySignal:
    name = "core_financial_strength"
    try:
        store = get_data_store()
        candidates: List[StrategySignal] = []
        for timeframe in ["5m", "15m", "1h"]:
            candidate = store.get_dataframe(symbol, timeframe, limit=180)
            if len(candidate) >= 40:
                candidates.append(build_core_financial_strength_signal(symbol, timeframe, candidate))

        return _pick_best_local_signal(
            candidates,
            fallback_name=name,
            fallback_reasoning="No local candles available for financial-strength analysis",
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 12: Advanced Quant Analysis
# Compact factor stack with risk-adjusted momentum and path efficiency.
# ═════════════════════════════════════════════════════════════════════
async def strategy_advanced_quant_analysis(symbol: str) -> StrategySignal:
    name = "advanced_quant_analysis"
    try:
        store = get_data_store()
        candidates: List[StrategySignal] = []
        for timeframe in ["5m", "15m", "1h"]:
            candidate = store.get_dataframe(symbol, timeframe, limit=180)
            if len(candidate) >= 40:
                candidates.append(build_advanced_quant_analysis_signal(symbol, timeframe, candidate))

        return _pick_best_local_signal(
            candidates,
            fallback_name=name,
            fallback_reasoning="No local candles available for quant analysis",
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY 13: Dual-Mode Financial Intelligence
# Tactical when orderflow is rich, strategic when only structural data is stable.
# ═════════════════════════════════════════════════════════════════════
async def strategy_dual_mode_financial_intelligence(symbol: str) -> StrategySignal:
    name = "dual_mode_financial_intelligence"
    try:
        store = get_data_store()
        snapshot = get_orderbook_feed().get_snapshot(symbol)
        orderflow_metrics = analyze_order_flow(snapshot) if snapshot is not None else None

        candidates: List[StrategySignal] = []
        for timeframe in ["5m", "15m", "1h"]:
            candidate = store.get_dataframe(symbol, timeframe, limit=180)
            if len(candidate) >= 40:
                candidates.append(
                    build_dual_mode_financial_intelligence_signal(
                        symbol,
                        timeframe,
                        candidate,
                        orderflow_metrics,
                    )
                )

        return _pick_best_local_signal(
            candidates,
            fallback_name=name,
            fallback_reasoning="No local candles available for dual-mode intelligence",
        )
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return StrategySignal(name=name, direction="NEUTRAL", confidence=0.0, score=0.0)


# ═════════════════════════════════════════════════════════════════════
# STRATEGY RUNNER — execute all 16 in parallel and fuse
# ═════════════════════════════════════════════════════════════════════

ALL_STRATEGIES = [
    strategy_liquidity_sweep_avwap,
    strategy_failed_auction_delta,
    strategy_cumulative_volume_delta_reversal,
    strategy_btc_dominance_rotation,
    strategy_exchange_flow_divergence,
    strategy_social_momentum,
    strategy_multi_exchange_arb,
    strategy_mempool_play,
    strategy_news_velocity,
    strategy_derivatives_divergence,
    strategy_freecrypto_ta,
    strategy_hash_rate_momentum,
    strategy_fng_contrarian,
    strategy_core_financial_strength,
    strategy_advanced_quant_analysis,
    strategy_dual_mode_financial_intelligence,
]

STRATEGY_WEIGHTS: Dict[str, float] = {
    "liquidity_sweep_avwap": 0.18,
    "failed_auction_delta": 0.16,
    "cumulative_volume_delta_reversal": 0.14,
    "btc_dominance_rotation": 0.12,
    "exchange_flow_divergence": 0.10,
    "social_momentum": 0.08,
    "multi_exchange_arb": 0.10,
    "mempool_play": 0.07,
    "news_velocity": 0.13,
    "derivatives_divergence": 0.15,
    "freecrypto_ta": 0.10,
    "hash_rate_momentum": 0.07,
    "fng_contrarian": 0.08,
    "core_financial_strength": 0.16,
    "advanced_quant_analysis": 0.18,
    "dual_mode_financial_intelligence": 0.17,
}


@dataclass
class StrategyFusionResult:
    fused_score: float
    direction: str
    confidence: float
    signals: List[StrategySignal]
    active_count: int
    contributing_count: int
    reasoning: str


def fuse_strategy_signals(results: List[StrategySignal]) -> StrategyFusionResult:
    """Fuse strategy outputs while ignoring flat neutral signals that add no information."""
    if not results:
        return StrategyFusionResult(
            fused_score=0.0,
            direction="NEUTRAL",
            confidence=0.0,
            signals=[],
            active_count=0,
            contributing_count=0,
            reasoning="All strategies failed",
        )

    weighted_sum = 0.0
    weight_total = 0.0
    active = 0
    contributing = 0
    parts: List[str] = []
    local_directionals: List[StrategySignal] = []
    core_directionals: List[StrategySignal] = []

    for sig in results:
        w = STRATEGY_WEIGHTS.get(sig.name, 0.10)
        contributes = sig.direction != "NEUTRAL" or abs(sig.score) >= 1.0 or sig.confidence > 0.05
        effective_weight = w
        if sig.name in LOCAL_SETUP_PRIORITY and sig.direction != "NEUTRAL":
            effective_weight *= LOCAL_SETUP_PRIORITY[sig.name]
            local_directionals.append(sig)
        if sig.name in CORE_INTELLIGENCE_NAMES and sig.direction != "NEUTRAL":
            core_directionals.append(sig)
        if contributes:
            weighted_sum += sig.score * effective_weight
            weight_total += effective_weight
            contributing += 1
        if sig.direction != "NEUTRAL":
            active += 1
        parts.append(f"{sig.name}={sig.score:+.0f}")

    fused = _clamp(weighted_sum / weight_total if weight_total > 0 else 0.0)

    local_bias = 0.0
    if local_directionals:
        directions = {sig.direction for sig in local_directionals}
        if len(directions) == 1:
            bias_sign = 1.0 if next(iter(directions)) == "LONG" else -1.0
            local_bias = sum(min(abs(sig.score) * 0.16, 14.0) for sig in local_directionals)
            fused = _clamp(fused + (bias_sign * local_bias))

    core_bias = 0.0
    if len(core_directionals) >= 2:
        directions = {sig.direction for sig in core_directionals}
        if len(directions) == 1:
            bias_sign = 1.0 if next(iter(directions)) == "LONG" else -1.0
            core_bias = sum(min(abs(sig.score) * 0.09, 7.0) for sig in core_directionals)
            fused = _clamp(fused + (bias_sign * core_bias))

    if fused > 15:
        direction = "LONG"
    elif fused < -15:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    confidence = min(abs(fused) / 80.0, 1.0)
    if local_bias > 0:
        confidence = max(confidence, min(0.52 + (0.1 * len(local_directionals)) + (local_bias / 100.0), 0.96))
    if core_bias > 0:
        confidence = max(confidence, min(0.48 + (0.07 * len(core_directionals)) + (core_bias / 140.0), 0.92))
    reasoning = (
        f"Fused={fused:+.1f} from {len(results)} strategies "
        f"({active} active, {contributing} contributing, local_bias={local_bias:+.1f}, core_bias={core_bias:+.1f}). {', '.join(parts)}"
    )

    return StrategyFusionResult(
        fused_score=fused,
        direction=direction,
        confidence=confidence,
        signals=results,
        active_count=active,
        contributing_count=contributing,
        reasoning=reasoning,
    )


async def run_all_strategies(symbol: str) -> StrategyFusionResult:
    """Run all strategies in parallel, fuse via weighted average."""
    tasks = [s(symbol) for s in ALL_STRATEGIES]
    results: List[StrategySignal] = []

    raw = await asyncio.gather(*tasks, return_exceptions=True)
    for r in raw:
        if isinstance(r, StrategySignal):
            results.append(r)
        elif isinstance(r, Exception):
            logger.warning("Strategy exception: %s", r)

    return fuse_strategy_signals(results)
