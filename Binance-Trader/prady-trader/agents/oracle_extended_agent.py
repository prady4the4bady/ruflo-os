"""
PRADY TRADER — OracleExtended Agent (Phase 3).

Aggregates signals from external APIs that go beyond the core Oracle/Sentinel:
 • FreeCryptoAPI technical analysis & breakouts
 • CoinGecko dominance & community data
 • CryptoCompare social metrics
 • Bitquery whale transfers
 • Blockchain mempool congestion
 • NewsData.io breaking news velocity
 • Multi-exchange price divergence
 • CoinCodex predictions
 • Fear & Greed historical momentum

Weight: 0.10 in council
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from agents.base_agent import AgentSignal, BaseAgent
from config.constants import AGENT_WEIGHTS
from data.orderbook_feed import get_orderbook_feed
from data.orderflow import analyze_order_flow

logger = logging.getLogger("prady.agents.oracle_extended")


class OracleExtendedAgent(BaseAgent):
    """Extended oracle that consumes external API signals to produce
    a directional score fused from 8+ data sources."""

    def __init__(self):
        super().__init__(name="oracle_extended", weight=AGENT_WEIGHTS.get("oracle_extended", 0.10))

    async def analyze(self, symbol: str, market_data: Optional[Dict] = None) -> AgentSignal:
        """Run all sub-analyses in parallel and fuse into a single signal."""
        start = time.time()

        results = await asyncio.gather(
            self._freecrypto_ta_signal(symbol),
            self._dominance_signal(),
            self._social_signal(),
            self._whale_signal(),
            self._mempool_signal(),
            self._news_velocity_signal(),
            self._multi_exchange_signal(symbol),
            self._prediction_signal(symbol),
            self._order_flow_signal(symbol),
            self._fng_momentum_signal(),
            return_exceptions=True,
        )

        component_names = [
            "freecrypto_ta", "dominance", "social", "whale", "mempool",
            "news_velocity", "multi_exchange", "prediction", "order_flow", "fng_momentum",
        ]

        scores = {}
        weights = {
            "freecrypto_ta": 0.18,
            "dominance": 0.10,
            "social": 0.08,
            "whale": 0.15,
            "mempool": 0.08,
            "news_velocity": 0.10,
            "multi_exchange": 0.12,
            "prediction": 0.09,
            "order_flow": 0.16,
            "fng_momentum": 0.10,
        }

        for i, (name, res) in enumerate(zip(component_names, results)):
            if isinstance(res, (int, float)):
                scores[name] = float(res)
            elif isinstance(res, Exception):
                logger.debug("OracleExtended %s failed: %s", name, res)
                scores[name] = 0.0
            else:
                scores[name] = 0.0

        # Weighted fusion
        weighted_sum = sum(scores.get(n, 0) * weights.get(n, 0) for n in component_names)
        total_weight = sum(weights.get(n, 0) for n in component_names if scores.get(n, 0) != 0)
        if total_weight > 0:
            fused_score = weighted_sum / total_weight
        else:
            fused_score = 0.0

        # Clamp to [-100, 100]
        fused_score = max(-100, min(100, fused_score))

        # Direction
        if fused_score >= 15:
            direction = "LONG"
        elif fused_score <= -15:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        # Confidence: strength of conviction
        confidence = min(abs(fused_score) / 100, 1.0)

        elapsed = time.time() - start
        reasoning = (
            f"OracleExtended: score={fused_score:.1f}, dir={direction}, "
            f"conf={confidence:.2f} | components={scores} | {elapsed:.2f}s"
        )

        return AgentSignal(
            agent_name=self.name,
            direction=direction,
            confidence=round(confidence, 4),
            score=round(fused_score, 2),
            reasoning=reasoning,
            metadata={"components": scores, "weights": weights},
        )

    # ───────────────────────────────────────────────────────────
    # Sub-analyses (each returns a score -100 to +100)
    # ───────────────────────────────────────────────────────────

    async def _freecrypto_ta_signal(self, symbol: str) -> float:
        """FreeCryptoAPI technical analysis + breakouts → score."""
        try:
            from data.freecrypto_api import get_technical_analysis, get_breakouts

            coin = symbol.replace("USDT", "").upper()
            ta, breakouts = await asyncio.gather(
                get_technical_analysis(coin),
                get_breakouts(),
                return_exceptions=True,
            )

            score = 0.0

            # Technical analysis indicators
            if isinstance(ta, dict) and not isinstance(ta, Exception):
                rsi = ta.get("rsi") or ta.get("RSI")
                macd = ta.get("macd_signal") or ta.get("MACD_Signal")
                if rsi is not None:
                    rsi = float(rsi)
                    if rsi > 70:
                        score -= min((rsi - 70) * 2, 40)   # overbought
                    elif rsi < 30:
                        score += min((30 - rsi) * 2, 40)   # oversold
                if macd is not None:
                    macd = float(macd)
                    score += max(min(macd * 10, 30), -30)

            # Breakout signals
            if isinstance(breakouts, dict) and not isinstance(breakouts, Exception):
                items = breakouts.get("data") or breakouts.get("breakouts") or []
                if isinstance(items, list):
                    for item in items:
                        name = (item.get("symbol") or item.get("coin") or "").upper()
                        if coin in name:
                            direction = (item.get("direction") or "").lower()
                            if "bull" in direction or "up" in direction:
                                score += 20
                            elif "bear" in direction or "down" in direction:
                                score -= 20
                            break

            return max(min(score, 80), -80)
        except Exception:
            return 0.0

    async def _dominance_signal(self) -> float:
        """BTC dominance trend → score.
        Rising dominance while BTC up = bullish. Falling = altcoin rotation."""
        try:
            from data.free_apis import async_fetch_coingecko_global
            g = await async_fetch_coingecko_global()
            btc_dom = g.get("btc_dominance", 50)
            change = g.get("market_cap_change_24h_pct", 0)

            # High dominance (>55%) + rising market = bullish
            if btc_dom > 55 and change > 0:
                return min(btc_dom - 50, 30)
            elif btc_dom < 40 and change < 0:
                return max(-(50 - btc_dom), -30)
            return (change / 5) * 20  # mild signal from market momentum
        except Exception:
            return 0.0

    async def _social_signal(self) -> float:
        """CryptoCompare social metrics → score.
        Unusual spikes in Reddit/Twitter activity = signal."""
        try:
            from data.free_apis import async_fetch_cryptocompare_social
            social = await async_fetch_cryptocompare_social(1182)  # BTC
            if not social:
                return 0.0

            reddit_active = social.get("reddit_active", 0)
            reddit_posts = social.get("reddit_posts_per_day", 0)

            # Baseline: reddit_active ~5000, posts ~50/day for BTC
            if reddit_active > 10000:
                return min((reddit_active - 5000) / 500, 40)
            elif reddit_active < 2000:
                return max((reddit_active - 5000) / 500, -30)
            return 0.0
        except Exception:
            return 0.0

    async def _whale_signal(self) -> float:
        """Bitquery whale transfers → score.
        Many large transfers = potential volatility incoming."""
        try:
            from data.free_apis import async_fetch_bitquery_whale_transfers
            whales = await async_fetch_bitquery_whale_transfers(limit=10)
            if not whales:
                return 0.0

            total_usd = sum(w.get("amount_usd", 0) for w in whales)
            count = len(whales)

            # > $50M in whale transfers in 24h = elevated activity
            if total_usd > 100_000_000:
                return 30  # high activity, could go either way, mild bullish bias
            elif total_usd > 50_000_000:
                return 15
            elif count >= 5:
                return 10
            return 0.0
        except Exception:
            return 0.0

    async def _mempool_signal(self) -> float:
        """BTC mempool congestion → score.
        High mempool = high demand = mildly bullish.
        Very high = panic = mildly bearish."""
        try:
            from data.free_apis import async_fetch_blockchain_mempool
            mp = await async_fetch_blockchain_mempool()
            count = mp.get("unconfirmed_tx_count", 0)

            if count > 200000:
                return -20  # extreme congestion = panic selling
            elif count > 100000:
                return -10  # elevated
            elif count > 50000:
                return 10  # normal high demand
            elif count > 20000:
                return 5
            return 0.0
        except Exception:
            return 0.0

    async def _news_velocity_signal(self) -> float:
        """NewsData.io breaking news count → score.
        Sudden spike in news articles = potential volatility."""
        try:
            from data.free_apis import async_fetch_newsdata
            articles = await async_fetch_newsdata(query="bitcoin OR crypto")
            if not articles:
                return 0.0

            count = len(articles)
            # Baseline: ~5-10 articles. Spike = >15
            if count > 15:
                # Check sentiment of titles
                bullish_keywords = {"surge", "rally", "bull", "high", "soar", "moon", "up"}
                bearish_keywords = {"crash", "dump", "bear", "drop", "fall", "plunge", "down"}

                bull_count = sum(
                    1 for a in articles
                    if any(k in a.get("title", "").lower() for k in bullish_keywords)
                )
                bear_count = sum(
                    1 for a in articles
                    if any(k in a.get("title", "").lower() for k in bearish_keywords)
                )

                if bull_count > bear_count:
                    return min(20 + (count - 15) * 2, 50)
                elif bear_count > bull_count:
                    return max(-20 - (count - 15) * 2, -50)
                return 10  # high velocity, neutral sentiment
            return 0.0
        except Exception:
            return 0.0

    async def _multi_exchange_signal(self, symbol: str) -> float:
        """Multi-exchange price divergence → score.
        Large spread = arbitrage opportunity or manipulation."""
        try:
            from data.crypto_indicators_api import async_fetch_multi_exchange_price
            mp = await async_fetch_multi_exchange_price(symbol)
            spread = mp.get("spread_pct", 0)

            # Normal spread < 0.1%. Large spread = anomaly
            if spread > 0.5:
                return 25  # significant divergence — potential opportunity
            elif spread > 0.2:
                return 10
            return 0.0
        except Exception:
            return 0.0

    async def _prediction_signal(self, symbol: str) -> float:
        """CoinCodex prediction score → directional signal."""
        try:
            from data.crypto_indicators_api import async_fetch_coincodex_prediction
            coin_map = {
                "BTCUSDT": "bitcoin",
                "ETHUSDT": "ethereum",
                "BNBUSDT": "binancecoin",
                "SOLUSDT": "solana",
                "XRPUSDT": "ripple",
            }
            coin = coin_map.get(symbol.upper(), "bitcoin")
            pred = await async_fetch_coincodex_prediction(coin)
            if not pred:
                return 0.0

            pct = pred.get("prediction_pct_1d", 0)
            # Scale: 1% predicted change → 20 score points
            return max(-50, min(50, pct * 20))
        except Exception:
            return 0.0

    async def _order_flow_signal(self, symbol: str) -> float:
        """Live order-flow score from current book imbalance and microprice skew."""
        try:
            snapshot = get_orderbook_feed().get_snapshot(symbol)
            return analyze_order_flow(snapshot).score if snapshot else 0.0
        except Exception:
            return 0.0

    async def _fng_momentum_signal(self) -> float:
        """Fear & Greed 30-day momentum → contrarian signal.
        Extreme fear = buy signal. Extreme greed = sell signal."""
        try:
            from data.free_apis import async_fetch_fear_greed, async_fetch_fear_greed_history
            current = await async_fetch_fear_greed()
            history = await async_fetch_fear_greed_history(7)

            value = current.get("value", 50)

            # 7-day average
            if history:
                avg_7d = sum(d.get("value", 50) for d in history) / len(history)
            else:
                avg_7d = 50

            # Contrarian: extreme fear → bullish, extreme greed → bearish
            if value < 20:
                score = 40  # extreme fear → strong buy
            elif value < 35:
                score = 20  # fear → moderate buy
            elif value > 80:
                score = -40  # extreme greed → strong sell
            elif value > 65:
                score = -20  # greed → moderate sell
            else:
                score = 0

            # Momentum adjustment: if improving (value > avg), add to bullish
            momentum = (value - avg_7d) / 10
            score += momentum * 5

            return max(-50, min(50, score))
        except Exception:
            return 0.0
