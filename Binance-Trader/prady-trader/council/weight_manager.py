"""
PRADY TRADER — Agent Weight Manager.
Dynamically adjusts agent weights based on recent prediction accuracy.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Dict, Optional

from config.constants import (
    AGENT_WEIGHTS,
    AGENT_WEIGHT_MIN,
    AGENT_WEIGHT_MAX,
    COUNCIL_LONG_THRESHOLD,
    COUNCIL_SHORT_THRESHOLD,
)
from config.settings import ROOT_DIR, get_settings

logger = logging.getLogger("prady.council.weight_manager")

HISTORY_WINDOW = 50
DEFAULT_WEIGHT_BOOTSTRAP_FILE = ROOT_DIR / "logs" / "calibrated_agent_weights.json"
PAPER_THRESHOLD_CAP = 10.0


def bounded_normalize_weights(
    raw_weights: Dict[str, float],
    *,
    min_weight: float = AGENT_WEIGHT_MIN,
    max_weight: float = AGENT_WEIGHT_MAX,
) -> Dict[str, float]:
    """Normalize raw weights while respecting the configured min/max bounds."""
    min_weight = max(0.0, float(min_weight))
    max_weight = max(min_weight, float(max_weight))
    positive = {
        name: max(0.0, float(raw_weights.get(name, 0.0)))
        for name in AGENT_WEIGHTS
    }
    if sum(positive.values()) <= 0:
        return AGENT_WEIGHTS.copy()

    remaining = positive.copy()
    fixed: Dict[str, float] = {}
    remaining_target = 1.0

    while remaining:
        total = sum(remaining.values())
        if total <= 0 or remaining_target <= 0:
            equal_share = remaining_target / max(len(remaining), 1)
            for name in list(remaining):
                fixed[name] = equal_share
                del remaining[name]
            break

        changed = False
        for name, value in list(remaining.items()):
            proposed = (value / total) * remaining_target
            if proposed < min_weight:
                fixed[name] = min_weight
                remaining_target -= min_weight
                del remaining[name]
                changed = True
            elif proposed > max_weight:
                fixed[name] = max_weight
                remaining_target -= max_weight
                del remaining[name]
                changed = True

        if not changed:
            for name, value in remaining.items():
                fixed[name] = (value / total) * remaining_target
            break

    delta = 1.0 - sum(fixed.values())
    if fixed and abs(delta) > 1e-9:
        anchor = max(fixed, key=fixed.get)
        fixed[anchor] = max(0.0, fixed[anchor] + delta)

    return {name: float(fixed.get(name, 0.0)) for name in AGENT_WEIGHTS}


class WeightManager:
    """
    Tracks per-agent prediction accuracy and adjusts voting weights.
    Weights stay in [AGENT_WEIGHT_MIN, AGENT_WEIGHT_MAX] and always sum to 1.0.
    """

    def __init__(
        self,
        bootstrap_file: Optional[str | Path] = None,
        *,
        bootstrap_enabled: bool = True,
    ):
        self._weights: Dict[str, float] = AGENT_WEIGHTS.copy()
        self._long_threshold = float(COUNCIL_LONG_THRESHOLD)
        self._short_threshold = float(COUNCIL_SHORT_THRESHOLD)
        self._history: Dict[str, deque] = {
            name: deque(maxlen=HISTORY_WINDOW)
            for name in AGENT_WEIGHTS
        }
        self._bootstrap_file = Path(bootstrap_file) if bootstrap_file else DEFAULT_WEIGHT_BOOTSTRAP_FILE
        if bootstrap_enabled:
            self._load_bootstrap_weights()

    def _apply_mode_threshold_policy(self) -> None:
        """Keep paper/testnet validation modes aggressive enough to exercise the system."""
        try:
            settings = get_settings()
        except Exception:
            return

        if getattr(settings, "is_paper", False) or getattr(settings, "is_testnet", False):
            self._long_threshold = min(self._long_threshold, PAPER_THRESHOLD_CAP)
            self._short_threshold = max(self._short_threshold, -PAPER_THRESHOLD_CAP)

    def _load_bootstrap_weights(self) -> None:
        if not self._bootstrap_file.exists():
            return

        try:
            payload = json.loads(self._bootstrap_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return

            recommended_weights = payload.get("recommended_weights")
            candidate = recommended_weights if isinstance(recommended_weights, dict) else (payload.get("weights") or payload)
            if not isinstance(candidate, dict):
                return

            raw_weights: Dict[str, float] = {}
            for name, default in AGENT_WEIGHTS.items():
                value = candidate.get(name, default)
                raw_weights[name] = float(value)

            bootstrap_min_weight = 0.0 if isinstance(recommended_weights, dict) else AGENT_WEIGHT_MIN
            self._weights = bounded_normalize_weights(raw_weights, min_weight=bootstrap_min_weight)

            threshold_payload = payload.get("recommended_thresholds")
            if isinstance(threshold_payload, dict):
                long_value = float(threshold_payload.get("long", self._long_threshold))
                short_value = float(threshold_payload.get("short", self._short_threshold))
                if long_value > 0 and short_value < 0:
                    self._long_threshold = long_value
                    self._short_threshold = short_value

            self._apply_mode_threshold_policy()

            logger.info("Loaded calibrated weights from %s", self._bootstrap_file)
        except Exception as exc:
            logger.warning("Failed to load calibrated weights from %s: %s", self._bootstrap_file, exc)

    @property
    def weights(self) -> Dict[str, float]:
        return self._weights.copy()

    @property
    def long_threshold(self) -> float:
        return self._long_threshold

    @property
    def short_threshold(self) -> float:
        return self._short_threshold

    def record_outcome(self, agent_name: str, correct: bool):
        """Record whether an agent's prediction was correct."""
        if agent_name not in self._history:
            return
        self._history[agent_name].append(1.0 if correct else 0.0)

    def get_accuracy(self, agent_name: str) -> float:
        """Get recent accuracy for an agent."""
        hist = self._history.get(agent_name)
        if not hist or len(hist) < 5:
            return 0.5  # neutral default
        return sum(hist) / len(hist)

    def update_weights(self):
        """
        Recalculate agent weights based on recent accuracy.
        Uses softmax-like normalisation.
        """
        accuracies = {}
        for name in self._weights:
            accuracies[name] = self.get_accuracy(name)

        total_acc = sum(accuracies.values())
        if total_acc <= 0:
            return

        # Proportional allocation
        raw = {name: acc / total_acc for name, acc in accuracies.items()}

        self._weights = bounded_normalize_weights(raw)

        logger.info(
            "Weights updated: %s",
            {k: f"{v:.3f}" for k, v in self._weights.items()},
        )

    def get_report(self) -> Dict[str, Dict[str, float]]:
        """Return weight and accuracy report for all agents."""
        return {
            name: {
                "weight": self._weights.get(name, 0.0),
                "accuracy": self.get_accuracy(name),
                "samples": len(self._history.get(name, [])),
            }
            for name in AGENT_WEIGHTS
        }
