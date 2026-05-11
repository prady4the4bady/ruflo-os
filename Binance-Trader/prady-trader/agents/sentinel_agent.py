"""
PRADY TRADER — Sentinel Agent (weight: 0.15).
Risk-scoring agent: funding rate, open interest, order-book imbalance,
fear-and-greed, long/short ratio, VADER NLP multi-source news sentiment
→ veto-capable risk score.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, List

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from agents.base_agent import BaseAgent, AgentSignal
from config.constants import (
    AGENT_WEIGHTS,
    FEAR_GREED_EXTREME_FEAR,
    FEAR_GREED_EXTREME_GREED,
    FUNDING_RATE_CROWDED_LONG,
    FUNDING_RATE_CROWDED_SHORT,
    LONG_SHORT_RATIO_BEAR,
    LONG_SHORT_RATIO_BULL,
)
from data.binance_client import get_binance_client
from data.orderflow import analyze_order_flow
from data.orderbook_feed import get_orderbook_feed
from data.sentiment_feeds import async_fetch_fear_greed
from data.free_apis import async_fetch_all_news

logger = logging.getLogger("prady.agents.sentinel")

# VADER — initialise once (thread-safe, read-only after init)
_vader = SentimentIntensityAnalyzer()

# Source reliability weights for weighted VADER averaging
_SOURCE_WEIGHTS: Dict[str, float] = {
    "RSS": 0.15,
    "Messari": 0.15,
    "NewsAPI": 0.25,
    "NewsData": 0.25,
    "CryptoCompare": 0.20,
    "YahooFinance": 0.15,
}


class SentinelAgent(BaseAgent):
    """
    Risk sentinel — monitors market microstructure and sentiment.
    Uses VADER NLP on 6 news sources for sentiment scoring.
    Can issue risk warnings that reduce council confidence.
    """

    def __init__(self):
        super().__init__(name="sentinel", weight=AGENT_WEIGHTS["sentinel"])

    # ------------------------------------------------------------------
    # VADER multi-source news sentiment
    # ------------------------------------------------------------------
    async def _aggregate_news_sentiment(self) -> Dict[str, Any]:
        """Fetch news from the shared free-data sources, run VADER on each article, return
        weighted sentiment score in [-1, 1] + per-source breakdown."""
        try:
            articles = await async_fetch_all_news()
        except Exception as exc:
            logger.warning("News fetch failed: %s", exc)
            return {"score": 0.0, "article_count": 0, "per_source": {}}

        if not articles:
            return {"score": 0.0, "article_count": 0, "per_source": {}}

        # Group articles by provider and compute per-article VADER compound
        source_scores: Dict[str, List[float]] = {}
        for art in articles:
            provider = art.get("_provider", "RSS")
            text = art.get("title", "")
            desc = art.get("description") or art.get("body") or ""
            if desc:
                text = f"{text}. {desc}"
            if not text.strip():
                continue
            compound = _vader.polarity_scores(text)["compound"]
            source_scores.setdefault(provider, []).append(compound)

        # Per-source average
        per_source: Dict[str, float] = {}
        for src, scores in source_scores.items():
            per_source[src] = sum(scores) / len(scores) if scores else 0.0

        # Weighted fusion across sources
        weighted_sum = 0.0
        weight_total = 0.0
        for src, avg in per_source.items():
            w = _SOURCE_WEIGHTS.get(src, 0.10)
            weighted_sum += avg * w
            weight_total += w

        fused = weighted_sum / weight_total if weight_total > 0 else 0.0

        total_articles = sum(len(v) for v in source_scores.values())
        return {
            "score": round(fused, 4),
            "article_count": total_articles,
            "per_source": per_source,
        }

    async def analyze(self, symbol: str) -> AgentSignal:
        client = get_binance_client()
        ob_feed = get_orderbook_feed()

        risk_components: Dict[str, float] = {}
        orderflow_metrics = None

        # 1. Funding rate
        try:
            funding_data = client.get_funding_rate(symbol)
            rate = Decimal(str(funding_data[0]["fundingRate"])) if funding_data else Decimal(0)
            if rate > FUNDING_RATE_CROWDED_LONG:
                risk_components["funding"] = -30.0  # crowded long → bearish risk
            elif rate < FUNDING_RATE_CROWDED_SHORT:
                risk_components["funding"] = 30.0   # crowded short → bullish risk
            else:
                risk_components["funding"] = 0.0
        except Exception:
            risk_components["funding"] = 0.0

        # 2. Open interest change (positive = rising, may indicate overleveraging)
        try:
            oi_data = client.get_open_interest(symbol)
            oi_val = float(oi_data.get("openInterest", 0))
            risk_components["open_interest"] = 0.0  # neutral baseline
        except Exception:
            risk_components["open_interest"] = 0.0

        # 3. Long/short ratio
        try:
            ls_data = client.get_long_short_ratio(symbol)
            ls_val = Decimal(str(ls_data[0]["longShortRatio"])) if ls_data else Decimal(1)
            if ls_val > LONG_SHORT_RATIO_BEAR:
                risk_components["ls_ratio"] = -20.0  # too many longs
            elif ls_val < LONG_SHORT_RATIO_BULL:
                risk_components["ls_ratio"] = 20.0   # too many shorts
            else:
                risk_components["ls_ratio"] = 0.0
        except Exception:
            risk_components["ls_ratio"] = 0.0

        # 4. Order book imbalance
        snapshot = ob_feed.get_snapshot(symbol)
        if snapshot:
            orderflow_metrics = analyze_order_flow(snapshot)
            risk_components["orderflow"] = round(orderflow_metrics.score * 0.55, 1)
        else:
            risk_components["orderflow"] = 0.0

        # 5. Fear & Greed index + 6. VADER news sentiment — run in parallel
        fng_result, news_sentiment = await asyncio.gather(
            async_fetch_fear_greed(),
            self._aggregate_news_sentiment(),
        )
        fng = fng_result

        # Fear & Greed component
        if fng <= FEAR_GREED_EXTREME_FEAR:
            risk_components["fear_greed"] = 15.0   # contrarian — extreme fear is bullish signal
        elif fng >= FEAR_GREED_EXTREME_GREED:
            risk_components["fear_greed"] = -15.0  # extreme greed is bearish signal
        else:
            risk_components["fear_greed"] = 0.0

        # 6. VADER multi-source news sentiment [-1..1] → risk score [-25..25]
        vader_score = news_sentiment["score"]
        news_risk = round(vader_score * 25.0, 1)  # scale to ±25
        risk_components["news_vader"] = news_risk

        # Aggregate
        total_score = sum(risk_components.values())
        total_score = max(-100.0, min(100.0, total_score))

        if total_score > 20:
            direction = "LONG"
        elif total_score < -20:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        confidence = min(abs(total_score) / 100.0, 1.0)

        parts = [f"{k}={v:+.0f}" for k, v in risk_components.items()]
        src_details = ", ".join(
            f"{s}={v:+.3f}" for s, v in news_sentiment.get("per_source", {}).items()
        )
        orderflow_summary = ""
        if orderflow_metrics is not None:
            orderflow_summary = (
                f" OrderFlow={orderflow_metrics.direction}"
                f" score={orderflow_metrics.score:+.1f}"
                f" micro={orderflow_metrics.microprice_delta_bps:+.2f}bps"
                f" spread={orderflow_metrics.spread_bps:.2f}bps."
            )
        reasoning = (
            f"Risk score {total_score:+.1f}. "
            f"FnG={fng}. VADER={vader_score:+.3f} "
            f"({news_sentiment['article_count']} articles: {src_details}). "
            f"Components: {', '.join(parts)}."
            f"{orderflow_summary}"
        )

        return AgentSignal(
            agent_name=self.name,
            direction=direction,
            confidence=confidence,
            score=total_score,
            reasoning=reasoning,
            metadata={
                "risk_components": risk_components,
                "fear_greed": fng,
                "vader_sentiment": news_sentiment,
                "orderflow": orderflow_metrics.to_dict() if orderflow_metrics is not None else {},
            },
        )
