"""
PRADY TRADER — Council voting logic.
Aggregates agent signals into a final trading decision.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any

from agents.base_agent import AgentSignal
from config.constants import (
    COUNCIL_CONFIDENCE_SCALE,
    COUNCIL_LONG_THRESHOLD,
    COUNCIL_SHORT_THRESHOLD,
)
from council.weight_manager import WeightManager

logger = logging.getLogger("prady.council.voting")

LOCAL_SETUP_NAMES = {
    "liquidity_sweep_avwap",
    "failed_auction_delta",
    "cumulative_volume_delta_reversal",
}

CORE_INTELLIGENCE_NAMES = {
    "core_financial_strength",
    "advanced_quant_analysis",
    "dual_mode_financial_intelligence",
}


@dataclass
class CouncilDecision:
    """Final output of the council voting process."""

    action: str                    # "LONG", "SHORT", or "HOLD"
    weighted_score: float          # -100 to +100
    confidence: float              # 0.0 – 1.0
    agent_signals: Dict[str, AgentSignal] = field(default_factory=dict)
    veto: bool = False
    veto_reason: str = ""
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def should_trade(self) -> bool:
        return self.action in ("LONG", "SHORT") and not self.veto


def compute_weighted_score(
    signals: Dict[str, AgentSignal],
    weights: Dict[str, float],
) -> float:
    """Compute weighted score from agent signals using dynamic weights."""
    total_weight = 0.0
    weighted_sum = 0.0

    for name, signal in signals.items():
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        weighted_sum += signal.score * w
        total_weight += w

    if total_weight <= 0:
        return 0.0
    return weighted_sum / total_weight


def compute_confidence(
    signals: Dict[str, AgentSignal],
    weights: Dict[str, float],
) -> float:
    """Compute weighted average confidence."""
    total_weight = 0.0
    weighted_conf = 0.0

    for name, signal in signals.items():
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        weighted_conf += signal.confidence * w
        total_weight += w

    if total_weight <= 0:
        return 0.0
    return weighted_conf / total_weight


def compute_decision_confidence(weighted_confidence: float, weighted_score: float) -> float:
    """Blend raw agent confidence with consensus strength from the final score."""
    score_strength = min(abs(weighted_score) / COUNCIL_CONFIDENCE_SCALE, 1.0)
    return max(weighted_confidence, score_strength)


def _build_effective_weights(
    signals: Dict[str, AgentSignal],
    weights: Dict[str, float],
) -> tuple[Dict[str, float], Dict[str, Any]]:
    """Boost strategy_fusion in council voting when local setups or core intelligence align."""
    effective_weights = weights.copy()
    fusion_signal = signals.get("strategy_fusion")
    if not fusion_signal:
        return effective_weights, {}

    metadata = fusion_signal.metadata if isinstance(fusion_signal.metadata, dict) else {}
    nested_signals = metadata.get("signals") or []
    base_weight = effective_weights.get("strategy_fusion", 0.0)
    if base_weight <= 0:
        return effective_weights, {}

    boost_metadata: Dict[str, Any] = {}

    local_directionals = [
        nested for nested in nested_signals
        if isinstance(nested, dict)
        and nested.get("name") in LOCAL_SETUP_NAMES
        and nested.get("direction") in {"LONG", "SHORT"}
    ]
    if local_directionals:
        directions = {nested.get("direction") for nested in local_directionals}
        if len(directions) == 1 and fusion_signal.direction in {"LONG", "SHORT"}:
            aligned_direction = next(iter(directions))
            if aligned_direction == fusion_signal.direction:
                multiplier = 1.85 if len(local_directionals) == 1 else 2.15
                if abs(fusion_signal.score) >= 35 or fusion_signal.confidence >= 0.72:
                    multiplier += 0.2
                effective_weights["strategy_fusion"] *= multiplier
                boost_metadata["local_setup"] = {
                    "direction": aligned_direction,
                    "count": len(local_directionals),
                    "multiplier": round(multiplier, 2),
                }

    core_directionals = [
        nested for nested in nested_signals
        if isinstance(nested, dict)
        and nested.get("name") in CORE_INTELLIGENCE_NAMES
        and nested.get("direction") in {"LONG", "SHORT"}
    ]
    if len(core_directionals) >= 2:
        directions = {nested.get("direction") for nested in core_directionals}
        if len(directions) == 1 and fusion_signal.direction in {"LONG", "SHORT"}:
            aligned_direction = next(iter(directions))
            if aligned_direction == fusion_signal.direction:
                multiplier = 1.3 + (0.2 * min(len(core_directionals), 3))
                if abs(fusion_signal.score) >= 25 or fusion_signal.confidence >= 0.68:
                    multiplier += 0.1
                effective_weights["strategy_fusion"] *= multiplier
                boost_metadata["core_intelligence"] = {
                    "direction": aligned_direction,
                    "count": len(core_directionals),
                    "multiplier": round(multiplier, 2),
                }

    return effective_weights, boost_metadata


def vote(
    signals: Dict[str, AgentSignal],
    weight_manager: WeightManager,
    veto: bool = False,
    veto_reason: str = "",
    weight_overrides: Dict[str, float] | None = None,
) -> CouncilDecision:
    """
    Run the council vote.
    Returns a CouncilDecision with action, score, and confidence.
    """
    weights = dict(weight_overrides or weight_manager.weights)
    effective_weights, boost_metadata = _build_effective_weights(signals, weights)
    long_threshold = getattr(weight_manager, "long_threshold", COUNCIL_LONG_THRESHOLD)
    short_threshold = getattr(weight_manager, "short_threshold", COUNCIL_SHORT_THRESHOLD)
    weighted_score = compute_weighted_score(signals, effective_weights)
    weighted_confidence = compute_confidence(signals, effective_weights)
    confidence = compute_decision_confidence(weighted_confidence, weighted_score)

    if veto:
        action = "HOLD"
        reasoning = f"VETOED by Warden: {veto_reason}"
    elif weighted_score >= long_threshold:
        action = "LONG"
        reasoning = f"Score {weighted_score:.1f} >= {long_threshold:.0f} threshold → LONG"
    elif weighted_score <= short_threshold:
        action = "SHORT"
        reasoning = f"Score {weighted_score:.1f} <= {short_threshold:.0f} threshold → SHORT"
    else:
        action = "HOLD"
        reasoning = (
            f"Score {weighted_score:.1f} between "
            f"[{short_threshold:.0f}, {long_threshold:.0f}] → HOLD"
        )

    local_boost = boost_metadata.get("local_setup") if boost_metadata else None
    if local_boost:
        reasoning += (
            " | strategy_fusion local-setup boost "
            f"x{local_boost['multiplier']:.2f} ({local_boost['count']} aligned {local_boost['direction']})"
        )
    core_boost = boost_metadata.get("core_intelligence") if boost_metadata else None
    if core_boost:
        reasoning += (
            " | strategy_fusion core-intelligence boost "
            f"x{core_boost['multiplier']:.2f} ({core_boost['count']} aligned {core_boost['direction']})"
        )

    # Build per-agent summary
    agent_parts = []
    for name, signal in signals.items():
        w = effective_weights.get(name, 0.0)
        agent_parts.append(
            f"{name}({signal.direction} conf={signal.confidence:.2f} "
            f"score={signal.score:.1f} w={w:.2f})"
        )
    reasoning += " | Agents: " + ", ".join(agent_parts)

    decision = CouncilDecision(
        action=action,
        weighted_score=round(weighted_score, 2),
        confidence=round(confidence, 4),
        agent_signals=signals,
        veto=veto,
        veto_reason=veto_reason,
        reasoning=reasoning,
    )

    logger.info(
        "COUNCIL VOTE: %s (score=%.1f, conf=%.2f, veto=%s)",
        action, weighted_score, confidence, veto,
    )
    return decision
