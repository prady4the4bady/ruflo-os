from datetime import datetime, timezone
from unittest.mock import patch

from council.trade_audit import evaluate_council_trades, simulate_trade_path


def test_simulate_trade_path_hits_take_profit_for_long():
    result = simulate_trade_path(
        {
            "entry_price": 100.0,
            "future_price": 101.0,
            "bars": [{"high": 103.5, "low": 99.5, "close": 102.0}],
        },
        "LONG",
    )

    assert result["exit_reason"] == "take_profit"
    assert round(result["pnl_pct"], 6) == 3.0


def test_simulate_trade_path_uses_conservative_intrabar_collision():
    result = simulate_trade_path(
        {
            "entry_price": 100.0,
            "future_price": 100.0,
            "bars": [{"high": 103.5, "low": 97.5, "close": 101.0}],
        },
        "LONG",
    )

    assert result["exit_reason"] == "stop_loss_intrabar_collision"
    assert round(result["pnl_pct"], 6) == -2.0


def test_evaluate_council_trades_filters_to_executable_decisions():
    records = [
        {
            "symbol": "ETHUSDT",
            "timestamp": "2026-04-21T00:00:00+00:00",
            "action": "LONG",
            "confidence": 0.72,
            "weighted_score": 14.0,
        },
        {
            "symbol": "BTCUSDT",
            "timestamp": "2026-04-21T00:05:00+00:00",
            "action": "SHORT",
            "confidence": 0.40,
            "weighted_score": -15.0,
        },
        {
            "symbol": "BNBUSDT",
            "timestamp": "2026-04-21T00:10:00+00:00",
            "action": "HOLD",
            "confidence": 0.9,
            "weighted_score": 0.0,
        },
    ]

    def resolver(symbol: str, timestamp: datetime, lookahead_minutes: int):
        if symbol == "ETHUSDT":
            return {
                "entry_price": 100.0,
                "future_price": 103.0,
                "bars": [{"high": 103.5, "low": 99.5, "close": 103.0}],
            }
        return None

    with patch("council.symbol_selection.has_trained_model_coverage", side_effect=lambda symbol: symbol == "ETHUSDT"):
        result = evaluate_council_trades(
            records,
            resolver,
            lookahead_minutes=60,
            configured_symbols=["ETHUSDT", "BTCUSDT"],
            selection_min_trades=1,
        )

    assert result["summary"]["directional_records"] == 2
    assert result["summary"]["simulated_trades"] == 1
    assert result["summary"]["skipped_low_confidence"] == 1
    assert result["eligible_symbols"] == ["ETHUSDT"]
    assert result["symbol_stats"]["ETHUSDT"]["profit_factor"] == float("inf")


def test_evaluate_council_trades_adds_agent_and_coalition_attribution():
    records = []
    for minute in range(4):
        records.append(
            {
                "symbol": "BTCUSDT",
                "timestamp": f"2026-04-21T00:0{minute}:00+00:00",
                "action": "LONG",
                "confidence": 0.74,
                "weighted_score": 14.0,
                "agent_signals": {
                    "oracle": {"direction": "LONG", "confidence": 0.9, "score": 70.0},
                    "debater": {"direction": "LONG", "confidence": 0.7, "score": 20.0},
                    "prophet": {"direction": "SHORT", "confidence": 0.6, "score": -25.0},
                },
            }
        )

    def resolver(symbol: str, timestamp: datetime, lookahead_minutes: int):
        return {
            "entry_price": 100.0,
            "future_price": 99.0,
            "bars": [{"high": 101.0, "low": 98.5, "close": 99.0}],
        }

    with patch("council.symbol_selection.has_trained_model_coverage", return_value=True):
        result = evaluate_council_trades(records, resolver, configured_symbols=["BTCUSDT"])

    supporting = result["agent_attribution"]["supporting"]
    assert supporting["oracle"]["trades"] == 4
    assert supporting["oracle"]["losses"] == 4
    assert supporting["debater"]["expectancy_pct"] < 0.0

    coalitions = result["coalition_attribution"]
    assert coalitions[0]["supporting_agents"] == ["debater", "oracle"]
    assert coalitions[0]["trades"] == 4

    controls = result["recommended_path_controls"]
    penalized_agents = {item["agent"]: item for item in controls["penalized_agents"]}
    assert penalized_agents["oracle"]["multiplier"] <= 0.5
    assert any(item["supporting_agents"] == ["debater", "oracle"] for item in controls["blocked_coalitions"])
