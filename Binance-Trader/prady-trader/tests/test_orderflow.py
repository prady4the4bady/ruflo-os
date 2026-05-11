from __future__ import annotations

from data.orderbook_feed import OrderBookSnapshot
from data.orderflow import analyze_order_flow


def test_orderflow_detects_bid_pressure():
    snapshot = OrderBookSnapshot(
        symbol="BTCUSDT",
        bids=[[100.0, 8.0], [99.9, 6.0], [99.8, 5.0]],
        asks=[[100.1, 2.0], [100.2, 2.5], [100.3, 3.0]],
        timestamp=1,
    )

    metrics = analyze_order_flow(snapshot)

    assert metrics.direction == "LONG"
    assert metrics.score > 0
    assert metrics.microprice_delta_bps > 0


def test_orderflow_detects_ask_pressure():
    snapshot = OrderBookSnapshot(
        symbol="BTCUSDT",
        bids=[[100.0, 2.0], [99.9, 1.5], [99.8, 1.0]],
        asks=[[100.1, 7.0], [100.2, 6.5], [100.3, 5.0]],
        timestamp=1,
    )

    metrics = analyze_order_flow(snapshot)

    assert metrics.direction == "SHORT"
    assert metrics.score < 0
    assert metrics.microprice_delta_bps < 0