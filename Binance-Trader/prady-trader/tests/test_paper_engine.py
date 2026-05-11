from decimal import Decimal

from execution.paper_engine import PaperTradingEngine


def test_closing_position_cancels_remaining_bracket_orders():
    engine = PaperTradingEngine(Decimal("10000"))

    engine.place_market_order("BNBUSDT", "BUY", 1.0, 100.0)
    engine.place_stop_market("BNBUSDT", "SELL", 1.0, 98.0)
    engine.place_limit_order("BNBUSDT", "SELL", 1.0, 103.0)

    assert len([order for order in engine._pending_orders if order.symbol == "BNBUSDT"]) == 2

    engine.check_pending_orders("BNBUSDT", 103.0)

    assert "BNBUSDT" not in engine.positions
    assert [order for order in engine._pending_orders if order.symbol == "BNBUSDT"] == []
    assert len(engine.get_trade_history()) == 1

    engine.check_pending_orders("BNBUSDT", 97.0)

    assert "BNBUSDT" not in engine.positions
    assert len(engine.get_trade_history()) == 1


def test_same_side_market_order_is_ignored_when_position_exists():
    engine = PaperTradingEngine(Decimal("10000"))

    opened = engine.place_market_order("BTCUSDT", "BUY", 1.0, 100.0)
    ignored = engine.place_market_order("BTCUSDT", "BUY", 2.0, 105.0)

    position = engine.positions["BTCUSDT"]

    assert opened["status"] == "FILLED"
    assert ignored["status"] == "IGNORED"
    assert float(position.quantity) == 1.0
    assert float(position.entry_price) == 100.0
    assert len(engine.get_trade_history()) == 0