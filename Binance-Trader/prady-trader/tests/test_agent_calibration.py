from __future__ import annotations

import json

from council.calibration import (
    classify_forward_move,
    evaluate_agent_decisions,
    load_decision_records,
    recommend_agent_weights,
    recommend_score_thresholds,
)
from council.weight_manager import WeightManager


def test_classify_forward_move_respects_threshold():
    assert classify_forward_move(100.0, 102.0, move_threshold_pct=0.01) == "LONG"
    assert classify_forward_move(100.0, 98.0, move_threshold_pct=0.01) == "SHORT"
    assert classify_forward_move(100.0, 100.4, move_threshold_pct=0.01) == "NEUTRAL"


def test_evaluate_agent_decisions_scores_directional_signals():
    records = [
        {
            "symbol": "BTCUSDT",
            "timestamp": "2026-04-19T00:00:00+00:00",
            "weighted_score": 18.0,
            "confidence": 0.7,
            "agent_signals": {
                "oracle": {"direction": "LONG", "confidence": 0.8, "score": 70.0},
                "prophet": {"direction": "SHORT", "confidence": 0.7, "score": -55.0},
            },
        },
        {
            "symbol": "ETHUSDT",
            "timestamp": "2026-04-19T01:00:00+00:00",
            "weighted_score": -14.0,
            "confidence": 0.6,
            "agent_signals": {
                "oracle": {"direction": "SHORT", "confidence": 0.9, "score": -80.0},
                "prophet": {"direction": "LONG", "confidence": 0.6, "score": 35.0},
            },
        },
    ]

    price_map = {
        ("BTCUSDT", "2026-04-19T00:00:00+00:00"): (100.0, 102.5),
        ("ETHUSDT", "2026-04-19T01:00:00+00:00"): (200.0, 194.0),
    }

    def resolver(symbol, timestamp, lookahead_minutes):
        return price_map.get((symbol, timestamp.isoformat()))

    result = evaluate_agent_decisions(records, resolver, lookahead_minutes=60, move_threshold_pct=0.01)

    oracle = result["agent_stats"]["oracle"]
    prophet = result["agent_stats"]["prophet"]
    assert result["summary"]["scored_records"] == 2
    assert oracle["accuracy"] > 0.99
    assert prophet["accuracy"] < 0.01


def test_recommend_agent_weights_favors_more_accurate_agent():
    stats = {
        "oracle": {"samples": 16.0, "accuracy": 0.82, "avg_confidence": 0.72, "avg_abs_score": 68.0},
        "prophet": {"samples": 16.0, "accuracy": 0.31, "avg_confidence": 0.54, "avg_abs_score": 46.0},
    }
    result = recommend_agent_weights(stats, min_samples=8)
    weights = result["recommended_weights"]

    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["oracle"] > weights["prophet"]


def test_recommend_agent_weights_preserves_zero_accuracy_penalty():
    stats = {
        "strategy_fusion": {
            "samples": 16.0,
            "accuracy": 0.0,
            "avg_confidence": 0.30,
            "avg_abs_score": 24.0,
        },
        "sentinel": {
            "samples": 16.0,
            "accuracy": 0.72,
            "avg_confidence": 0.31,
            "avg_abs_score": 31.0,
        },
    }

    result = recommend_agent_weights(stats, min_samples=8)
    weights = result["recommended_weights"]
    diagnostics = result["diagnostics"]

    assert diagnostics["strategy_fusion"]["accuracy"] == 0.0
    assert diagnostics["strategy_fusion"]["raw_weight"] == 0.0
    assert weights["strategy_fusion"] == 0.0
    assert weights["strategy_fusion"] < weights["sentinel"]


def test_recommend_score_thresholds_returns_symmetric_thresholds():
    outcomes = [
        {"weighted_score": 18.0, "outcome_direction": "LONG"},
        {"weighted_score": 22.0, "outcome_direction": "LONG"},
        {"weighted_score": -20.0, "outcome_direction": "SHORT"},
        {"weighted_score": 6.0, "outcome_direction": "LONG"},
    ]

    thresholds = recommend_score_thresholds(outcomes, min_threshold=8, max_threshold=18)
    assert thresholds["long"] >= 8
    assert thresholds["short"] == -thresholds["long"]


def test_recommend_score_thresholds_soft_caps_small_samples():
    outcomes = [
        {"weighted_score": 18.0, "outcome_direction": "LONG"},
        {"weighted_score": 19.0, "outcome_direction": "LONG"},
        {"weighted_score": 21.0, "outcome_direction": "LONG"},
        {"weighted_score": -20.0, "outcome_direction": "SHORT"},
    ]

    thresholds = recommend_score_thresholds(
        outcomes,
        min_threshold=12,
        max_threshold=20,
        soft_cap_threshold=10,
        soft_cap_min_samples=12,
    )

    assert thresholds["raw_long"] >= 12
    assert thresholds["long"] == 10
    assert thresholds["short"] == -10


def test_load_decision_records_reads_recent_files(tmp_path):
    file_a = tmp_path / "decisions_20260418.jsonl"
    file_b = tmp_path / "decisions_20260419.jsonl"
    file_a.write_text(json.dumps({"symbol": "BTCUSDT", "timestamp": "2026-04-18T00:00:00+00:00"}) + "\n", encoding="utf-8")
    file_b.write_text(json.dumps({"symbol": "ETHUSDT", "timestamp": "2026-04-19T00:00:00+00:00"}) + "\n", encoding="utf-8")

    records = load_decision_records(tmp_path, max_files=1)
    assert len(records) == 1
    assert records[0]["symbol"] == "ETHUSDT"


def test_weight_manager_bootstraps_recommended_weights(tmp_path):
    bootstrap_file = tmp_path / "calibrated_agent_weights.json"
    bootstrap_file.write_text(
        json.dumps(
            {
                "recommended_weights": {
                    "oracle": 0.4,
                    "prophet": 0.08,
                    "arbiter": 0.14,
                    "sentinel": 0.1,
                    "oracle_extended": 0.1,
                    "strategy_fusion": 0.13,
                    "debater": 0.05,
                    "warden": 0.0,
                }
            }
        ),
        encoding="utf-8",
    )

    manager = WeightManager(bootstrap_file=bootstrap_file)
    weights = manager.weights

    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["oracle"] > weights["prophet"]


def test_weight_manager_preserves_zero_bootstrap_weight(tmp_path):
    bootstrap_file = tmp_path / "calibrated_agent_weights.json"
    bootstrap_file.write_text(
        json.dumps(
            {
                "recommended_weights": {
                    "oracle": 0.5,
                    "prophet": 0.2,
                    "arbiter": 0.1,
                    "sentinel": 0.1,
                    "oracle_extended": 0.05,
                    "strategy_fusion": 0.0,
                    "debater": 0.03,
                    "warden": 0.02,
                }
            }
        ),
        encoding="utf-8",
    )

    manager = WeightManager(bootstrap_file=bootstrap_file)
    weights = manager.weights

    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["strategy_fusion"] == 0.0