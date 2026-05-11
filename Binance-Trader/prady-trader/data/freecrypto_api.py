"""
PRADY TRADER — FreeCryptoAPI Integration.

Base URL: https://api.freecryptoapi.com/v1
Auth: Bearer token in Authorization header
Free tier: 100,000 requests/month

Endpoints used:
  /getData       — Real-time price, change, market cap, volume, RSI, signal
  /getNews       — Crypto news with source & keyword filtering
  /getTechnicalAnalysis — MACD, signal line, RSI
  /getBreakouts  — 20/50/200 SMA crossover detection
  /getFearGreed  — Fear & Greed index
  /getOHLC       — Daily OHLC candles (up to 365 days)
  /getBollinger  — Bollinger Bands with squeeze detection
  /getSupportResistance — Pivot, Fibonacci, Camarilla, Woodie
  /getCorrelation — Pearson correlation between assets
  /getTop        — Top 200 coins ranked data
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
import requests

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

logger = logging.getLogger("prady.data.freecrypto_api")

_BASE = "https://api.freecryptoapi.com/v1"
_TIMEOUT = aiohttp.ClientTimeout(total=12)


def _endpoint_provider_name(endpoint: str) -> str:
    endpoint_key = endpoint.strip("/") or "root"
    return f"FreeCryptoAPI {endpoint_key}"


def _is_plan_limited_error(message: str) -> bool:
    lowered = str(message or "").lower()
    return "upgrade your subscription" in lowered or "no access" in lowered


def _log_failure(provider_name: str, message: str, exc: Exception) -> None:
    settings = get_settings()
    cooldown = int(getattr(settings, "provider_warning_cooldown_sec", 300) or 300)
    startup_grace = int(getattr(settings, "provider_startup_grace_sec", 180) or 180)
    if should_emit_runtime_warning(
        provider_name,
        cooldown_sec=cooldown,
        startup_grace_sec=startup_grace,
        warn_after_failures=2,
    ):
        logger.warning("%s: %s", message, exc)
    else:
        logger.debug("%s: %s", message, exc)


def _is_success_status(status: Any) -> bool:
    if isinstance(status, str):
        return status.lower() in {"success", "ok", "true"}
    return bool(status)


def _maybe_suppress_provider(
    provider_name: str,
    endpoint: str,
    message: str,
    failures: int,
    *,
    configured: bool,
) -> None:
    cooldown = int(getattr(get_settings(), "provider_warning_cooldown_sec", 300) or 300)
    backoff = recommended_suppression_seconds(message, default_cooldown=cooldown)
    threshold = 1 if backoff >= 3600 else 2
    if backoff > 0 and failures >= threshold:
        suppress_provider(
            provider_name,
            "Temporarily suppressing FreeCryptoAPI after repeated failures",
            cooldown_sec=backoff,
            category="data",
            configured=configured,
            optional=True,
            details={"endpoint": endpoint, "error": message},
        )


def _normalize_payload(endpoint: str, data: Any) -> Dict[str, Any]:
    endpoint_provider = _endpoint_provider_name(endpoint)
    if not isinstance(data, dict):
        record = mark_provider_failure(
            endpoint_provider,
            f"Non-dict payload for {endpoint}",
            category="data",
            configured=True,
            optional=True,
            details={"endpoint": endpoint, "payload_type": type(data).__name__},
        )
        _maybe_suppress_provider(
            endpoint_provider,
            endpoint,
            f"Non-dict payload for {endpoint}",
            int(record.get("consecutive_failures", 0) or 0),
            configured=True,
        )
        logger.debug("FreeCryptoAPI %s returned non-dict payload: %s", endpoint, type(data).__name__)
        return {}

    if not _is_success_status(data.get("status", True)):
        error_message = str(data.get("error") or data)
        if _is_plan_limited_error(error_message):
            mark_provider_disabled(
                endpoint_provider,
                f"{endpoint} not available on current FreeCryptoAPI plan",
                category="data",
                configured=True,
                optional=True,
                details={"endpoint": endpoint, "payload": data},
            )
            logger.info("FreeCryptoAPI %s unavailable on current plan: %s", endpoint, error_message)
            return {}

        record = mark_provider_failure(
            endpoint_provider,
            f"Error payload for {endpoint}",
            category="data",
            configured=True,
            optional=True,
            details={"endpoint": endpoint, "payload": data},
        )
        _maybe_suppress_provider(
            endpoint_provider,
            endpoint,
            error_message,
            int(record.get("consecutive_failures", 0) or 0),
            configured=True,
        )
        logger.debug("FreeCryptoAPI %s returned error payload: %s", endpoint, data)
        return {}

    mark_provider_success(
        endpoint_provider,
        f"{endpoint} healthy",
        category="data",
        configured=True,
        optional=True,
        details={"endpoint": endpoint},
    )
    mark_provider_success(
        "FreeCryptoAPI",
        f"{endpoint} healthy",
        category="data",
        configured=True,
        optional=True,
        details={"endpoint": endpoint},
    )

    return data


def _sync_get_json(url: str, params: Optional[Dict[str, Any]], headers: Dict[str, str]) -> Dict[str, Any]:
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _headers() -> Dict[str, str]:
    key = get_settings().freecrypto_api_key
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


async def _get(endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    """Generic GET request to FreeCryptoAPI."""
    endpoint_provider = _endpoint_provider_name(endpoint)
    if not bool(getattr(get_settings(), "enable_freecrypto", True)):
        mark_provider_disabled(
            "FreeCryptoAPI",
            "Disabled in settings",
            category="data",
            configured=False,
            optional=True,
            details={"flag": "enable_freecrypto"},
        )
        return {}
    hdrs = _headers()
    if not hdrs:
        logger.debug("FreeCryptoAPI key not set — skipping %s", endpoint)
        mark_provider_disabled(
            "FreeCryptoAPI",
            "API key not configured",
            category="data",
            configured=False,
            optional=True,
            details={"setting": "freecrypto_api_key", "endpoint": endpoint},
        )
        return {}
    if is_provider_suppressed(endpoint_provider):
        logger.debug("%s temporarily suppressed — skipping %s", endpoint_provider, endpoint)
        return {}
    url = f"{_BASE}{endpoint}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=hdrs, timeout=_TIMEOUT
            ) as resp:
                data = await resp.json(content_type=None)
                return _normalize_payload(endpoint, data)
    except Exception as exc:
        record = mark_provider_failure(
            endpoint_provider,
            f"aiohttp transport failed for {endpoint}",
            category="data",
            configured=True,
            optional=True,
            details={"endpoint": endpoint, "transport": "aiohttp"},
        )
        _maybe_suppress_provider(
            endpoint_provider,
            endpoint,
            str(exc),
            int(record.get("consecutive_failures", 0) or 0),
            configured=True,
        )
        _log_failure(
            endpoint_provider,
            f"FreeCryptoAPI {endpoint} aiohttp failed, retrying with requests",
            exc,
        )

    try:
        data = await asyncio.to_thread(_sync_get_json, url, params, hdrs)
        return _normalize_payload(endpoint, data)
    except Exception as exc:
        record = mark_provider_failure(
            endpoint_provider,
            f"requests fallback failed for {endpoint}",
            category="data",
            configured=True,
            optional=True,
            details={"endpoint": endpoint, "transport": "requests"},
        )
        _maybe_suppress_provider(
            endpoint_provider,
            endpoint,
            str(exc),
            int(record.get("consecutive_failures", 0) or 0),
            configured=True,
        )
        _log_failure(endpoint_provider, f"FreeCryptoAPI {endpoint} requests fallback failed", exc)
        return {}


# ── Market Data ──────────────────────────────────────────────


async def get_live_data(symbols: str = "BTC+ETH") -> Dict[str, Any]:
    """Get real-time price, change_24h, market_cap, volume, RSI, signal.
    Symbols separated by + (e.g. BTC+ETH+SOL).
    """
    return await _get("/getData", {"symbol": symbols})


async def get_top_coins(top: int = 50) -> Dict[str, Any]:
    """Get ranked top coins with live data."""
    return await _get("/getTop", {"top": top})


async def get_fear_greed() -> Dict[str, Any]:
    """Get Fear & Greed index."""
    return await _get("/getFearGreed")


# ── Technical Analysis ───────────────────────────────────────


async def get_technical_analysis(symbol: str = "BTC") -> Dict[str, Any]:
    """Get MACD, signal line, RSI for a symbol."""
    return await _get("/getTechnicalAnalysis", {"symbol": symbol})


async def get_breakouts(symbol: Optional[str] = None) -> Dict[str, Any]:
    """Get 20/50/200 SMA breakout signals.
    If symbol is None, returns top 200 coins.
    """
    params = {"symbol": symbol} if symbol else {}
    return await _get("/getBreakouts", params)


async def get_bollinger(symbol: str = "BTC", days: int = 90) -> Dict[str, Any]:
    """Bollinger Bands with squeeze & expansion detection."""
    return await _get("/getBollinger", {"symbol": symbol, "days": days})


async def get_support_resistance(symbol: str = "BTC", period: int = 30) -> Dict[str, Any]:
    """Support & resistance: Pivot, Fibonacci, Camarilla, Woodie."""
    return await _get("/getSupportResistance", {"symbol": symbol, "period": period})


async def get_correlation(symbols: str = "BTC,ETH,SOL", days: int = 90) -> Dict[str, Any]:
    """Pearson correlation between 2-10 crypto assets."""
    return await _get("/getCorrelation", {"symbols": symbols, "days": days})


async def get_ma_ribbon(symbol: str = "BTC", days: int = 90) -> Dict[str, Any]:
    """Moving Average Ribbon (SMA & EMA for 10/20/50/100/200 periods)."""
    return await _get("/getMARibbon", {"symbol": symbol, "days": days})


# ── Historical Data ──────────────────────────────────────────


async def get_ohlc(symbol: str = "BTC", days: int = 30) -> Dict[str, Any]:
    """Daily OHLC candles (max 365 days)."""
    return await _get("/getOHLC", {"symbol": symbol, "days": days})


async def get_history(symbol: str = "BTC", days: int = 30) -> Dict[str, Any]:
    """Last X days of historical data."""
    return await _get("/getHistory", {"symbol": symbol, "days": days})


# ── News ─────────────────────────────────────────────────────


async def get_news(
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get latest crypto news articles with filtering."""
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if source:
        params["source"] = source
    if search:
        params["search"] = search
    return await _get("/getNews", params)


# ── Convenience wrappers ─────────────────────────────────────


async def get_btc_summary() -> Dict[str, Any]:
    """Quick BTC summary: price, RSI, Fear & Greed, breakouts."""
    import asyncio
    data, fg, ta = await asyncio.gather(
        get_live_data("BTC"),
        get_fear_greed(),
        get_technical_analysis("BTC"),
    )
    return {"live": data, "fear_greed": fg, "technical": ta}
