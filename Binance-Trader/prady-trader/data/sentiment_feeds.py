"""
PRADY TRADER — Free sentiment data feeds.
All sources are 100% free, no paid API keys required.

1. Fear & Greed Index — alternative.me (no key)
2. Crypto news — Messari free API + RSS feeds (CoinDesk, Cointelegraph, Decrypt, Bitcoin Magazine)
3. NewsData.io — real-time news with built-in sentiment (free tier)
4. CryptoCompare — 100K calls/month free crypto news
5. Reddit sentiment — PRAW (free Reddit app credentials)
6. Aggregated VADER sentiment — weighted fusion across all sources
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from config.settings import get_settings

logger = logging.getLogger("prady.data.sentiment_feeds")

_REQUEST_TIMEOUT = 5

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
except ImportError:
    _vader = None
    logger.debug("vaderSentiment not installed — VADER scoring disabled")


# ── 1. Fear & Greed Index (completely free) ──────────────────

def fetch_fear_greed() -> Dict[str, Any]:
    """Fetch Fear & Greed index from alternative.me.
    Returns dict with 'value' (0-100), 'classification', 'timestamp'.
    Falls back to neutral (50) on any failure.
    """
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()["data"][0]
        return {
            "value": int(data["value"]),
            "classification": data.get("value_classification", "Neutral"),
            "timestamp": data.get("timestamp", ""),
        }
    except Exception as exc:
        logger.warning("Fear & Greed fetch failed: %s", exc)
        return {"value": 50, "classification": "Neutral", "timestamp": ""}


async def async_fetch_fear_greed() -> int:
    """Async version — returns just the 0-100 value. 50 on failure."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/?limit=1",
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json()
                return int(data["data"][0]["value"])
    except Exception:
        return 50


# ── 2. Crypto news — Messari + RSS ──────────────────────────────────

_RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
]


def fetch_crypto_news(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch crypto news from Messari free API + RSS feeds.
    No API key required. Returns list of dicts: title, url, source, sentiment.
    """
    articles: List[Dict[str, Any]] = []

    # Source 1: Messari free news API
    try:
        resp = requests.get(
            "https://data.messari.io/api/v1/news",
            params={"as-markdown": "false"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        for item in resp.json().get("data", [])[:limit]:
            articles.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": "messari",
                "created_at": item.get("published_at", ""),
                "sentiment": _simple_text_sentiment(item.get("title", "")),
            })
    except Exception as exc:
        logger.debug("Messari news fetch failed: %s", exc)

    # Source 2: RSS feeds
    try:
        import feedparser
        for feed_url in _RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                source_name = feed.feed.get("title", feed_url.split("/")[2])
                for entry in feed.entries[:10]:
                    articles.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "source": source_name,
                        "created_at": entry.get("published", ""),
                        "sentiment": _simple_text_sentiment(entry.get("title", "")),
                    })
            except Exception as exc:
                logger.debug("RSS feed %s failed: %s", feed_url, exc)
    except ImportError:
        logger.debug("feedparser not installed — skipping RSS feeds")

    return articles[:limit]


def fetch_all_rss_news() -> List[Dict[str, Any]]:
    """Fetch from all RSS feeds. No API key, no rate limit."""
    articles: List[Dict[str, Any]] = []
    try:
        import feedparser
    except ImportError:
        return articles
    for feed_url in _RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "source": feed_url,
                })
        except Exception as exc:
            logger.debug("RSS fetch failed for %s: %s", feed_url, exc)
    return articles


# ── 3. NewsData.io (real-time, built-in sentiment) ──────────────────

async def fetch_newsdata_crypto(symbols: List[str] | None = None) -> List[Dict[str, Any]]:
    """Fetch news from NewsData.io (free 200 req/day)."""
    cfg = get_settings()
    if not cfg.newsdata_api_key:
        return []
    symbols = symbols or ["BTC", "ETH"]
    try:
        import aiohttp
        url = "https://newsdata.io/api/1/news"
        params = {
            "apikey": cfg.newsdata_api_key,
            "q": " OR ".join(symbols),
            "language": "en",
            "category": "business,technology",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
                return data.get("results", [])
    except Exception as exc:
        logger.debug("NewsData fetch failed: %s", exc)
        return []


# ── 4. CryptoCompare news (100K calls/month free) ──────────────────

async def fetch_cryptocompare_news(categories: str = "BTC,ETH,Trading") -> List[Dict[str, Any]]:
    """Fetch news from CryptoCompare (free tier)."""
    cfg = get_settings()
    if not cfg.cryptocompare_api_key:
        return []
    try:
        import aiohttp
        url = "https://min-api.cryptocompare.com/data/v2/news/"
        params = {"categories": categories, "lang": "EN"}
        headers = {"Apikey": cfg.cryptocompare_api_key}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
                return data.get("Data", [])
    except Exception as exc:
        logger.debug("CryptoCompare news failed: %s", exc)
        return []


# ── 5. Messari async (no key needed) ───────────────────────────────

async def fetch_messari_news_async() -> List[Dict[str, Any]]:
    """Fetch news from Messari (no API key required)."""
    try:
        import aiohttp
        url = "https://data.messari.io/api/v1/news"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
                return data.get("data", [])
    except Exception as exc:
        logger.debug("Messari async news failed: %s", exc)
        return []


# ── 6. Fear & Greed history ─────────────────────────────────────────

async def fetch_fear_greed_history(limit: int = 7) -> List[Dict[str, Any]]:
    """Fetch Fear & Greed index history."""
    try:
        import aiohttp
        url = f"https://api.alternative.me/fng/?limit={limit}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return data.get("data", [])
    except Exception as exc:
        logger.debug("Fear & Greed history failed: %s", exc)
        return []


# ── 7. Aggregated VADER news sentiment ──────────────────────────────

async def get_aggregated_news_sentiment(symbol: str = "BTC") -> float:
    """Weighted VADER sentiment across all free sources.
    Returns -1.0 (very bearish) to +1.0 (very bullish).
    """
    if _vader is None:
        return 0.0

    scores: List[tuple] = []  # (score, weight)
    from data.free_apis import async_fetch_yahoo_finance_news

    # NewsData.io (weight 0.35 — real-time, built-in sentiment)
    nd_articles = await fetch_newsdata_crypto([symbol])
    if nd_articles:
        pos = sum(1 for a in nd_articles if a.get("sentiment") == "positive")
        neg = sum(1 for a in nd_articles if a.get("sentiment") == "negative")
        total = pos + neg
        if total > 0:
            scores.append(((pos - neg) / total, 0.35))

    # CryptoCompare (weight 0.30 — 100K calls/month)
    cc_articles = await fetch_cryptocompare_news(symbol)
    if cc_articles:
        cc_scores = [_vader.polarity_scores(a.get("title", ""))["compound"]
                     for a in cc_articles[:10]]
        if cc_scores:
            scores.append((sum(cc_scores) / len(cc_scores), 0.30))

    # RSS feeds via VADER (weight 0.20 — no rate limit)
    rss = fetch_all_rss_news()
    if rss:
        rss_scores = [_vader.polarity_scores(a["title"])["compound"] for a in rss]
        if rss_scores:
            scores.append((sum(rss_scores) / len(rss_scores), 0.20))

    # Messari (weight 0.15 — no key needed)
    m_articles = await fetch_messari_news_async()
    if m_articles:
        m_scores = [_vader.polarity_scores(a.get("title", ""))["compound"]
                    for a in m_articles[:5]]
        if m_scores:
            scores.append((sum(m_scores) / len(m_scores), 0.15))

    # Yahoo Finance news (weight 0.15 — free via yfinance)
    yahoo_articles = await async_fetch_yahoo_finance_news([f"{symbol}-USD"], max_per_symbol=5)
    if yahoo_articles:
        yahoo_scores = [
            _vader.polarity_scores(
                ". ".join(part for part in [a.get("title", ""), a.get("summary", "")] if part)
            )["compound"]
            for a in yahoo_articles
        ]
        yahoo_scores = [score for score in yahoo_scores if score is not None]
        if yahoo_scores:
            scores.append((sum(yahoo_scores) / len(yahoo_scores), 0.15))

    if not scores:
        return 0.0

    total_weight = sum(w for _, w in scores)
    weighted_score = sum(s * w for s, w in scores) / total_weight
    return max(-1.0, min(1.0, weighted_score))


# ── 3. Reddit sentiment (free PRAW) ─────────────────────────

_CRYPTO_SUBREDDITS = ["Bitcoin", "CryptoCurrency", "binance", "ethtrader"]


def fetch_reddit_sentiment(
    subreddits: Optional[List[str]] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """Fetch recent posts from crypto subreddits and analyze sentiment.
    Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env (free from reddit.com/prefs/apps).
    Returns dict with 'posts', 'avg_score', 'bullish_pct', 'bearish_pct'.
    """
    cfg = get_settings()
    if not cfg.reddit_client_id or not cfg.reddit_client_secret:
        logger.info("Reddit credentials not configured — skipping Reddit sentiment")
        return {"posts": [], "avg_score": 0.0, "bullish_pct": 0.5, "bearish_pct": 0.5}

    try:
        import praw
    except ImportError:
        logger.warning("praw not installed — skipping Reddit sentiment")
        return {"posts": [], "avg_score": 0.0, "bullish_pct": 0.5, "bearish_pct": 0.5}

    subs = subreddits or _CRYPTO_SUBREDDITS

    try:
        reddit = praw.Reddit(
            client_id=cfg.reddit_client_id,
            client_secret=cfg.reddit_client_secret,
            user_agent=cfg.reddit_user_agent,
        )

        posts = []
        for sub_name in subs:
            try:
                subreddit = reddit.subreddit(sub_name)
                for post in subreddit.hot(limit=limit):
                    sentiment = _simple_text_sentiment(post.title)
                    posts.append({
                        "subreddit": sub_name,
                        "title": post.title,
                        "score": post.score,
                        "upvote_ratio": post.upvote_ratio,
                        "num_comments": post.num_comments,
                        "sentiment": sentiment,
                    })
            except Exception as exc:
                logger.warning("Failed to fetch r/%s: %s", sub_name, exc)

        if not posts:
            return {"posts": [], "avg_score": 0.0, "bullish_pct": 0.5, "bearish_pct": 0.5}

        bullish = sum(1 for p in posts if p["sentiment"] == "bullish")
        bearish = sum(1 for p in posts if p["sentiment"] == "bearish")
        total = len(posts)

        return {
            "posts": posts[:20],  # cap output
            "avg_score": sum(p["score"] for p in posts) / total,
            "bullish_pct": bullish / total,
            "bearish_pct": bearish / total,
        }
    except Exception as exc:
        logger.warning("Reddit sentiment failed: %s", exc)
        return {"posts": [], "avg_score": 0.0, "bullish_pct": 0.5, "bearish_pct": 0.5}


# ── Simple keyword-based sentiment (no ML dependency needed) ─

_BULLISH_WORDS = {
    "bull", "bullish", "moon", "pump", "buy", "long", "breakout", "ath",
    "accumulate", "hodl", "rally", "surge", "soar", "gain", "green",
    "rocket", "🚀", "📈", "up", "higher",
}
_BEARISH_WORDS = {
    "bear", "bearish", "dump", "sell", "short", "crash", "dip", "drop",
    "correction", "fear", "panic", "red", "down", "lower", "plunge",
    "collapse", "📉", "rug", "scam", "bubble",
}


def _simple_text_sentiment(text: str) -> str:
    """Quick keyword-based sentiment. No ML model needed."""
    words = set(text.lower().split())
    bull_count = len(words & _BULLISH_WORDS)
    bear_count = len(words & _BEARISH_WORDS)
    if bull_count > bear_count:
        return "bullish"
    elif bear_count > bull_count:
        return "bearish"
    return "neutral"
