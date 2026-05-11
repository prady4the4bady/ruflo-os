"""
PRADY TRADER — Base agent ABC.
Every agent inherits from this and implements analyze().
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from config.mode_policy import get_mode_policy


@dataclass
class AgentSignal:
    """Standard output from every agent."""

    agent_name: str
    direction: str               # "LONG", "SHORT", or "NEUTRAL"
    confidence: float            # 0.0 – 1.0
    score: float                 # -100 to +100
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_bullish(self) -> bool:
        return self.direction == "LONG" and self.confidence > 0.5

    @property
    def is_bearish(self) -> bool:
        return self.direction == "SHORT" and self.confidence > 0.5


class BaseAgent(ABC):
    """Abstract base class for all AI agents."""

    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight
        self.logger = logging.getLogger(f"prady.agents.{name}")
        self._last_signal: Optional[AgentSignal] = None

    @abstractmethod
    async def analyze(self, symbol: str) -> AgentSignal:
        """
        Run the agent's analysis for the given symbol.
        Must return an AgentSignal.
        """
        ...

    @property
    def last_signal(self) -> Optional[AgentSignal]:
        return self._last_signal

    async def run(self, symbol: str) -> AgentSignal:
        """Run analysis with timing and error handling."""
        start = time.time()
        try:
            signal = await self.analyze(symbol)
            mode_policy = get_mode_policy()
            signal.metadata = dict(signal.metadata or {})
            signal.metadata.setdefault("runtime_mode", mode_policy["mode"])
            signal.metadata.setdefault("mode_objective", mode_policy["primary_goal"])
            signal.metadata.setdefault("execution_model", mode_policy["execution_model"])
            signal.metadata.setdefault("mode_context", mode_policy)
            self._last_signal = signal
            elapsed = time.time() - start
            self.logger.info(
                "%s → %s (conf=%.2f, score=%.1f) [%.2fs]",
                symbol, signal.direction, signal.confidence, signal.score, elapsed,
            )
            return signal
        except Exception as exc:
            elapsed = time.time() - start
            self.logger.exception("Agent %s failed for %s (%.2fs): %s", self.name, symbol, elapsed, exc)
            return AgentSignal(
                agent_name=self.name,
                direction="NEUTRAL",
                confidence=0.0,
                score=0.0,
                reasoning=f"Error: {exc}",
            )
