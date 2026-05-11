"""
PRADY TRADER — Phase 3: Maximum API Integration.

Async-first data layer covering 10+ free crypto data providers.
Every function has an async primary + sync wrapper for backward compatibility.

Providers:
 1. CoinGecko (Pro key optional — falls back to free)
 2. NewsAPI.org
 3. NewsData.io
 4. CryptoCompare
 5. CoinAPI.io
 6. Bitquery (GraphQL)
 7. Alternative.me (Fear & Greed)
 8. Blockchain.com (BTC on-chain)
 9. Messari
10. Yahoo Finance (via yfinance)
11. RSS feeds (CoinDesk, Cointelegraph, Decrypt, TheBlock, Bitcoin Magazine)

Features:
 • aiohttp session pooling with connector limit
 • asyncio.Semaphore rate limiters per provider
 • Redis cache with per-endpoint TTL (graceful fallback to in-memory dict)
 • Sync wrappers via asyncio.run() for legacy callers
"""

from __future__ import annotations

import atexit
import asyncio
import hashlib
import json
import logging
import socket
import time
from typing import Any, Dict, List, Optional

import aiohttp

from config.settings import get_settings
from utils.provider_status import (
    is_provider_suppressed,
    mark_provider_disabled,
    mark_provider_failure,
    mark_provider_success,
    recommended_suppression_seconds,
    should_emit_runtime_warning,
    suppress_provider,
)

logger = logging.getLogger("prady.data.free_apis")

_TIMEOUT = aiohttp.ClientTimeout(total=12)

# ═══════════════════════════════════════════════════════════════
# Token-bucket rate limiter (production)
# ═══════════════════════════════════════════════════════════════

try:
    from utils.rate_limiter import get_rate_limiter as _get_rl
    _RL = _get_rl()
except Exception:
    _RL = None


async def _rl_acquire(provider: str) -> None:
    """Acquire a token from the production rate limiter (if available)."""
    if _RL is not None:
        await _RL.acquire(provider)


# ═══════════════════════════════════════════════════════════════
# Rate limiters (asyncio.Semaphore per provider)
# ═══════════════════════════════════════════════════════════════

_RATE_LIMITERS: Dict[str, asyncio.Semaphore] = {}
_RATE_LIMITER_LOOP: Optional[asyncio.AbstractEventLoop] = None


def _limiter(name: str, max_concurrent: int = 5) -> asyncio.Semaphore:
    global _RATE_LIMITER_LOOP
    # Recreate all semaphores if the event loop changed (e.g. QThread new loop)
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if current_loop is not None and _RATE_LIMITER_LOOP is not current_loop:
        _RATE_LIMITERS.clear()
        _RATE_LIMITER_LOOP = current_loop
    if name not in _RATE_LIMITERS:
        _RATE_LIMITERS[name] = asyncio.Semaphore(max_concurrent)
    # Also acquire from the production token-bucket (fire-and-forget schedule)
    if _RL is not None:
        try:
            asyncio.ensure_future(_rl_acquire(name))
        except RuntimeError:
            pass  # no running loop — skip token-bucket
    return _RATE_LIMITERS[name]


# ═══════════════════════════════════════════════════════════════
# Cache layer (Redis with in-memory fallback)
# ═══════════════════════════════════════════════════════════════

_MEM_CACHE: Dict[str, tuple] = {}  # key → (data, expiry_ts)


def _cache_key(prefix: str, *args: Any) -> str:
    raw = f"{prefix}:{':'.join(str(a) for a in args)}"
    return hashlib.md5(raw.encode()).hexdigest()


async def _cache_get(key: str) -> Optional[Any]:
    try:
        from config.settings import get_settings
        url = get_settings().redis_url
        if url:
            import redis as _redis
            r = _redis.from_url(url, decode_responses=True)
            val = r.get(f"fapi:{key}")
            if val:
                return json.loads(val)
    except Exception:
        pass
    entry = _MEM_CACHE.get(key)
    if entry and entry[1] > time.time():
        return entry[0]
    return None


async def _cache_set(key: str, data: Any, ttl: int = 60) -> None:
    try:
        from config.settings import get_settings
        url = get_settings().redis_url
        if url:
            import redis as _redis
            r = _redis.from_url(url, decode_responses=True)
            r.setex(f"fapi:{key}", ttl, json.dumps(data, default=str))
    except Exception:
        pass
    _MEM_CACHE[key] = (data, time.time() + ttl)


# ═══════════════════════════════════════════════════════════════
# Session management
# ═══════════════════════════════════════════════════════════════

_SESSION: Optional[aiohttp.ClientSession] = None
_SESSION_LOOP: Optional[asyncio.AbstractEventLoop] = None


async def _get_session() -> aiohttp.ClientSession:
    global _SESSION, _SESSION_LOOP
    current_loop = asyncio.get_running_loop()
    if _SESSION is None or _SESSION.closed or _SESSION_LOOP is not current_loop:
        if _SESSION and not _SESSION.closed:
            try:
                await _SESSION.close()
            except Exception:
                pass
        connector = aiohttp.TCPConnector(
            limit=30,
            limit_per_host=10,
            resolver=aiohttp.ThreadedResolver(),
            family=socket.AF_INET,
        )
        _SESSION = aiohttp.ClientSession(connector=connector, timeout=_TIMEOUT)
        _SESSION_LOOP = current_loop
    return _SESSION


async def close_session() -> None:
    global _SESSION, _SESSION_LOOP
    if _SESSION and not _SESSION.closed:
        await _SESSION.close()
    _SESSION = None
    _SESSION_LOOP = None


def _run_sync(async_fn, *args: Any) -> Any:
    """Run an async fetcher in a fresh loop and close pooled sessions before exit."""

    async def _runner() -> Any:
        try:
            return await async_fn(*args)
        finally:
            await close_session()

    return asyncio.run(_runner())


def close_session_sync() -> None:
    """Best-effort synchronous shutdown for the shared aiohttp session."""
    global _SESSION, _SESSION_LOOP

    session = _SESSION
    loop = _SESSION_LOOP
    _SESSION = None
    _SESSION_LOOP = None

    if not session or session.closed:
        return

    try:
        if loop and not loop.is_closed():
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(session.close(), loop)
                future.result(timeout=2)
            else:
                loop.run_until_complete(session.close())
        else:
            asyncio.run(session.close())
    except Exception:
        pass


atexit.register(close_session_sync)


# ═══════════════════════════════════════════════════════════════
# Helper: settings keys
# ═══════════════════════════════════════════════════════════════

def _get_key(name: str) -> str:
    return getattr(get_settings(), name, "") or ""


def _provider_enabled(flag_name: str) -> bool:
    return bool(getattr(get_settings(), flag_name, True))


def _provider_disabled(provider: str, reason: str, default: Any, *, details: Dict[str, Any] | None = None) -> Any:
    mark_provider_disabled(
        provider,
        reason,
        category="data",
        configured=False,
        optional=True,
        details=details,
    )
    return default


def _provider_succeeded(
    provider: str,
    message: str,
    *,
    optional: bool,
    details: Dict[str, Any] | None = None,
) -> None:
    mark_provider_success(
        provider,
        message,
        category="data",
        configured=True,
        optional=optional,
        details=details,
    )


def _provider_failed(
    provider: str,
    log_message: str,
    exc: Exception,
    *,
    optional: bool,
    details: Dict[str, Any] | None = None,
) -> None:
    record = mark_provider_failure(
        provider,
        str(exc),
        category="data",
        configured=True,
        optional=optional,
        details=details,
    )
    settings = get_settings()
    cooldown = int(getattr(settings, "provider_warning_cooldown_sec", 300) or 300)
    startup_grace = int(getattr(settings, "provider_startup_grace_sec", 180) or 180)
    backoff = recommended_suppression_seconds(str(exc), default_cooldown=cooldown)
    threshold = 1 if backoff >= 3600 else 2
    if backoff > 0 and int(record.get("consecutive_failures", 0) or 0) >= threshold:
        suppress_provider(
            provider,
            f"Temporarily suppressing {provider} after repeated failures",
            cooldown_sec=backoff,
            category="data",
            configured=True,
            optional=optional,
            details={**(details or {}), "error": str(exc)},
        )
    if should_emit_runtime_warning(
        provider,
        cooldown_sec=cooldown,
        startup_grace_sec=startup_grace,
        warn_after_failures=2 if optional else 1,
    ):
        logger.warning("%s: %s", log_message, exc)
    else:
        logger.debug("%s: %s", log_message, exc)


def _provider_temporarily_suppressed(provider: str, default: Any) -> Any | None:
    if not is_provider_suppressed(provider):
        return None
    logger.debug("%s temporarily suppressed after recent failures", provider)
    return default


# ═══════════════════════════════════════════════════════════════
# 1. CoinGecko (free or Pro with key)
# ═══════════════════════════════════════════════════════════════

_CG_FREE = "https://api.coingecko.com/api/v3"
_CG_PRO = "https://pro-api.coingecko.com/api/v3"


def _is_demo_key(key: str) -> bool:
    """Demo keys start with 'CG-'; Pro keys do not."""
    return key.startswith("CG-")


def _cg_base() -> str:
    key = _get_key("coingecko_api_key")
    if key and not _is_demo_key(key):
        return _CG_PRO
    return _CG_FREE


def _cg_headers() -> Dict[str, str]:
    key = _get_key("coingecko_api_key")
    if not key:
        return {}
    if _is_demo_key(key):
        return {"x-cg-demo-api-key": key}
    return {"x-cg-pro-api-key": key}


async def async_fetch_coingecko_price(
    coin_ids: str = "bitcoin,ethereum",
    vs_currencies: str = "usd",
) -> Dict[str, Any]:
    ck = _cache_key("cg_price", coin_ids, vs_currencies)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CoinGecko", {})
    if suppressed is not None:
        return suppressed
    async with _limiter("coingecko"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_cg_base()}/simple/price",
                params={
                    "ids": coin_ids,
                    "vs_currencies": vs_currencies,
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                },
                headers=_cg_headers(),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                await _cache_set(ck, data, ttl=30)
                _provider_succeeded(
                    "CoinGecko",
                    "Simple price feed healthy",
                    optional=False,
                    details={"endpoint": "simple/price", "coin_ids": coin_ids},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinGecko",
                "CoinGecko price fetch failed",
                exc,
                optional=False,
                details={"endpoint": "simple/price", "coin_ids": coin_ids},
            )
            return {}


def fetch_coingecko_price(
    coin_ids: str = "bitcoin,ethereum",
    vs_currencies: str = "usd",
) -> Dict[str, Any]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_coingecko_price, coin_ids, vs_currencies)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(
            _run_sync, async_fetch_coingecko_price, coin_ids, vs_currencies
        ).result(timeout=15)


async def async_fetch_coingecko_global() -> Dict[str, Any]:
    ck = _cache_key("cg_global")
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CoinGecko", {})
    if suppressed is not None:
        return suppressed
    async with _limiter("coingecko"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_cg_base()}/global", headers=_cg_headers()
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                d = raw.get("data", {})
                data = {
                    "total_market_cap_usd": d.get("total_market_cap", {}).get("usd", 0),
                    "total_volume_usd": d.get("total_volume", {}).get("usd", 0),
                    "btc_dominance": d.get("market_cap_percentage", {}).get("btc", 0),
                    "eth_dominance": d.get("market_cap_percentage", {}).get("eth", 0),
                    "active_coins": d.get("active_cryptocurrencies", 0),
                    "markets": d.get("markets", 0),
                    "market_cap_change_24h_pct": d.get(
                        "market_cap_change_percentage_24h_usd", 0
                    ),
                }
                await _cache_set(ck, data, ttl=120)
                _provider_succeeded(
                    "CoinGecko",
                    "Global market feed healthy",
                    optional=False,
                    details={"endpoint": "global"},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinGecko",
                "CoinGecko global fetch failed",
                exc,
                optional=False,
                details={"endpoint": "global"},
            )
            return {}


def fetch_coingecko_global() -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_coingecko_global)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_run_sync, async_fetch_coingecko_global).result(timeout=15)


async def async_fetch_coingecko_trending() -> List[Dict[str, Any]]:
    ck = _cache_key("cg_trending")
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coingecko"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_cg_base()}/search/trending", headers=_cg_headers()
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                coins = raw.get("coins", [])
                data = [
                    {
                        "name": c["item"]["name"],
                        "symbol": c["item"]["symbol"],
                        "market_cap_rank": c["item"].get("market_cap_rank", 0),
                        "score": c["item"].get("score", 0),
                    }
                    for c in coins
                ]
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "CoinGecko",
                    "Trending feed healthy",
                    optional=False,
                    details={"endpoint": "search/trending"},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinGecko",
                "CoinGecko trending fetch failed",
                exc,
                optional=False,
                details={"endpoint": "search/trending"},
            )
            return []


def fetch_coingecko_trending() -> List[Dict[str, Any]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_coingecko_trending)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_run_sync, async_fetch_coingecko_trending).result(timeout=15)


async def async_fetch_coingecko_market_chart(
    coin_id: str = "bitcoin", days: int = 7, vs_currency: str = "usd"
) -> Dict[str, Any]:
    ck = _cache_key("cg_chart", coin_id, days, vs_currency)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coingecko"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_cg_base()}/coins/{coin_id}/market_chart",
                params={"vs_currency": vs_currency, "days": days},
                headers=_cg_headers(),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "CoinGecko",
                    "Market chart feed healthy",
                    optional=False,
                    details={"endpoint": "market_chart", "coin_id": coin_id},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinGecko",
                "CoinGecko market chart fetch failed",
                exc,
                optional=False,
                details={"endpoint": "market_chart", "coin_id": coin_id},
            )
            return {}


def fetch_coingecko_market_chart(
    coin_id: str = "bitcoin", days: int = 7, vs_currency: str = "usd"
) -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_coingecko_market_chart, coin_id, days, vs_currency)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(
            _run_sync, async_fetch_coingecko_market_chart, coin_id, days, vs_currency
        ).result(timeout=15)


async def async_fetch_coingecko_coin_data(coin_id: str = "bitcoin") -> Dict[str, Any]:
    """Detailed coin data including community, developer, and tickers."""
    ck = _cache_key("cg_coin", coin_id)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coingecko"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_cg_base()}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "true",
                    "market_data": "true",
                    "community_data": "true",
                    "developer_data": "false",
                },
                headers=_cg_headers(),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                md = raw.get("market_data", {})
                cd = raw.get("community_data", {})
                data = {
                    "price_usd": md.get("current_price", {}).get("usd", 0),
                    "market_cap": md.get("market_cap", {}).get("usd", 0),
                    "total_volume": md.get("total_volume", {}).get("usd", 0),
                    "price_change_24h_pct": md.get("price_change_percentage_24h", 0),
                    "price_change_7d_pct": md.get("price_change_percentage_7d", 0),
                    "price_change_30d_pct": md.get("price_change_percentage_30d", 0),
                    "ath": md.get("ath", {}).get("usd", 0),
                    "ath_change_pct": md.get("ath_change_percentage", {}).get("usd", 0),
                    "circulating_supply": md.get("circulating_supply", 0),
                    "max_supply": md.get("max_supply", 0),
                    "twitter_followers": cd.get("twitter_followers", 0),
                    "reddit_subscribers": cd.get("reddit_subscribers", 0),
                    "reddit_active_48h": cd.get("reddit_accounts_active_48h", 0),
                }
                await _cache_set(ck, data, ttl=120)
                _provider_succeeded(
                    "CoinGecko",
                    "Coin detail feed healthy",
                    optional=False,
                    details={"endpoint": "coin", "coin_id": coin_id},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinGecko",
                "CoinGecko coin data fetch failed",
                exc,
                optional=False,
                details={"endpoint": "coin", "coin_id": coin_id},
            )
            return {}


async def async_fetch_coingecko_exchanges() -> List[Dict[str, Any]]:
    """Top exchanges by trust score."""
    ck = _cache_key("cg_exchanges")
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coingecko"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_cg_base()}/exchanges",
                params={"per_page": 20, "page": 1},
                headers=_cg_headers(),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                data = [
                    {
                        "id": e.get("id"),
                        "name": e.get("name"),
                        "trust_score": e.get("trust_score", 0),
                        "trade_volume_24h_btc": e.get("trade_volume_24h_btc", 0),
                        "year_established": e.get("year_established"),
                    }
                    for e in raw
                ]
                await _cache_set(ck, data, ttl=600)
                _provider_succeeded(
                    "CoinGecko",
                    "Exchange directory feed healthy",
                    optional=False,
                    details={"endpoint": "exchanges"},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinGecko",
                "CoinGecko exchanges fetch failed",
                exc,
                optional=False,
                details={"endpoint": "exchanges"},
            )
            return []


# ═══════════════════════════════════════════════════════════════
# 2. NewsAPI.org
# ═══════════════════════════════════════════════════════════════

async def async_fetch_newsapi(
    query: str = "bitcoin OR crypto OR ethereum",
    page_size: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch news articles from NewsAPI.org."""
    if not _provider_enabled("enable_newsapi"):
        return _provider_disabled(
            "NewsAPI",
            "Disabled in settings",
            [],
            details={"flag": "enable_newsapi"},
        )
    key = _get_key("news_api_key")
    if not key:
        return _provider_disabled(
            "NewsAPI",
            "API key not configured",
            [],
            details={"setting": "news_api_key"},
        )
    ck = _cache_key("newsapi", query, page_size)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("newsapi", 3):
        try:
            session = await _get_session()
            async with session.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": page_size,
                    "apiKey": key,
                },
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                articles = raw.get("articles", [])
                data = [
                    {
                        "title": a.get("title", ""),
                        "description": a.get("description", ""),
                        "source": a.get("source", {}).get("name", ""),
                        "url": a.get("url", ""),
                        "published_at": a.get("publishedAt", ""),
                    }
                    for a in articles
                ]
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "NewsAPI",
                    "Everything feed healthy",
                    optional=True,
                    details={"endpoint": "everything", "query": query},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "NewsAPI",
                "NewsAPI fetch failed",
                exc,
                optional=True,
                details={"endpoint": "everything", "query": query},
            )
            return []


# ═══════════════════════════════════════════════════════════════
# 3. NewsData.io
# ═══════════════════════════════════════════════════════════════

async def async_fetch_newsdata(
    query: str = "bitcoin OR crypto",
    category: str = "business",
) -> List[Dict[str, Any]]:
    """Fetch news from NewsData.io (free tier: 200 req/day)."""
    if not _provider_enabled("enable_newsdata"):
        return _provider_disabled(
            "NewsData.io",
            "Disabled in settings",
            [],
            details={"flag": "enable_newsdata"},
        )
    key = _get_key("newsdata_api_key")
    if not key:
        return _provider_disabled(
            "NewsData.io",
            "API key not configured",
            [],
            details={"setting": "newsdata_api_key"},
        )
    ck = _cache_key("newsdata", query, category)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("newsdata", 2):
        try:
            session = await _get_session()
            async with session.get(
                "https://newsdata.io/api/1/news",
                params={
                    "apikey": key,
                    "q": query,
                    "language": "en",
                    "category": category,
                },
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                results = raw.get("results", [])
                data = [
                    {
                        "title": a.get("title", ""),
                        "description": a.get("description") or "",
                        "source": a.get("source_id", ""),
                        "url": a.get("link", ""),
                        "published_at": a.get("pubDate", ""),
                        "sentiment": a.get("sentiment", ""),
                    }
                    for a in results
                ]
                await _cache_set(ck, data, ttl=600)
                _provider_succeeded(
                    "NewsData.io",
                    "News feed healthy",
                    optional=True,
                    details={"endpoint": "news", "query": query, "category": category},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "NewsData.io",
                "NewsData.io fetch failed",
                exc,
                optional=True,
                details={"endpoint": "news", "query": query, "category": category},
            )
            return []


# ═══════════════════════════════════════════════════════════════
# 4. CryptoCompare
# ═══════════════════════════════════════════════════════════════

_CC_BASE = "https://min-api.cryptocompare.com/data"


def _cc_headers() -> Dict[str, str]:
    key = _get_key("cryptocompare_api_key")
    return {"authorization": f"Apikey {key}"} if key else {}


async def async_fetch_cryptocompare_news(
    categories: str = "BTC,ETH,Trading",
) -> List[Dict[str, Any]]:
    """Latest crypto news from CryptoCompare."""
    if not _provider_enabled("enable_cryptocompare"):
        return _provider_disabled(
            "CryptoCompare",
            "Disabled in settings",
            [],
            details={"flag": "enable_cryptocompare"},
        )
    ck = _cache_key("cc_news", categories)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CryptoCompare", [])
    if suppressed is not None:
        return suppressed
    async with _limiter("cryptocompare"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_CC_BASE}/v2/news/",
                params={"categories": categories, "lang": "EN"},
                headers=_cc_headers(),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                articles = raw.get("Data", [])
                data = [
                    {
                        "title": a.get("title", ""),
                        "body": a.get("body", "")[:500],
                        "source": a.get("source", ""),
                        "url": a.get("url", ""),
                        "published_at": a.get("published_on", 0),
                        "categories": a.get("categories", ""),
                    }
                    for a in articles[:20]
                ]
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "CryptoCompare",
                    "News feed healthy",
                    optional=True,
                    details={"endpoint": "news", "categories": categories},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CryptoCompare",
                "CryptoCompare news fetch failed",
                exc,
                optional=True,
                details={"endpoint": "news", "categories": categories},
            )
            return []


async def async_fetch_cryptocompare_price(
    fsym: str = "BTC", tsyms: str = "USD"
) -> Dict[str, Any]:
    """Multi-exchange aggregated price from CryptoCompare."""
    if not _provider_enabled("enable_cryptocompare"):
        return _provider_disabled(
            "CryptoCompare",
            "Disabled in settings",
            {},
            details={"flag": "enable_cryptocompare"},
        )
    ck = _cache_key("cc_price", fsym, tsyms)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CryptoCompare", {})
    if suppressed is not None:
        return suppressed
    async with _limiter("cryptocompare"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_CC_BASE}/pricemultifull",
                params={"fsyms": fsym, "tsyms": tsyms},
                headers=_cc_headers(),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                display = raw.get("RAW", {}).get(fsym, {}).get(tsyms, {})
                data = {
                    "price": display.get("PRICE", 0),
                    "open_24h": display.get("OPEN24HOUR", 0),
                    "high_24h": display.get("HIGH24HOUR", 0),
                    "low_24h": display.get("LOW24HOUR", 0),
                    "volume_24h": display.get("VOLUME24HOUR", 0),
                    "change_24h": display.get("CHANGE24HOUR", 0),
                    "change_pct_24h": display.get("CHANGEPCT24HOUR", 0),
                    "market_cap": display.get("MKTCAP", 0),
                    "supply": display.get("SUPPLY", 0),
                    "last_market": display.get("LASTMARKET", ""),
                }
                await _cache_set(ck, data, ttl=30)
                _provider_succeeded(
                    "CryptoCompare",
                    "Price feed healthy",
                    optional=True,
                    details={"endpoint": "pricemultifull", "fsym": fsym, "tsyms": tsyms},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CryptoCompare",
                "CryptoCompare price fetch failed",
                exc,
                optional=True,
                details={"endpoint": "pricemultifull", "fsym": fsym, "tsyms": tsyms},
            )
            return {}


async def async_fetch_cryptocompare_social(coin_id: int = 1182) -> Dict[str, Any]:
    """Social stats from CryptoCompare (1182 = BTC)."""
    if not _provider_enabled("enable_cryptocompare"):
        return _provider_disabled(
            "CryptoCompare",
            "Disabled in settings",
            {},
            details={"flag": "enable_cryptocompare"},
        )
    ck = _cache_key("cc_social", coin_id)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CryptoCompare", {})
    if suppressed is not None:
        return suppressed
    async with _limiter("cryptocompare"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_CC_BASE}/social/coin/latest",
                params={"coinId": coin_id},
                headers=_cc_headers(),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                d = raw.get("Data", {})
                tw = d.get("Twitter", {})
                rd = d.get("Reddit", {})
                data = {
                    "twitter_followers": tw.get("followers", 0),
                    "twitter_statuses": tw.get("statuses", 0),
                    "twitter_favourites": tw.get("favourites", 0),
                    "reddit_subscribers": rd.get("subscribers", 0),
                    "reddit_active": rd.get("active_users", 0),
                    "reddit_posts_per_day": rd.get("posts_per_day", 0),
                    "reddit_comments_per_day": rd.get("comments_per_day", 0),
                }
                await _cache_set(ck, data, ttl=600)
                _provider_succeeded(
                    "CryptoCompare",
                    "Social feed healthy",
                    optional=True,
                    details={"endpoint": "social", "coin_id": coin_id},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CryptoCompare",
                "CryptoCompare social fetch failed",
                exc,
                optional=True,
                details={"endpoint": "social", "coin_id": coin_id},
            )
            return {}


async def async_fetch_cryptocompare_histohour(
    fsym: str = "BTC", tsym: str = "USD", limit: int = 168
) -> List[Dict[str, Any]]:
    """Hourly OHLCV from CryptoCompare (default: 7 days)."""
    if not _provider_enabled("enable_cryptocompare"):
        return _provider_disabled(
            "CryptoCompare",
            "Disabled in settings",
            [],
            details={"flag": "enable_cryptocompare"},
        )
    ck = _cache_key("cc_histohour", fsym, tsym, limit)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CryptoCompare", [])
    if suppressed is not None:
        return suppressed
    async with _limiter("cryptocompare"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_CC_BASE}/v2/histohour",
                params={"fsym": fsym, "tsym": tsym, "limit": limit},
                headers=_cc_headers(),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                bars = raw.get("Data", {}).get("Data", [])
                data = [
                    {
                        "time": b["time"],
                        "open": b["open"],
                        "high": b["high"],
                        "low": b["low"],
                        "close": b["close"],
                        "volume_from": b.get("volumefrom", 0),
                        "volume_to": b.get("volumeto", 0),
                    }
                    for b in bars
                ]
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "CryptoCompare",
                    "Histohour feed healthy",
                    optional=True,
                    details={"endpoint": "histohour", "fsym": fsym, "tsym": tsym},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CryptoCompare",
                "CryptoCompare histohour fetch failed",
                exc,
                optional=True,
                details={"endpoint": "histohour", "fsym": fsym, "tsym": tsym},
            )
            return []


# ═══════════════════════════════════════════════════════════════
# 5. CoinAPI.io
# ═══════════════════════════════════════════════════════════════

_COINAPI_BASE = "https://rest.coinapi.io/v1"


async def async_fetch_coinapi_ohlcv(
    symbol: str = "BINANCE_SPOT_BTC_USDT",
    period: str = "1HRS",
    limit: int = 168,
) -> List[Dict[str, Any]]:
    """OHLCV data from CoinAPI (free tier: 100 req/day)."""
    if not _provider_enabled("enable_coinapi"):
        return _provider_disabled(
            "CoinAPI",
            "Disabled in settings",
            [],
            details={"flag": "enable_coinapi"},
        )
    key = _get_key("coinapi_key")
    if not key:
        return _provider_disabled(
            "CoinAPI",
            "API key not configured",
            [],
            details={"setting": "coinapi_key"},
        )
    ck = _cache_key("coinapi_ohlcv", symbol, period, limit)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coinapi", 2):
        try:
            session = await _get_session()
            async with session.get(
                f"{_COINAPI_BASE}/ohlcv/{symbol}/latest",
                params={"period_id": period, "limit": limit},
                headers={"X-CoinAPI-Key": key},
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                data = [
                    {
                        "time": b.get("time_period_start", ""),
                        "open": b.get("price_open", 0),
                        "high": b.get("price_high", 0),
                        "low": b.get("price_low", 0),
                        "close": b.get("price_close", 0),
                        "volume": b.get("volume_traded", 0),
                        "trades_count": b.get("trades_count", 0),
                    }
                    for b in raw
                ]
                await _cache_set(ck, data, ttl=600)
                _provider_succeeded(
                    "CoinAPI",
                    "OHLCV feed healthy",
                    optional=True,
                    details={"endpoint": "ohlcv", "symbol": symbol, "period": period},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinAPI",
                "CoinAPI OHLCV fetch failed",
                exc,
                optional=True,
                details={"endpoint": "ohlcv", "symbol": symbol, "period": period},
            )
            return []


async def async_fetch_coinapi_exchange_rates(
    base: str = "BTC", quotes: str = "USD,EUR,GBP,JPY"
) -> Dict[str, float]:
    """Exchange rates from CoinAPI."""
    if not _provider_enabled("enable_coinapi"):
        return _provider_disabled(
            "CoinAPI",
            "Disabled in settings",
            {},
            details={"flag": "enable_coinapi"},
        )
    key = _get_key("coinapi_key")
    if not key:
        return _provider_disabled(
            "CoinAPI",
            "API key not configured",
            {},
            details={"setting": "coinapi_key"},
        )
    ck = _cache_key("coinapi_rates", base, quotes)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coinapi", 2):
        try:
            session = await _get_session()
            async with session.get(
                f"{_COINAPI_BASE}/exchangerate/{base}",
                headers={"X-CoinAPI-Key": key},
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                quote_set = set(quotes.upper().split(","))
                rates = raw.get("rates", [])
                data = {
                    r["asset_id_quote"]: r["rate"]
                    for r in rates
                    if r.get("asset_id_quote") in quote_set
                }
                await _cache_set(ck, data, ttl=60)
                _provider_succeeded(
                    "CoinAPI",
                    "Exchange-rate feed healthy",
                    optional=True,
                    details={"endpoint": "exchangerate", "base": base},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "CoinAPI",
                "CoinAPI exchange rates fetch failed",
                exc,
                optional=True,
                details={"endpoint": "exchangerate", "base": base},
            )
            return {}


# ═══════════════════════════════════════════════════════════════
# 6. Bitquery (GraphQL — free tier: 10k points/month)
# ═══════════════════════════════════════════════════════════════

_BITQUERY_URL = "https://graphql.bitquery.io"


async def async_fetch_bitquery_whale_transfers(
    network: str = "bitcoin",
    min_amount_usd: float = 1_000_000,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Fetch large (whale) transfers from Bitquery GraphQL."""
    if not _provider_enabled("enable_bitquery"):
        return _provider_disabled(
            "Bitquery",
            "Disabled in settings",
            [],
            details={"flag": "enable_bitquery"},
        )
    key = _get_key("bitquery_api_key")
    if not key:
        return _provider_disabled(
            "Bitquery",
            "API key not configured",
            [],
            details={"setting": "bitquery_api_key"},
        )
    ck = _cache_key("bq_whale", network, min_amount_usd, limit)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("Bitquery", [])
    if suppressed is not None:
        return suppressed

    since_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))
    min_btc = min_amount_usd / 50000  # rough BTC conversion

    query = """
    {
      bitcoin(network: %s) {
        transfers(
          options: {limit: %d, desc: "amount"}
          amount: {gteq: %f}
          date: {since: "%s"}
        ) {
          amount
          amountInUSD: amount(in: USD)
          sender { address }
          receiver { address }
          block { timestamp { iso8601 } }
        }
      }
    }
    """ % (network, limit, min_btc, since_date)

    async with _limiter("bitquery", 2):
        try:
            session = await _get_session()
            async with session.post(
                _BITQUERY_URL,
                json={"query": query},
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                transfers = (
                    raw.get("data", {}).get("bitcoin", {}).get("transfers", [])
                )
                data = [
                    {
                        "amount": t.get("amount", 0),
                        "amount_usd": t.get("amountInUSD", 0),
                        "sender": t.get("sender", {}).get("address", ""),
                        "receiver": t.get("receiver", {}).get("address", ""),
                        "timestamp": (
                            t.get("block", {})
                            .get("timestamp", {})
                            .get("iso8601", "")
                        ),
                    }
                    for t in transfers
                ]
                await _cache_set(ck, data, ttl=600)
                _provider_succeeded(
                    "Bitquery",
                    "Whale-transfer feed healthy",
                    optional=True,
                    details={"endpoint": "whale_transfers", "network": network},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Bitquery",
                "Bitquery whale transfers fetch failed",
                exc,
                optional=True,
                details={"endpoint": "whale_transfers", "network": network},
            )
            return []


async def async_fetch_bitquery_dex_trades(
    network: str = "ethereum",
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Recent DEX trades from Bitquery."""
    if not _provider_enabled("enable_bitquery"):
        return _provider_disabled(
            "Bitquery",
            "Disabled in settings",
            [],
            details={"flag": "enable_bitquery"},
        )
    key = _get_key("bitquery_api_key")
    if not key:
        return _provider_disabled(
            "Bitquery",
            "API key not configured",
            [],
            details={"setting": "bitquery_api_key"},
        )
    ck = _cache_key("bq_dex", network, limit)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("Bitquery", [])
    if suppressed is not None:
        return suppressed

    since_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 3600))

    query = """
    {
      ethereum(network: %s) {
        dexTrades(
          options: {limit: %d, desc: "block.height"}
          date: {since: "%s"}
        ) {
          transaction { hash }
          block { height timestamp { iso8601 } }
          buyAmount
          buyCurrency { symbol }
          sellAmount
          sellCurrency { symbol }
          exchange { fullName }
          tradeAmount(in: USD)
        }
      }
    }
    """ % (network, limit, since_date)

    async with _limiter("bitquery", 2):
        try:
            session = await _get_session()
            async with session.post(
                _BITQUERY_URL,
                json={"query": query},
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                trades = (
                    raw.get("data", {}).get("ethereum", {}).get("dexTrades", [])
                )
                data = [
                    {
                        "tx_hash": t.get("transaction", {}).get("hash", ""),
                        "buy_amount": t.get("buyAmount", 0),
                        "buy_currency": t.get("buyCurrency", {}).get("symbol", ""),
                        "sell_amount": t.get("sellAmount", 0),
                        "sell_currency": t.get("sellCurrency", {}).get("symbol", ""),
                        "exchange": t.get("exchange", {}).get("fullName", ""),
                        "trade_amount_usd": t.get("tradeAmount", 0),
                        "timestamp": (
                            t.get("block", {})
                            .get("timestamp", {})
                            .get("iso8601", "")
                        ),
                    }
                    for t in trades
                ]
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "Bitquery",
                    "DEX-trade feed healthy",
                    optional=True,
                    details={"endpoint": "dex_trades", "network": network},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Bitquery",
                "Bitquery DEX trades fetch failed",
                exc,
                optional=True,
                details={"endpoint": "dex_trades", "network": network},
            )
            return []


# ═══════════════════════════════════════════════════════════════
# 7. Alternative.me — Fear & Greed Index
# ═══════════════════════════════════════════════════════════════

async def async_fetch_fear_greed(limit: int = 1) -> Dict[str, Any]:
    """Fetch Crypto Fear & Greed Index from Alternative.me."""
    ck = _cache_key("fng", limit)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("alternativeme"):
        try:
            session = await _get_session()
            async with session.get(
                "https://api.alternative.me/fng/",
                params={"limit": limit, "format": "json"},
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                items = raw.get("data", [])
                if items:
                    item = items[0]
                    data = {
                        "value": int(item.get("value", 50)),
                        "label": item.get("value_classification", "Neutral"),
                        "timestamp": int(item.get("timestamp", 0)),
                    }
                else:
                    data = {"value": 50, "label": "Neutral", "timestamp": 0}
                await _cache_set(ck, data, ttl=600)
                _provider_succeeded(
                    "Alternative.me",
                    "Fear & Greed feed healthy",
                    optional=False,
                    details={"endpoint": "fng", "limit": limit},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Alternative.me",
                "Fear & Greed fetch failed",
                exc,
                optional=False,
                details={"endpoint": "fng", "limit": limit},
            )
            return {"value": 50, "label": "Neutral", "timestamp": 0}


def fetch_fear_greed(limit: int = 1) -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_fear_greed, limit)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_run_sync, async_fetch_fear_greed, limit).result(timeout=15)


async def async_fetch_fear_greed_history(days: int = 30) -> List[Dict[str, Any]]:
    """Fetch Fear & Greed historical data."""
    ck = _cache_key("fng_hist", days)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("alternativeme"):
        try:
            session = await _get_session()
            async with session.get(
                "https://api.alternative.me/fng/",
                params={"limit": days, "format": "json"},
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                data = [
                    {
                        "value": int(d.get("value", 50)),
                        "label": d.get("value_classification", "Neutral"),
                        "timestamp": int(d.get("timestamp", 0)),
                    }
                    for d in raw.get("data", [])
                ]
                await _cache_set(ck, data, ttl=3600)
                _provider_succeeded(
                    "Alternative.me",
                    "Fear & Greed history healthy",
                    optional=False,
                    details={"endpoint": "fng_history", "days": days},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Alternative.me",
                "Fear & Greed history fetch failed",
                exc,
                optional=False,
                details={"endpoint": "fng_history", "days": days},
            )
            return []


# ═══════════════════════════════════════════════════════════════
# 8. Blockchain.com — BTC on-chain stats
# ═══════════════════════════════════════════════════════════════

_BLOCKCHAIN_BASE = "https://api.blockchain.info"


async def async_fetch_blockchain_stats() -> Dict[str, Any]:
    ck = _cache_key("bc_stats")
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("blockchain"):
        try:
            session = await _get_session()
            async with session.get(f"{_BLOCKCHAIN_BASE}/stats") as resp:
                resp.raise_for_status()
                raw = await resp.json()
                data = {
                    "hash_rate": raw.get("hash_rate", 0),
                    "difficulty": raw.get("difficulty", 0),
                    "mempool_size": raw.get("n_tx_total_mem", 0),
                    "avg_block_size": raw.get("avg_block_size", 0),
                    "miners_revenue_usd": raw.get("miners_revenue_usd", 0),
                    "total_btc_sent_24h": raw.get("total_btc_sent", 0) / 1e8,
                    "n_blocks_mined_24h": raw.get("n_blocks_mined", 0),
                    "total_fees_btc": raw.get("total_fees_btc", 0) / 1e8,
                    "market_price_usd": raw.get("market_price_usd", 0),
                }
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "Blockchain.com",
                    "Chain stats feed healthy",
                    optional=False,
                    details={"endpoint": "stats"},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Blockchain.com",
                "Blockchain.com stats fetch failed",
                exc,
                optional=False,
                details={"endpoint": "stats"},
            )
            return {}


def fetch_blockchain_stats() -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_blockchain_stats)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_run_sync, async_fetch_blockchain_stats).result(timeout=15)


async def async_fetch_blockchain_mempool() -> Dict[str, Any]:
    ck = _cache_key("bc_mempool")
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("Blockchain.com", {"unconfirmed_tx_count": 0})
    if suppressed is not None:
        return suppressed
    async with _limiter("blockchain"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_BLOCKCHAIN_BASE}/q/unconfirmedcount"
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
                count = int(text.strip())
                data = {"unconfirmed_tx_count": count}
                await _cache_set(ck, data, ttl=120)
                _provider_succeeded(
                    "Blockchain.com",
                    "Mempool feed healthy",
                    optional=False,
                    details={"endpoint": "mempool"},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Blockchain.com",
                "Blockchain mempool fetch failed",
                exc,
                optional=False,
                details={"endpoint": "mempool"},
            )
            return {"unconfirmed_tx_count": 0}


def fetch_blockchain_mempool() -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_blockchain_mempool)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_run_sync, async_fetch_blockchain_mempool).result(timeout=15)


# ═══════════════════════════════════════════════════════════════
# 9. Messari
# ═══════════════════════════════════════════════════════════════

_MESSARI_BASE = "https://data.messari.io/api"


async def async_fetch_messari_news() -> List[Dict[str, Any]]:
    """Fetch latest crypto news from Messari (free, no key)."""
    ck = _cache_key("messari_news")
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("Messari", [])
    if suppressed is not None:
        return suppressed
    async with _limiter("messari"):
        try:
            session = await _get_session()
            async with session.get(f"{_MESSARI_BASE}/v1/news/") as resp:
                if resp.status == 404:
                    logger.debug("Messari news endpoint deprecated (404) — skipping")
                    mark_provider_disabled(
                        "Messari",
                        "News endpoint deprecated",
                        category="data",
                        configured=False,
                        optional=True,
                        details={"endpoint": "news"},
                    )
                    suppress_provider(
                        "Messari",
                        "Temporarily suppressing deprecated Messari news endpoint",
                        cooldown_sec=21600,
                        category="data",
                        configured=False,
                        optional=True,
                        details={"endpoint": "news", "status": 404},
                    )
                    return []
                resp.raise_for_status()
                raw = await resp.json()
                articles = raw.get("data", [])
                data = [
                    {
                        "title": a.get("title", ""),
                        "url": a.get("url", ""),
                        "published_at": a.get("published_at", ""),
                        "author": a.get("author", {}).get("name", ""),
                    }
                    for a in articles[:20]
                ]
                await _cache_set(ck, data, ttl=600)
                _provider_succeeded(
                    "Messari",
                    "News feed healthy",
                    optional=True,
                    details={"endpoint": "news"},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Messari",
                "Messari news fetch failed",
                exc,
                optional=True,
                details={"endpoint": "news"},
            )
            return []


async def async_fetch_messari_asset_metrics(asset: str = "bitcoin") -> Dict[str, Any]:
    """Fetch asset metrics from Messari (ROI, volatility, etc.)."""
    ck = _cache_key("messari_metrics", asset)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("messari"):
        try:
            session = await _get_session()
            async with session.get(
                f"{_MESSARI_BASE}/v1/assets/{asset}/metrics"
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                d = raw.get("data", {})
                md = d.get("market_data", {})
                roi = d.get("roi_data", {})
                data = {
                    "price_usd": md.get("price_usd", 0),
                    "volume_24h": md.get("volume_last_24_hours", 0),
                    "volatility_30d": md.get("volatility_last_30_days", 0),
                    "roi_1w": roi.get("percent_change_last_1_week", 0),
                    "roi_1m": roi.get("percent_change_last_1_month", 0),
                    "roi_3m": roi.get("percent_change_last_3_months", 0),
                    "roi_1y": roi.get("percent_change_last_1_year", 0),
                }
                await _cache_set(ck, data, ttl=300)
                _provider_succeeded(
                    "Messari",
                    "Asset-metrics feed healthy",
                    optional=True,
                    details={"endpoint": "asset_metrics", "asset": asset},
                )
                return data
        except Exception as exc:
            _provider_failed(
                "Messari",
                "Messari asset metrics fetch failed",
                exc,
                optional=True,
                details={"endpoint": "asset_metrics", "asset": asset},
            )
            return {}


# ═══════════════════════════════════════════════════════════════
# 10. Yahoo Finance (prices + Yahoo-hosted news via yfinance)
# ═══════════════════════════════════════════════════════════════

def _normalise_yahoo_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if "-" in symbol:
        return symbol
    if symbol.endswith("USD") and len(symbol) > 3:
        return f"{symbol[:-3]}-USD"
    return f"{symbol}-USD"


def _extract_yahoo_article(item: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    content = item.get("content", {}) if isinstance(item.get("content"), dict) else {}
    provider = content.get("provider", {}) if isinstance(content.get("provider"), dict) else {}
    canonical = content.get("clickThroughUrl") or content.get("canonicalUrl") or {}

    url = ""
    if isinstance(canonical, dict):
        url = canonical.get("url", "")
    elif isinstance(canonical, str):
        url = canonical

    return {
        "title": content.get("title") or item.get("title", ""),
        "summary": content.get("summary") or content.get("description") or item.get("summary", ""),
        "source": provider.get("displayName") or "Yahoo Finance",
        "url": url,
        "published_at": content.get("pubDate") or item.get("providerPublishTime") or "",
        "symbol": symbol,
    }


async def async_fetch_yahoo_finance_prices(
    symbols: Optional[List[str]] = None,
) -> Dict[str, Dict[str, float]]:
    """Fetch latest Yahoo Finance crypto prices as a free cross-check/fallback."""
    yahoo_symbols = [_normalise_yahoo_symbol(symbol) for symbol in (symbols or ["BTC-USD", "ETH-USD"])]
    ck = _cache_key("yahoo_prices", ",".join(yahoo_symbols))
    cached = await _cache_get(ck)
    if cached:
        return cached

    def _fetch_sync() -> Dict[str, Dict[str, float]]:
        import yfinance as yf

        prices: Dict[str, Dict[str, float]] = {}
        for symbol in yahoo_symbols:
            history = yf.Ticker(symbol).history(period="2d", interval="1d", auto_adjust=False)
            if history is None or history.empty:
                continue
            closes = history["Close"].dropna()
            if closes.empty:
                continue
            price = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2]) if len(closes) > 1 else price
            change_pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
            prices[symbol] = {
                "price": price,
                "change_pct_24h": change_pct,
                "previous_close": prev_close,
            }
        return prices

    try:
        data = await asyncio.to_thread(_fetch_sync)
        await _cache_set(ck, data, ttl=120)
        _provider_succeeded(
            "Yahoo Finance",
            "Price cross-check healthy",
            optional=False,
            details={"symbols": yahoo_symbols},
        )
        return data
    except Exception as exc:
        _provider_failed(
            "Yahoo Finance",
            "Yahoo Finance price fetch failed",
            exc,
            optional=False,
            details={"symbols": yahoo_symbols},
        )
        return {}


async def async_fetch_yahoo_finance_news(
    symbols: Optional[List[str]] = None,
    max_per_symbol: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch Yahoo-hosted finance and crypto news through yfinance."""
    yahoo_symbols = [_normalise_yahoo_symbol(symbol) for symbol in (symbols or ["BTC-USD", "ETH-USD"])]
    ck = _cache_key("yahoo_news", ",".join(yahoo_symbols), max_per_symbol)
    cached = await _cache_get(ck)
    if cached:
        return cached

    def _fetch_sync() -> List[Dict[str, Any]]:
        import yfinance as yf

        articles: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        for symbol in yahoo_symbols:
            news_items = yf.Ticker(symbol).news or []
            for item in news_items[:max_per_symbol]:
                article = _extract_yahoo_article(item, symbol)
                url = article.get("url", "").strip().lower()
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                articles.append(article)
        return articles

    try:
        data = await asyncio.to_thread(_fetch_sync)
        await _cache_set(ck, data, ttl=300)
        _provider_succeeded(
            "Yahoo Finance",
            "News feed healthy",
            optional=False,
            details={"symbols": yahoo_symbols},
        )
        return data
    except Exception as exc:
        _provider_failed(
            "Yahoo Finance",
            "Yahoo Finance news fetch failed",
            exc,
            optional=False,
            details={"symbols": yahoo_symbols},
        )
        return []


def _dedupe_news_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}
    for article in articles:
        url = str(article.get("url", "")).strip().lower()
        title = " ".join(str(article.get("title", "")).strip().lower().split())
        if not url and not title:
            continue
        identity = url or title
        unique.setdefault(identity, article)
    return list(unique.values())


# ═══════════════════════════════════════════════════════════════
# 11. RSS Feeds (CoinDesk, Cointelegraph, Decrypt, TheBlock, Bitcoin Mag)
# ═══════════════════════════════════════════════════════════════

_RSS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("TheBlock", "https://www.theblock.co/rss.xml"),
    ("BitcoinMagazine", "https://bitcoinmagazine.com/.rss/full/"),
]


async def async_fetch_rss_news(max_per_feed: int = 5) -> List[Dict[str, Any]]:
    """Fetch latest articles from 5 crypto RSS feeds."""
    ck = _cache_key("rss_news", max_per_feed)
    cached = await _cache_get(ck)
    if cached:
        return cached

    import feedparser

    all_articles: List[Dict[str, Any]] = []
    session = await _get_session()

    for source_name, url in _RSS_FEEDS:
        try:
            async with _limiter("rss"):
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()
            feed = feedparser.parse(text)
            for entry in feed.entries[:max_per_feed]:
                all_articles.append(
                    {
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", "")[:300],
                        "source": source_name,
                        "url": entry.get("link", ""),
                        "published_at": entry.get("published", ""),
                    }
                )
        except Exception as exc:
            logger.debug("RSS feed %s failed: %s", source_name, exc)

    await _cache_set(ck, all_articles, ttl=300)
    if all_articles:
        _provider_succeeded(
            "RSS Feeds",
            "RSS aggregation healthy",
            optional=True,
            details={"feeds": len(_RSS_FEEDS), "articles": len(all_articles)},
        )
    else:
        mark_provider_failure(
            "RSS Feeds",
            "No RSS articles collected",
            category="data",
            configured=True,
            optional=True,
            details={"feeds": len(_RSS_FEEDS)},
        )
    return all_articles


def fetch_crypto_news() -> List[Dict[str, Any]]:
    """Sync wrapper for RSS news (backward compat)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_rss_news)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_run_sync, async_fetch_rss_news).result(timeout=30)


# ═══════════════════════════════════════════════════════════════
# Aggregated market overview (backward compatible)
# ═══════════════════════════════════════════════════════════════

async def async_fetch_market_overview() -> Dict[str, Any]:
    """Aggregate data from CoinGecko + Blockchain.com + Fear&Greed into
    a single market overview dict. Enhanced with CryptoCompare + Yahoo Finance."""
    from data.macro_feeds import fetch_macro_snapshot

    overview: Dict[str, Any] = {}

    # Parallel fetch
    cg_price, cg_global, bc_stats, fng, cc_price, yahoo_prices, macro_snapshot = await asyncio.gather(
        async_fetch_coingecko_price("bitcoin,ethereum"),
        async_fetch_coingecko_global(),
        async_fetch_blockchain_stats(),
        async_fetch_fear_greed(),
        async_fetch_cryptocompare_price("BTC", "USD"),
        async_fetch_yahoo_finance_prices(["BTC-USD", "ETH-USD"]),
        asyncio.to_thread(fetch_macro_snapshot),
        return_exceptions=True,
    )

    # CoinGecko prices
    if isinstance(cg_price, dict):
        overview["btc_price"] = cg_price.get("bitcoin", {}).get("usd", 0)
        overview["eth_price"] = cg_price.get("ethereum", {}).get("usd", 0)
        overview["btc_24h_change"] = cg_price.get("bitcoin", {}).get("usd_24h_change", 0)
        overview["eth_24h_change"] = cg_price.get("ethereum", {}).get("usd_24h_change", 0)
        overview["btc_market_cap"] = cg_price.get("bitcoin", {}).get("usd_market_cap", 0)
        overview["btc_volume_24h"] = cg_price.get("bitcoin", {}).get("usd_24h_vol", 0)

    # CoinGecko global
    if isinstance(cg_global, dict):
        overview["btc_dominance"] = cg_global.get("btc_dominance", 0)
        overview["eth_dominance"] = cg_global.get("eth_dominance", 0)
        overview["total_market_cap"] = cg_global.get("total_market_cap_usd", 0)
        overview["market_cap_change_24h"] = cg_global.get("market_cap_change_24h_pct", 0)
        overview["active_coins"] = cg_global.get("active_coins", 0)

    # Blockchain.com
    if isinstance(bc_stats, dict):
        overview["btc_hash_rate"] = bc_stats.get("hash_rate", 0)
        overview["btc_mempool"] = bc_stats.get("mempool_size", 0)
        overview["btc_difficulty"] = bc_stats.get("difficulty", 0)
        overview["btc_miners_revenue"] = bc_stats.get("miners_revenue_usd", 0)

    # Fear & Greed
    if isinstance(fng, dict):
        overview["fear_greed_value"] = fng.get("value", 50)
        overview["fear_greed_label"] = fng.get("label", "Neutral")

    # CryptoCompare crosscheck
    if isinstance(cc_price, dict) and cc_price.get("price"):
        overview["btc_price_cc"] = cc_price.get("price", 0)
        overview["btc_cc_change_pct_24h"] = cc_price.get("change_pct_24h", 0)

    # Yahoo Finance crosscheck / fallback
    if isinstance(yahoo_prices, dict):
        btc_yahoo = yahoo_prices.get("BTC-USD", {})
        eth_yahoo = yahoo_prices.get("ETH-USD", {})

        if btc_yahoo:
            overview["btc_price_yahoo"] = btc_yahoo.get("price", 0)
            overview["btc_yahoo_change_pct_24h"] = btc_yahoo.get("change_pct_24h", 0)
            if not overview.get("btc_price"):
                overview["btc_price"] = btc_yahoo.get("price", 0)
            if not overview.get("btc_24h_change"):
                overview["btc_24h_change"] = btc_yahoo.get("change_pct_24h", 0)

        if eth_yahoo:
            overview["eth_price_yahoo"] = eth_yahoo.get("price", 0)
            overview["eth_yahoo_change_pct_24h"] = eth_yahoo.get("change_pct_24h", 0)
            if not overview.get("eth_price"):
                overview["eth_price"] = eth_yahoo.get("price", 0)
            if not overview.get("eth_24h_change"):
                overview["eth_24h_change"] = eth_yahoo.get("change_pct_24h", 0)

    # Yahoo macro snapshot (also backed by yfinance)
    if isinstance(macro_snapshot, dict):
        for key, value in macro_snapshot.items():
            overview[f"macro_{key}"] = value if value is not None else 0.0

    return overview


def fetch_market_overview() -> Dict[str, Any]:
    """Sync wrapper — backward compat for dashboard."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_sync(async_fetch_market_overview)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(_run_sync, async_fetch_market_overview).result(timeout=30)


# ═══════════════════════════════════════════════════════════════
# Multi-source news aggregation (for Sentinel)
# ═══════════════════════════════════════════════════════════════

async def async_fetch_all_news() -> List[Dict[str, Any]]:
    """Aggregate news from all 6 sources: RSS, Messari, NewsAPI, NewsData, CryptoCompare, Yahoo Finance.
    Returns unified list with 'title', 'source', 'published_at', 'url'."""
    results = await asyncio.gather(
        async_fetch_rss_news(),
        async_fetch_messari_news(),
        async_fetch_newsapi(),
        async_fetch_newsdata(),
        async_fetch_cryptocompare_news(),
        async_fetch_yahoo_finance_news(),
        return_exceptions=True,
    )

    all_news: List[Dict[str, Any]] = []
    source_names = ["RSS", "Messari", "NewsAPI", "NewsData", "CryptoCompare", "YahooFinance"]
    for i, batch in enumerate(results):
        if isinstance(batch, list):
            for article in batch:
                normalised = dict(article)
                normalised["_provider"] = source_names[i]
                all_news.append(normalised)

    all_news = _dedupe_news_articles(all_news)

    # Sort by published_at if available (best effort)
    # Some providers return int timestamps, others return date strings
    all_news.sort(key=lambda a: str(a.get("published_at", "")), reverse=True)
    return all_news
