"""
PRADY TRADER — Order-flow helpers derived from live order-book snapshots.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from config.constants import ORDERFLOW_NEUTRAL_BAND


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class OrderFlowMetrics:
    imbalance: float
    weighted_imbalance: float
    top_level_imbalance: float
    microprice_delta_bps: float
    spread_bps: float
    score: float
    direction: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_order_flow(snapshot) -> OrderFlowMetrics:
    """Convert a depth snapshot into a directional order-flow signal."""
    if snapshot is None or not snapshot.bids or not snapshot.asks:
        return OrderFlowMetrics(
            imbalance=0.0,
            weighted_imbalance=0.0,
            top_level_imbalance=0.0,
            microprice_delta_bps=0.0,
            spread_bps=0.0,
            score=0.0,
            direction="NEUTRAL",
            confidence=0.0,
        )

    best_bid, best_bid_qty = snapshot.bids[0]
    best_ask, best_ask_qty = snapshot.asks[0]
    mid_price = snapshot.mid_price or 0.0

    weighted_bid = 0.0
    weighted_ask = 0.0
    for index, (_, qty) in enumerate(snapshot.bids, start=1):
        weighted_bid += float(qty) / index
    for index, (_, qty) in enumerate(snapshot.asks, start=1):
        weighted_ask += float(qty) / index

    weighted_total = weighted_bid + weighted_ask
    weighted_imbalance = (
        (weighted_bid - weighted_ask) / weighted_total
        if weighted_total > 0
        else 0.0
    )

    top_total = float(best_bid_qty) + float(best_ask_qty)
    top_level_imbalance = (
        (float(best_bid_qty) - float(best_ask_qty)) / top_total
        if top_total > 0
        else 0.0
    )

    microprice = (
        (best_ask * float(best_bid_qty)) + (best_bid * float(best_ask_qty))
    ) / top_total if top_total > 0 else mid_price
    microprice_delta_bps = (
        ((microprice - mid_price) / mid_price) * 10_000.0
        if mid_price > 0
        else 0.0
    )

    spread_bps = ((snapshot.spread / mid_price) * 10_000.0) if mid_price > 0 else 0.0

    score = (
        weighted_imbalance * 45.0
        + top_level_imbalance * 20.0
        + _clamp(microprice_delta_bps * 1.5, -20.0, 20.0)
    )

    if spread_bps > 5.0:
        spread_penalty = _clamp(1.0 - ((spread_bps - 5.0) / 25.0), 0.35, 1.0)
        score *= spread_penalty

    score = _clamp(score, -100.0, 100.0)
    if score >= ORDERFLOW_NEUTRAL_BAND:
        direction = "LONG"
    elif score <= -ORDERFLOW_NEUTRAL_BAND:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    confidence = min(abs(score) / 55.0, 1.0)

    return OrderFlowMetrics(
        imbalance=round(float(snapshot.imbalance), 4),
        weighted_imbalance=round(weighted_imbalance, 4),
        top_level_imbalance=round(top_level_imbalance, 4),
        microprice_delta_bps=round(microprice_delta_bps, 3),
        spread_bps=round(spread_bps, 3),
        score=round(score, 2),
        direction=direction,
        confidence=round(confidence, 4),
    )