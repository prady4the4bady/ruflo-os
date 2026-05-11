"""
PRADY TRADER — Strategy Fusion Agent.
Wraps the execution/strategies fusion module so it can participate in council voting.
"""

from __future__ import annotations

import asyncio

from agents.base_agent import BaseAgent, AgentSignal
from config.constants import AGENT_WEIGHTS
from execution.strategies import run_all_strategies


class StrategyFusionAgent(BaseAgent):
    """Expose the weighted strategy fusion module as a first-class council signal."""

    def __init__(self):
        super().__init__(name="strategy_fusion", weight=AGENT_WEIGHTS["strategy_fusion"])

    async def analyze(self, symbol: str) -> AgentSignal:
        fused = await asyncio.wait_for(run_all_strategies(symbol), timeout=25.0)
        metadata = {
            "active_count": fused.active_count,
            "contributing_count": fused.contributing_count,
            "signals": [
                {
                    "name": signal.name,
                    "direction": signal.direction,
                    "confidence": signal.confidence,
                    "score": signal.score,
                    "reasoning": signal.reasoning,
                    "metadata": dict(signal.metadata or {}),
                }
                for signal in fused.signals
            ],
        }
        return AgentSignal(
            agent_name=self.name,
            direction=fused.direction,
            confidence=round(fused.confidence, 4),
            score=round(fused.fused_score, 2),
            reasoning=fused.reasoning,
            metadata=metadata,
        )