"""
PRADY TRADER — Oracle Agent (weight: 0.30).
Multi-timeframe technical analysis synthesiser.
Runs ALL indicators across all timeframes, produces composite score.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, AgentSignal
from config.constants import AGENT_WEIGHTS, EMA_PERIODS, TIMEFRAME_WEIGHTS
from data.data_store import get_data_store
from indicators.composite import compute_composite_score

logger = logging.getLogger("prady.agents.oracle")


class OracleAgent(BaseAgent):
    """
    Multi-timeframe technical oracle.
    Weights: 0.30 of council vote.
    """

    def __init__(self):
        super().__init__(name="oracle", weight=AGENT_WEIGHTS["oracle"])

    async def analyze(self, symbol: str) -> AgentSignal:
        store = get_data_store()

        # Build per-timeframe DataFrames from the data store
        dataframes = {}
        for tf in TIMEFRAME_WEIGHTS:
            df = store.get_dataframe(symbol, tf)
            if not df.empty:
                dataframes[tf] = df

        composite = compute_composite_score(dataframes)

        score = composite["score"]
        direction_raw = composite["direction"]
        confidence = composite["confidence"]
        per_tf = composite.get("per_timeframe", {})

        if direction_raw == "LONG":
            direction = "LONG"
            final_score = score
        elif direction_raw == "SHORT":
            direction = "SHORT"
            final_score = -score
        else:
            direction = "NEUTRAL"
            final_score = 0.0

        tf_summary = "; ".join(
            f"{tf}={info.get('score', 0):.0f}" for tf, info in per_tf.items()
        )
        reasoning = (
            f"Composite {score:.1f}/100 ({direction_raw}). "
            f"Confidence {confidence:.2f}. "
            f"TF breakdown: [{tf_summary}]"
        )

        return AgentSignal(
            agent_name=self.name,
            direction=direction,
            confidence=confidence,
            score=final_score,
            reasoning=reasoning,
            metadata={
                "composite_score": score,
                "per_timeframe": per_tf,
            },
        )
