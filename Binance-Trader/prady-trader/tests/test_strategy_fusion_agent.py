from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from agents.strategy_fusion_agent import StrategyFusionAgent
from execution.strategies import StrategyFusionResult, StrategySignal


def test_strategy_fusion_agent_wraps_fused_result():
    fused_result = StrategyFusionResult(
        fused_score=38.5,
        direction="LONG",
        confidence=0.72,
        signals=[
            StrategySignal(
                name="news_velocity",
                direction="LONG",
                confidence=0.8,
                score=45.0,
                reasoning="News flow is improving",
                metadata={"articles": 12},
            )
        ],
        active_count=1,
        contributing_count=1,
        reasoning="Fused=+38.5 from 1 strategies",
    )

    with patch(
        "agents.strategy_fusion_agent.run_all_strategies",
        new=AsyncMock(return_value=fused_result),
    ):
        agent = StrategyFusionAgent()
        signal = asyncio.run(agent.analyze("BTCUSDT"))

    assert signal.agent_name == "strategy_fusion"
    assert signal.direction == "LONG"
    assert signal.confidence == 0.72
    assert signal.score == 38.5
    assert signal.metadata["active_count"] == 1
    assert signal.metadata["contributing_count"] == 1
    assert signal.metadata["signals"][0]["name"] == "news_velocity"