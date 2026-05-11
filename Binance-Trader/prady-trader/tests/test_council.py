"""
PRADY TRADER — Unit tests for council voting logic.
Tests weighted scoring, confidence, thresholds, veto, and weight manager.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents.base_agent import AgentSignal
from config.constants import AGENT_WEIGHTS, COUNCIL_LONG_THRESHOLD, COUNCIL_SHORT_THRESHOLD
from council.voting import (
    CouncilDecision,
    compute_weighted_score,
    compute_confidence,
    compute_decision_confidence,
    vote,
)
from council.path_policy import CouncilPathPolicyManager
from council.weight_manager import WeightManager


def make_signal(name: str, direction: str, conf: float, score: float) -> AgentSignal:
    """Helper to build an AgentSignal quickly."""
    return AgentSignal(
        agent_name=name,
        direction=direction,
        confidence=conf,
        score=score,
        reasoning=f"Test {name} signal",
    )


class TestComputeWeightedScore(unittest.TestCase):
    """Tests for compute_weighted_score()."""

    def test_all_bullish(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.9, 80),
            "prophet": make_signal("prophet", "LONG", 0.8, 70),
            "arbiter": make_signal("arbiter", "LONG", 0.7, 60),
        }
        weights = {"oracle": 0.5, "prophet": 0.3, "arbiter": 0.2}
        score = compute_weighted_score(signals, weights)
        expected = (80 * 0.5 + 70 * 0.3 + 60 * 0.2) / (0.5 + 0.3 + 0.2)
        self.assertAlmostEqual(score, expected, places=2)

    def test_mixed_signals(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.9, 80),
            "sentinel": make_signal("sentinel", "SHORT", 0.8, -60),
        }
        weights = {"oracle": 0.5, "sentinel": 0.5}
        score = compute_weighted_score(signals, weights)
        expected = (80 * 0.5 + (-60) * 0.5) / 1.0
        self.assertAlmostEqual(score, expected, places=2)

    def test_zero_weights(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.9, 80),
        }
        weights = {"oracle": 0.0}
        score = compute_weighted_score(signals, weights)
        self.assertEqual(score, 0.0)

    def test_missing_weight(self):
        signals = {
            "unknown": make_signal("unknown", "LONG", 0.9, 80),
        }
        weights = {"oracle": 0.5}
        score = compute_weighted_score(signals, weights)
        self.assertEqual(score, 0.0)


class TestComputeConfidence(unittest.TestCase):
    """Tests for compute_confidence()."""

    def test_high_confidence(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.9, 80),
            "prophet": make_signal("prophet", "LONG", 0.8, 70),
        }
        weights = {"oracle": 0.6, "prophet": 0.4}
        conf = compute_confidence(signals, weights)
        expected = (0.9 * 0.6 + 0.8 * 0.4) / 1.0
        self.assertAlmostEqual(conf, expected, places=4)

    def test_zero_confidence(self):
        signals = {
            "oracle": make_signal("oracle", "NEUTRAL", 0.0, 0),
        }
        weights = {"oracle": 0.5}
        conf = compute_confidence(signals, weights)
        self.assertEqual(conf, 0.0)


class TestDecisionConfidence(unittest.TestCase):
    """Tests for score-aware council confidence."""

    def test_score_strength_can_raise_decision_confidence(self):
        conf = compute_decision_confidence(0.24, 18.0)
        self.assertAlmostEqual(conf, 1.0, places=4)


class TestVote(unittest.TestCase):
    """Tests for the vote() function."""

    def setUp(self):
        self.wm = WeightManager(bootstrap_enabled=False)

    def test_strong_long_signal(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.95, 90),
            "prophet": make_signal("prophet", "LONG", 0.90, 85),
            "arbiter": make_signal("arbiter", "LONG", 0.80, 75),
            "sentinel": make_signal("sentinel", "LONG", 0.85, 70),
            "debater": make_signal("debater", "LONG", 0.70, 65),
        }
        decision = vote(signals, self.wm)
        self.assertEqual(decision.action, "LONG")
        self.assertTrue(decision.should_trade)
        self.assertGreater(decision.weighted_score, 0)

    def test_strong_short_signal(self):
        signals = {
            "oracle": make_signal("oracle", "SHORT", 0.95, -90),
            "prophet": make_signal("prophet", "SHORT", 0.90, -85),
            "arbiter": make_signal("arbiter", "SHORT", 0.80, -75),
            "sentinel": make_signal("sentinel", "SHORT", 0.85, -70),
            "debater": make_signal("debater", "SHORT", 0.70, -65),
        }
        decision = vote(signals, self.wm)
        self.assertEqual(decision.action, "SHORT")
        self.assertTrue(decision.should_trade)

    def test_mixed_signals_hold(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.6, 30),
            "prophet": make_signal("prophet", "SHORT", 0.5, -20),
            "arbiter": make_signal("arbiter", "NEUTRAL", 0.3, 5),
            "sentinel": make_signal("sentinel", "NEUTRAL", 0.4, -10),
            "debater": make_signal("debater", "LONG", 0.4, 15),
        }
        decision = vote(signals, self.wm)
        self.assertEqual(decision.action, "HOLD")
        self.assertFalse(decision.should_trade)

    def test_veto_overrides_long(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.95, 90),
            "prophet": make_signal("prophet", "LONG", 0.90, 85),
            "arbiter": make_signal("arbiter", "LONG", 0.80, 75),
            "sentinel": make_signal("sentinel", "LONG", 0.85, 70),
            "debater": make_signal("debater", "LONG", 0.70, 65),
        }
        decision = vote(signals, self.wm, veto=True, veto_reason="Daily loss limit reached")
        self.assertEqual(decision.action, "HOLD")
        self.assertFalse(decision.should_trade)
        self.assertTrue(decision.veto)
        self.assertIn("VETOED", decision.reasoning)

    def test_decision_has_reasoning(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.9, 80),
        }
        decision = vote(signals, self.wm)
        self.assertIsInstance(decision.reasoning, str)
        self.assertTrue(len(decision.reasoning) > 0)

    def test_score_strength_can_unlock_trade_confidence(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.35, 28),
            "strategy_fusion": make_signal("strategy_fusion", "LONG", 0.30, 42),
        }
        decision = vote(signals, self.wm)
        self.assertEqual(decision.action, "LONG")
        self.assertGreaterEqual(decision.confidence, 0.75)

    def test_vote_uses_bootstrapped_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bootstrap_path = Path(temp_dir) / "calibrated_agent_weights.json"
            bootstrap_path.write_text(
                json.dumps(
                    {
                        "recommended_weights": AGENT_WEIGHTS,
                        "recommended_thresholds": {"long": 8, "short": -8},
                    }
                ),
                encoding="utf-8",
            )
            wm = WeightManager(bootstrap_file=bootstrap_path)
            decision = vote({"oracle": make_signal("oracle", "LONG", 0.3, 10)}, wm)

        self.assertEqual(decision.action, "LONG")

    def test_vote_respects_weight_overrides(self):
        signals = {
            "oracle": make_signal("oracle", "LONG", 0.6, 30),
            "prophet": make_signal("prophet", "SHORT", 0.9, -90),
        }

        default_decision = vote(signals, self.wm)
        overridden = vote(
            signals,
            self.wm,
            weight_overrides={
                **self.wm.weights,
                "oracle": 1.0,
                "prophet": 0.0,
                "arbiter": 0.0,
                "sentinel": 0.0,
                "oracle_extended": 0.0,
                "strategy_fusion": 0.0,
                "debater": 0.0,
                "warden": 0.0,
            },
        )

        self.assertNotEqual(default_decision.action, overridden.action)
        self.assertEqual(overridden.action, "LONG")

    def test_vote_boosts_strategy_fusion_on_confirmed_local_setup(self):
        wm = WeightManager(bootstrap_enabled=False)
        wm._weights = {
            "oracle": 0.34,
            "sentinel": 0.33,
            "strategy_fusion": 0.33,
            "prophet": 0.0,
            "arbiter": 0.0,
            "oracle_extended": 0.0,
            "debater": 0.0,
            "warden": 0.0,
        }

        strategy_fusion = make_signal("strategy_fusion", "LONG", 0.74, 30)
        strategy_fusion.metadata = {
            "signals": [
                {
                    "name": "liquidity_sweep_avwap",
                    "direction": "LONG",
                    "confidence": 0.78,
                    "score": 52.0,
                }
            ]
        }
        signals = {
            "oracle": make_signal("oracle", "SHORT", 0.56, -10),
            "sentinel": make_signal("sentinel", "NEUTRAL", 0.20, 0),
            "strategy_fusion": strategy_fusion,
        }

        decision = vote(signals, wm)

        self.assertEqual(decision.action, "LONG")
        self.assertGreaterEqual(decision.weighted_score, 8.0)
        self.assertIn("local-setup boost", decision.reasoning)

    def test_vote_boosts_strategy_fusion_on_cvd_local_setup(self):
        wm = WeightManager(bootstrap_enabled=False)
        wm._weights = {
            "oracle": 0.34,
            "sentinel": 0.33,
            "strategy_fusion": 0.33,
            "prophet": 0.0,
            "arbiter": 0.0,
            "oracle_extended": 0.0,
            "debater": 0.0,
            "warden": 0.0,
        }

        strategy_fusion = make_signal("strategy_fusion", "LONG", 0.73, 48)
        strategy_fusion.metadata = {
            "signals": [
                {
                    "name": "cumulative_volume_delta_reversal",
                    "direction": "LONG",
                    "confidence": 0.74,
                    "score": 48.0,
                }
            ]
        }
        signals = {
            "oracle": make_signal("oracle", "SHORT", 0.56, -10),
            "sentinel": make_signal("sentinel", "NEUTRAL", 0.20, 0),
            "strategy_fusion": strategy_fusion,
        }

        decision = vote(signals, wm)

        self.assertEqual(decision.action, "LONG")
        self.assertGreaterEqual(decision.weighted_score, 8.0)
        self.assertIn("local-setup boost", decision.reasoning)

    def test_vote_boosts_strategy_fusion_on_core_intelligence_alignment(self):
        wm = WeightManager(bootstrap_enabled=False)
        wm._weights = {
            "oracle": 0.34,
            "sentinel": 0.33,
            "strategy_fusion": 0.33,
            "prophet": 0.0,
            "arbiter": 0.0,
            "oracle_extended": 0.0,
            "debater": 0.0,
            "warden": 0.0,
        }

        strategy_fusion = make_signal("strategy_fusion", "LONG", 0.71, 30)
        strategy_fusion.metadata = {
            "signals": [
                {
                    "name": "core_financial_strength",
                    "direction": "LONG",
                    "confidence": 0.74,
                    "score": 32.0,
                },
                {
                    "name": "advanced_quant_analysis",
                    "direction": "LONG",
                    "confidence": 0.72,
                    "score": 28.0,
                },
                {
                    "name": "dual_mode_financial_intelligence",
                    "direction": "LONG",
                    "confidence": 0.76,
                    "score": 35.0,
                },
            ]
        }
        signals = {
            "oracle": make_signal("oracle", "SHORT", 0.56, -10),
            "sentinel": make_signal("sentinel", "NEUTRAL", 0.20, 0),
            "strategy_fusion": strategy_fusion,
        }

        decision = vote(signals, wm)

        self.assertEqual(decision.action, "LONG")
        self.assertGreaterEqual(decision.weighted_score, 10.0)
        self.assertIn("core-intelligence boost", decision.reasoning)


class TestCouncilDecision(unittest.TestCase):
    """Tests for CouncilDecision dataclass."""

    def test_should_trade_long(self):
        d = CouncilDecision(action="LONG", weighted_score=70, confidence=0.9)
        self.assertTrue(d.should_trade)

    def test_should_trade_short(self):
        d = CouncilDecision(action="SHORT", weighted_score=-70, confidence=0.9)
        self.assertTrue(d.should_trade)

    def test_should_not_trade_hold(self):
        d = CouncilDecision(action="HOLD", weighted_score=10, confidence=0.5)
        self.assertFalse(d.should_trade)

    def test_should_not_trade_vetoed(self):
        d = CouncilDecision(action="LONG", weighted_score=80, confidence=0.9, veto=True)
        self.assertFalse(d.should_trade)


class TestCouncilPathPolicy(unittest.TestCase):
    def test_path_policy_adjusts_weights_and_blocks_coalition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "council_trade_audit.json"
            audit_path.write_text(
                json.dumps(
                    {
                        "recommended_path_controls": {
                            "disabled_agents": ["oracle"],
                            "penalized_agents": [{"agent": "debater", "multiplier": 0.5}],
                            "blocked_coalitions": [
                                {
                                    "supporting_agents": ["debater", "sentinel"],
                                    "reason": "negative_coalition_expectancy",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            policy = CouncilPathPolicyManager(audit_file=audit_path)
            adjusted = policy.adjust_weights(AGENT_WEIGHTS)
            decision = CouncilDecision(
                action="LONG",
                weighted_score=14,
                confidence=0.8,
                agent_signals={
                    "sentinel": make_signal("sentinel", "LONG", 0.8, 60),
                    "debater": make_signal("debater", "LONG", 0.7, 20),
                    "oracle": make_signal("oracle", "SHORT", 0.7, -40),
                },
                reasoning="Score 14 >= 12 threshold → LONG",
            )
            blocked = policy.enforce_decision(decision)

        self.assertEqual(adjusted["oracle"], 0.0)
        self.assertLess(adjusted["debater"], AGENT_WEIGHTS["debater"])
        self.assertEqual(blocked.action, "HOLD")
        self.assertIn("Audit policy blocked coalition", blocked.reasoning)


class TestWeightManager(unittest.TestCase):
    """Tests for WeightManager."""

    def setUp(self):
        self.wm = WeightManager(bootstrap_enabled=False)

    def test_initial_weights_sum_to_one(self):
        total = sum(self.wm.weights.values())
        self.assertAlmostEqual(total, 1.0, places=4)

    def test_record_outcome(self):
        self.wm.record_outcome("oracle", True)
        self.wm.record_outcome("oracle", True)
        self.wm.record_outcome("oracle", False)
        acc = self.wm.get_accuracy("oracle")
        # < 5 samples → returns 0.5 default
        self.assertAlmostEqual(acc, 0.5, places=4)

    def test_accuracy_with_enough_samples(self):
        for _ in range(8):
            self.wm.record_outcome("oracle", True)
        for _ in range(2):
            self.wm.record_outcome("oracle", False)
        acc = self.wm.get_accuracy("oracle")
        self.assertAlmostEqual(acc, 0.8, places=4)

    def test_update_weights_preserves_sum(self):
        for _ in range(10):
            self.wm.record_outcome("oracle", True)
            self.wm.record_outcome("prophet", True)
            self.wm.record_outcome("arbiter", False)
            self.wm.record_outcome("sentinel", True)
            self.wm.record_outcome("debater", False)
        self.wm.update_weights()
        total = sum(self.wm.weights.values())
        self.assertAlmostEqual(total, 1.0, places=4)

    def test_weights_returns_copy(self):
        w1 = self.wm.weights
        w2 = self.wm.weights
        self.assertIsNot(w1, w2)

    def test_unknown_agent_ignored(self):
        self.wm.record_outcome("nonexistent", True)
        acc = self.wm.get_accuracy("nonexistent")
        self.assertAlmostEqual(acc, 0.5, places=4)

    def test_get_report(self):
        report = self.wm.get_report()
        self.assertIn("oracle", report)
        self.assertIn("weight", report["oracle"])
        self.assertIn("accuracy", report["oracle"])
        self.assertIn("samples", report["oracle"])

    def test_bootstrap_thresholds_are_capped_in_paper_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bootstrap_path = Path(temp_dir) / "calibrated_agent_weights.json"
            bootstrap_path.write_text(
                json.dumps(
                    {
                        "recommended_weights": AGENT_WEIGHTS,
                        "recommended_thresholds": {"long": 16, "short": -16},
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "council.weight_manager.get_settings",
                return_value=SimpleNamespace(is_paper=True, is_testnet=False),
            ):
                wm = WeightManager(bootstrap_file=bootstrap_path)

        self.assertEqual(wm.long_threshold, 10.0)
        self.assertEqual(wm.short_threshold, -10.0)

    def test_bootstrap_thresholds_remain_uncapped_in_live_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bootstrap_path = Path(temp_dir) / "calibrated_agent_weights.json"
            bootstrap_path.write_text(
                json.dumps(
                    {
                        "recommended_weights": AGENT_WEIGHTS,
                        "recommended_thresholds": {"long": 16, "short": -16},
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "council.weight_manager.get_settings",
                return_value=SimpleNamespace(is_paper=False, is_testnet=False),
            ):
                wm = WeightManager(bootstrap_file=bootstrap_path)

        self.assertEqual(wm.long_threshold, 16.0)
        self.assertEqual(wm.short_threshold, -16.0)


if __name__ == "__main__":
    unittest.main()
