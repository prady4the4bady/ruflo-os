"""
PRADY TRADER — Crypto Indicators & Multi-Exchange API.

Provides technical indicators and price data from multiple free sources:
 1. TAAPI.IO — RSI, MACD, Bollinger, EMA, SMA (free: 1 req/15s)
 2. CoinCodex — coin detail, predictions
 3. CoinStats — portfolio-grade coin data
 4. CryptoRank — market rankings
 5. CoinLore — global + ticker data (no key needed)
 6. Multi-exchange price aggregation (Binance + CoinGecko + CryptoCompare)

All functions are async with Redis caching + in-memory fallback.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from typing import Any, Dict, List, Optional

import aiohttp
import pandas as pd

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*copy_on_write.*")
    import pandas_ta as ta

from config.constants import (
    BOLLINGER_PERIOD,
    BOLLINGER_STD,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    RSI_PERIOD,
)
from config.settings import get_settings
from data.data_store import get_data_store
from data.free_apis import (
    _cache_get,
    _cache_key,
    _cache_set,
    _get_key,
    _get_session,
    _limiter,
)
from utils.provider_status import (
    is_provider_suppressed,
    mark_provider_disabled,
    mark_provider_failure,
    recommended_suppression_seconds,
    should_emit_runtime_warning,
    suppress_provider,
)

logger = logging.getLogger("prady.data.crypto_indicators")


def _provider_temporarily_suppressed(provider: str, default: Any) -> Any | None:
    if not is_provider_suppressed(provider):
        return None
    logger.debug("%s temporarily suppressed after recent failures", provider)
    return default


def _log_provider_failure(provider: str, message: str, exc: Exception) -> None:
    settings = get_settings()
    cooldown = int(getattr(settings, "provider_warning_cooldown_sec", 300) or 300)
    startup_grace = int(getattr(settings, "provider_startup_grace_sec", 180) or 180)
    if should_emit_runtime_warning(
        provider,
        cooldown_sec=cooldown,
        startup_grace_sec=startup_grace,
        warn_after_failures=2,
    ):
        logger.warning("%s: %s", message, exc)
    else:
        logger.debug("%s: %s", message, exc)


def _maybe_suppress_provider(provider: str, message: str, failures: int, *, details: Dict[str, Any]) -> None:
    cooldown = int(getattr(get_settings(), "provider_warning_cooldown_sec", 300) or 300)
    backoff = recommended_suppression_seconds(message, default_cooldown=cooldown)
    threshold = 1 if backoff >= 3600 else 2
    if backoff > 0 and failures >= threshold:
        suppress_provider(
            provider,
            f"Temporarily suppressing {provider} after repeated failures",
            cooldown_sec=backoff,
            category="data",
            configured=True,
            optional=True,
            details={**details, "error": message},
        )


# ═══════════════════════════════════════════════════════════════
# 1. TAAPI.IO — Technical Indicators
# ═══════════════════════════════════════════════════════════════

_TAAPI_BASE = "https://api.taapi.io"
_LOCAL_TA_FALLBACK_TTL_SEC = 45


def _normalize_market_symbol(symbol: str) -> str:
    return str(symbol or "BTCUSDT").upper().replace("/", "").replace("-", "")


def _local_indicator_min_rows() -> int:
    return max(RSI_PERIOD + 5, MACD_SLOW + MACD_SIGNAL + 5, BOLLINGER_PERIOD + 5)


def _klines_to_dataframe(klines: List[List[Any]]) -> pd.DataFrame:
    rows = [
        {
            "timestamp": int(kline[0]),
            "open": float(kline[1]),
            "high": float(kline[2]),
            "low": float(kline[3]),
            "close": float(kline[4]),
            "volume": float(kline[5]),
        }
        for kline in klines
    ]
    return pd.DataFrame(rows)


def _resolve_indicator_frame(symbol: str, interval: str) -> pd.DataFrame:
    normalized_symbol = _normalize_market_symbol(symbol)
    store = get_data_store()
    frame = store.get_dataframe(normalized_symbol, interval, limit=300)
    min_rows = _local_indicator_min_rows()
    if len(frame) >= min_rows:
        return frame

    try:
        from data.binance_client import BinanceClientWrapper

        klines = BinanceClientWrapper().get_klines(
            symbol=normalized_symbol,
            interval=interval,
            limit=max(200, min_rows + 20),
        )
    except Exception as exc:
        logger.debug("Local indicator fetch failed for %s %s: %s", normalized_symbol, interval, exc)
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()

    if not klines:
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    return _klines_to_dataframe(klines)


def _compute_local_indicator_snapshot(symbol: str, interval: str) -> Dict[str, Any]:
    frame = _resolve_indicator_frame(symbol, interval)
    if frame is None or frame.empty or len(frame) < _local_indicator_min_rows():
        return {}

    close = pd.to_numeric(frame["close"], errors="coerce")
    if close.isna().all():
        return {}

    rsi_series = ta.rsi(close, length=RSI_PERIOD)
    macd_df = ta.macd(close, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    bb_df = ta.bbands(
        close,
        length=BOLLINGER_PERIOD,
        lower_std=BOLLINGER_STD,
        upper_std=BOLLINGER_STD,
    )

    snapshot: Dict[str, Any] = {}

    if rsi_series is not None and not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]):
        snapshot["rsi"] = float(rsi_series.iloc[-1])

    if macd_df is not None and not macd_df.empty:
        cols = macd_df.columns.tolist()
        macd_col = next((col for col in cols if "MACD_" in col and "MACDs" not in col and "MACDh" not in col), None)
        signal_col = next((col for col in cols if "MACDs" in col), None)
        hist_col = next((col for col in cols if "MACDh" in col), None)
        if macd_col and signal_col:
            macd_val = macd_df[macd_col].iloc[-1]
            signal_val = macd_df[signal_col].iloc[-1]
            hist_val = macd_df[hist_col].iloc[-1] if hist_col else 0.0
            if not pd.isna(macd_val) and not pd.isna(signal_val):
                snapshot["macd"] = {
                    "macd": float(macd_val),
                    "signal": float(signal_val),
                    "histogram": float(hist_val) if not pd.isna(hist_val) else 0.0,
                }

    if bb_df is not None and not bb_df.empty:
        cols = bb_df.columns.tolist()
        lower_col = next((col for col in cols if "BBL_" in col), None)
        mid_col = next((col for col in cols if "BBM_" in col), None)
        upper_col = next((col for col in cols if "BBU_" in col), None)
        if lower_col and mid_col and upper_col:
            lower_val = bb_df[lower_col].iloc[-1]
            mid_val = bb_df[mid_col].iloc[-1]
            upper_val = bb_df[upper_col].iloc[-1]
            if not pd.isna(lower_val) and not pd.isna(mid_val) and not pd.isna(upper_val):
                snapshot["bbands"] = {
                    "upper": float(upper_val),
                    "middle": float(mid_val),
                    "lower": float(lower_val),
                }

    return snapshot


async def _async_fetch_local_indicator_snapshot(symbol: str, interval: str) -> Dict[str, Any]:
    normalized_symbol = _normalize_market_symbol(symbol)
    cache_key = _cache_key("local_ta_fallback", normalized_symbol, interval)
    cached = await _cache_get(cache_key)
    if isinstance(cached, dict) and cached:
        return cached

    snapshot = _compute_local_indicator_snapshot(normalized_symbol, interval)
    if snapshot:
        await _cache_set(cache_key, snapshot, ttl=_LOCAL_TA_FALLBACK_TTL_SEC)
    return snapshot


async def async_fetch_taapi_indicator(
    indicator: str = "rsi",
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    interval: str = "1h",
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Fetch a technical indicator from TAAPI.IO.
    Supported: rsi, macd, bbands, ema, sma, stoch, atr, adx, cci, willr, etc.
    """
    secret = _get_key("taapi_secret")
    if not secret:
        return {}

    suppressed = _provider_temporarily_suppressed("TAAPI", {})
    if suppressed is not None:
        return suppressed

    ck = _cache_key("taapi", indicator, symbol, exchange, interval, str(params))
    cached = await _cache_get(ck)
    if cached:
        return cached

    async with _limiter("taapi", 1):  # free tier: 1 req/15s
        try:
            p = {
                "secret": secret,
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
            }
            if params:
                p.update(params)

            session = await _get_session()
            async with session.get(
                f"{_TAAPI_BASE}/{indicator}", params=p
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                await _cache_set(ck, data, ttl=60)
                return data
        except Exception as exc:
            record = mark_provider_failure(
                "TAAPI",
                str(exc),
                category="data",
                configured=True,
                optional=True,
                details={"indicator": indicator, "symbol": symbol, "interval": interval},
            )
            _maybe_suppress_provider(
                "TAAPI",
                str(exc),
                int(record.get("consecutive_failures", 0) or 0),
                details={"indicator": indicator, "symbol": symbol, "interval": interval},
            )
            _log_provider_failure("TAAPI", f"TAAPI {indicator} fetch failed", exc)
            return {}


async def async_fetch_taapi_rsi(
    symbol: str = "BTC/USDT", interval: str = "1h"
) -> float:
    """Get RSI value from TAAPI."""
    data = await async_fetch_taapi_indicator("rsi", symbol, interval=interval)
    if data:
        return float(data.get("value", 50.0))

    local = await _async_fetch_local_indicator_snapshot(symbol, interval)
    return float(local.get("rsi", 50.0))


async def async_fetch_taapi_macd(
    symbol: str = "BTC/USDT", interval: str = "1h"
) -> Dict[str, float]:
    """Get MACD values from TAAPI."""
    data = await async_fetch_taapi_indicator("macd", symbol, interval=interval)
    if not data:
        local = await _async_fetch_local_indicator_snapshot(symbol, interval)
        return dict(local.get("macd") or {"macd": 0.0, "signal": 0.0, "histogram": 0.0})
    return {
        "macd": float(data.get("valueMACD", 0)),
        "signal": float(data.get("valueMACDSignal", 0)),
        "histogram": float(data.get("valueMACDHist", 0)),
    }


async def async_fetch_taapi_bbands(
    symbol: str = "BTC/USDT", interval: str = "1h"
) -> Dict[str, float]:
    """Get Bollinger Bands from TAAPI."""
    data = await async_fetch_taapi_indicator("bbands", symbol, interval=interval)
    if not data:
        local = await _async_fetch_local_indicator_snapshot(symbol, interval)
        return dict(local.get("bbands") or {"upper": 0.0, "middle": 0.0, "lower": 0.0})
    return {
        "upper": float(data.get("valueUpperBand", 0)),
        "middle": float(data.get("valueMiddleBand", 0)),
        "lower": float(data.get("valueLowerBand", 0)),
    }


async def async_fetch_taapi_bulk(
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    indicators: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fetch multiple indicators in one call (TAAPI bulk endpoint).
    Free tier may not support this — falls back to sequential calls."""
    if indicators is None:
        indicators = ["rsi", "macd", "bbands", "ema", "sma"]

    secret = _get_key("taapi_secret")
    if not secret:
        return {}

    ck = _cache_key("taapi_bulk", symbol, interval, ",".join(indicators))
    cached = await _cache_get(ck)
    if cached:
        return cached

    # Try bulk endpoint first
    async with _limiter("taapi", 1):
        try:
            session = await _get_session()
            construct = [{"indicator": ind} for ind in indicators]
            payload = {
                "secret": secret,
                "construct": {
                    "exchange": "binance",
                    "symbol": symbol,
                    "interval": interval,
                    "indicators": construct,
                },
            }
            async with session.post(
                f"{_TAAPI_BASE}/bulk", json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = {}
                    for item in data.get("data", []):
                        ind_name = item.get("indicator", "")
                        result[ind_name] = item.get("result", {})
                    await _cache_set(ck, result, ttl=60)
                    return result
        except Exception:
            pass

    # Fallback: sequential
    result = {}
    for ind in indicators:
        val = await async_fetch_taapi_indicator(ind, symbol, interval=interval)
        if val:
            result[ind] = val
        await asyncio.sleep(1)  # rate limit
    await _cache_set(ck, result, ttl=60)
    return result


# ═══════════════════════════════════════════════════════════════
# 2. CoinCodex
# ═══════════════════════════════════════════════════════════════

_COINCODEX_BASE = "https://coincodex.com/api/coincodex"


async def async_fetch_coincodex_coin(coin: str = "bitcoin") -> Dict[str, Any]:
    """Fetch coin detail from CoinCodex (free, no key)."""
    ck = _cache_key("coincodex", coin)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CoinCodex", {})
    if suppressed is not None:
        return suppressed
    async with _limiter("coincodex", 3):
        try:
            session = await _get_session()
            async with session.get(
                f"{_COINCODEX_BASE}/get_coin/{coin}"
            ) as resp:
                if resp.status == 404:
                    logger.debug("CoinCodex get_coin endpoint returned 404 — skipping")
                    mark_provider_disabled(
                        "CoinCodex",
                        "get_coin endpoint returned 404",
                        category="data",
                        configured=False,
                        optional=True,
                        details={"endpoint": "get_coin", "coin": coin},
                    )
                    suppress_provider(
                        "CoinCodex",
                        "Temporarily suppressing missing CoinCodex endpoint",
                        cooldown_sec=21600,
                        category="data",
                        configured=False,
                        optional=True,
                        details={"endpoint": "get_coin", "coin": coin, "status": 404},
                    )
                    return {}
                resp.raise_for_status()
                raw = await resp.json()
                data = {
                    "symbol": raw.get("symbol", ""),
                    "name": raw.get("name", ""),
                    "price_usd": float(raw.get("last_price_usd", 0)),
                    "change_1h": float(raw.get("price_change_1H_percent", 0)),
                    "change_24h": float(raw.get("price_change_24H_percent", 0)),
                    "change_7d": float(raw.get("price_change_7D_percent", 0)),
                    "change_30d": float(raw.get("price_change_30D_percent", 0)),
                    "volume_24h": float(raw.get("volume_24_usd", 0)),
                    "market_cap": float(raw.get("market_cap_usd", 0)),
                    "ath": float(raw.get("ATH", 0)),
                    "atl": float(raw.get("ATL", 0)),
                }
                await _cache_set(ck, data, ttl=120)
                return data
        except Exception as exc:
            record = mark_provider_failure(
                "CoinCodex",
                str(exc),
                category="data",
                configured=True,
                optional=True,
                details={"endpoint": "get_coin", "coin": coin},
            )
            _maybe_suppress_provider(
                "CoinCodex",
                str(exc),
                int(record.get("consecutive_failures", 0) or 0),
                details={"endpoint": "get_coin", "coin": coin},
            )
            _log_provider_failure("CoinCodex", "CoinCodex fetch failed", exc)
            return {}


async def async_fetch_coincodex_prediction(coin: str = "bitcoin") -> Dict[str, Any]:
    """Fetch price prediction / forecast from CoinCodex."""
    ck = _cache_key("coincodex_pred", coin)
    cached = await _cache_get(ck)
    if cached:
        return cached
    suppressed = _provider_temporarily_suppressed("CoinCodex", {})
    if suppressed is not None:
        return suppressed
    async with _limiter("coincodex", 3):
        try:
            session = await _get_session()
            async with session.get(
                f"{_COINCODEX_BASE}/get_coin/{coin}"
            ) as resp:
                if resp.status == 404:
                    logger.debug("CoinCodex prediction endpoint returned 404 — skipping")
                    mark_provider_disabled(
                        "CoinCodex",
                        "prediction endpoint returned 404",
                        category="data",
                        configured=False,
                        optional=True,
                        details={"endpoint": "prediction", "coin": coin},
                    )
                    suppress_provider(
                        "CoinCodex",
                        "Temporarily suppressing missing CoinCodex prediction endpoint",
                        cooldown_sec=21600,
                        category="data",
                        configured=False,
                        optional=True,
                        details={"endpoint": "prediction", "coin": coin, "status": 404},
                    )
                    return {}
                resp.raise_for_status()
                raw = await resp.json()
                data = {
                    "price_prediction_1d": float(
                        raw.get("prediction_1d_price", raw.get("last_price_usd", 0))
                    ),
                    "prediction_pct_1d": float(
                        raw.get("prediction_1d_percent", 0)
                    ),
                    "score": float(raw.get("coincodex_score", 0)),
                }
                await _cache_set(ck, data, ttl=600)
                return data
        except Exception as exc:
            record = mark_provider_failure(
                "CoinCodex",
                str(exc),
                category="data",
                configured=True,
                optional=True,
                details={"endpoint": "prediction", "coin": coin},
            )
            _maybe_suppress_provider(
                "CoinCodex",
                str(exc),
                int(record.get("consecutive_failures", 0) or 0),
                details={"endpoint": "prediction", "coin": coin},
            )
            _log_provider_failure("CoinCodex", "CoinCodex prediction fetch failed", exc)
            return {}


# ═══════════════════════════════════════════════════════════════
# 3. CoinStats
# ═══════════════════════════════════════════════════════════════

_COINSTATS_BASE = "https://api.coinstats.app/public/v1"


async def async_fetch_coinstats_coin(coin_id: str = "bitcoin") -> Dict[str, Any]:
    """Fetch coin data from CoinStats (free, no key)."""
    ck = _cache_key("coinstats", coin_id)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coinstats", 3):
        try:
            session = await _get_session()
            async with session.get(
                f"{_COINSTATS_BASE}/coins/{coin_id}",
                params={"currency": "USD"},
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                c = raw.get("coin", raw)
                data = {
                    "name": c.get("name", ""),
                    "symbol": c.get("symbol", ""),
                    "rank": c.get("rank", 0),
                    "price": float(c.get("price", 0)),
                    "volume_24h": float(c.get("volume", 0)),
                    "market_cap": float(c.get("marketCap", 0)),
                    "change_1h": float(c.get("priceChange1h", 0)),
                    "change_24h": float(c.get("priceChange1d", 0)),
                    "change_7d": float(c.get("priceChange1w", 0)),
                    "available_supply": float(c.get("availableSupply", 0)),
                    "total_supply": float(c.get("totalSupply", 0)),
                }
                await _cache_set(ck, data, ttl=120)
                return data
        except Exception as exc:
            logger.warning("CoinStats fetch failed: %s", exc)
            return {}


async def async_fetch_coinstats_global() -> Dict[str, Any]:
    """Global market stats from CoinStats."""
    ck = _cache_key("coinstats_global")
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coinstats", 3):
        try:
            session = await _get_session()
            async with session.get(f"{_COINSTATS_BASE}/global") as resp:
                resp.raise_for_status()
                data = await resp.json()
                await _cache_set(ck, data, ttl=300)
                return data
        except Exception as exc:
            logger.warning("CoinStats global fetch failed: %s", exc)
            return {}


# ═══════════════════════════════════════════════════════════════
# 4. CryptoRank
# ═══════════════════════════════════════════════════════════════

_CRYPTORANK_BASE = "https://api.cryptorank.io/v1"


async def async_fetch_cryptorank_global() -> Dict[str, Any]:
    """Global crypto market data from CryptoRank (free, no key)."""
    ck = _cache_key("cryptorank_global")
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("cryptorank", 3):
        try:
            session = await _get_session()
            async with session.get(f"{_CRYPTORANK_BASE}/global") as resp:
                resp.raise_for_status()
                raw = await resp.json()
                d = raw.get("data", raw)
                data = {
                    "total_market_cap": float(d.get("marketCap", 0)),
                    "total_volume_24h": float(d.get("volume24h", 0)),
                    "btc_dominance": float(d.get("btcDominance", 0)),
                    "eth_dominance": float(d.get("ethDominance", 0)),
                    "market_cap_change_24h": float(d.get("marketCapChange24h", 0)),
                }
                await _cache_set(ck, data, ttl=300)
                return data
        except Exception as exc:
            logger.warning("CryptoRank global fetch failed: %s", exc)
            return {}


# ═══════════════════════════════════════════════════════════════
# 5. CoinLore (no key needed)
# ═══════════════════════════════════════════════════════════════

_COINLORE_BASE = "https://api.coinlore.net/api"


async def async_fetch_coinlore_global() -> Dict[str, Any]:
    """Global market data from CoinLore (free, no key)."""
    ck = _cache_key("coinlore_global")
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coinlore", 5):
        try:
            session = await _get_session()
            async with session.get(f"{_COINLORE_BASE}/global/") as resp:
                resp.raise_for_status()
                raw = await resp.json()
                data_list = raw if isinstance(raw, list) else [raw]
                d = data_list[0] if data_list else {}
                data = {
                    "coins_count": int(d.get("coins_count", 0)),
                    "active_markets": int(d.get("active_markets", 0)),
                    "total_mcap": float(d.get("total_mcap", 0)),
                    "total_volume": float(d.get("total_volume", 0)),
                    "btc_dominance": float(d.get("btc_d", 0)),
                    "eth_dominance": float(d.get("eth_d", 0)),
                    "mcap_change": float(d.get("mcap_change", 0)),
                    "volume_change": float(d.get("volume_change", 0)),
                }
                await _cache_set(ck, data, ttl=300)
                return data
        except Exception as exc:
            logger.warning("CoinLore global fetch failed: %s", exc)
            return {}


async def async_fetch_coinlore_ticker(coin_id: int = 90) -> Dict[str, Any]:
    """Fetch specific coin ticker from CoinLore (90 = BTC)."""
    ck = _cache_key("coinlore_ticker", coin_id)
    cached = await _cache_get(ck)
    if cached:
        return cached
    async with _limiter("coinlore", 5):
        try:
            session = await _get_session()
            async with session.get(
                f"{_COINLORE_BASE}/ticker/", params={"id": coin_id}
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()
                items = raw if isinstance(raw, list) else [raw]
                c = items[0] if items else {}
                data = {
                    "name": c.get("name", ""),
                    "symbol": c.get("symbol", ""),
                    "rank": int(c.get("rank", 0)),
                    "price_usd": float(c.get("price_usd", 0)),
                    "change_1h": float(c.get("percent_change_1h", 0)),
                    "change_24h": float(c.get("percent_change_24h", 0)),
                    "change_7d": float(c.get("percent_change_7d", 0)),
                    "market_cap": float(c.get("market_cap_usd", 0)),
                    "volume_24h": float(c.get("volume24", 0)),
                    "supply": float(c.get("csupply", 0)),
                }
                await _cache_set(ck, data, ttl=120)
                return data
        except Exception as exc:
            logger.warning("CoinLore ticker fetch failed: %s", exc)
            return {}


# ═══════════════════════════════════════════════════════════════
# 6. Multi-exchange price aggregation
# ═══════════════════════════════════════════════════════════════

async def async_fetch_multi_exchange_price(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """Fetch price from 3 sources and compute average, spread, divergence.
    Sources: Binance (live), CoinGecko, CryptoCompare."""
    from data.free_apis import (
        async_fetch_coingecko_price,
        async_fetch_cryptocompare_price,
    )

    # Map BTCUSDT → bitcoin / BTC
    coin_map = {
        "BTCUSDT": ("bitcoin", "BTC"),
        "ETHUSDT": ("ethereum", "ETH"),
        "BNBUSDT": ("binancecoin", "BNB"),
        "SOLUSDT": ("solana", "SOL"),
        "XRPUSDT": ("ripple", "XRP"),
    }
    cg_id, cc_sym = coin_map.get(symbol.upper(), ("bitcoin", "BTC"))

    prices_dict: Dict[str, float] = {}

    # Binance
    try:
        from data.binance_client import get_binance_client
        client = get_binance_client()
        ticker = client.get_ticker_price(symbol)
        if isinstance(ticker, dict):
            bp = float(ticker.get("lastPrice", ticker.get("price", 0)))
        else:
            bp = float(ticker)
        if bp > 0:
            prices_dict["binance"] = bp
    except Exception:
        pass

    # CoinGecko + CryptoCompare in parallel
    cg, cc = await asyncio.gather(
        async_fetch_coingecko_price(cg_id, "usd"),
        async_fetch_cryptocompare_price(cc_sym, "USD"),
        return_exceptions=True,
    )

    if isinstance(cg, dict) and cg.get(cg_id, {}).get("usd"):
        prices_dict["coingecko"] = float(cg[cg_id]["usd"])

    if isinstance(cc, dict) and cc.get("price"):
        prices_dict["cryptocompare"] = float(cc["price"])

    if not prices_dict:
        return {"average_price": 0, "spread_pct": 0, "sources": 0, "prices": {}}

    values = list(prices_dict.values())
    avg = sum(values) / len(values)
    spread = ((max(values) - min(values)) / avg * 100) if avg > 0 else 0

    return {
        "average_price": round(avg, 2),
        "spread_pct": round(spread, 4),
        "max_price": round(max(values), 2),
        "min_price": round(min(values), 2),
        "sources": len(prices_dict),
        "prices": prices_dict,
    }


# ═══════════════════════════════════════════════════════════════
# Aggregated indicators snapshot
# ═══════════════════════════════════════════════════════════════

async def async_fetch_indicator_snapshot(
    symbol: str = "BTCUSDT",
) -> Dict[str, Any]:
    """Complete indicator snapshot combining TAAPI + CoinLore + multi-exchange.
    Used by OracleExtendedAgent and strategies."""
    taapi_sym = symbol.replace("USDT", "/USDT")

    # Parallel fetch
    results = await asyncio.gather(
        async_fetch_taapi_rsi(taapi_sym),
        async_fetch_taapi_macd(taapi_sym),
        async_fetch_taapi_bbands(taapi_sym),
        async_fetch_multi_exchange_price(symbol),
        async_fetch_coinlore_global(),
        return_exceptions=True,
    )

    rsi = results[0] if isinstance(results[0], (int, float)) else 50.0
    macd = results[1] if isinstance(results[1], dict) else {}
    bbands = results[2] if isinstance(results[2], dict) else {}
    multi_price = results[3] if isinstance(results[3], dict) else {}
    global_data = results[4] if isinstance(results[4], dict) else {}

    return {
        "rsi": rsi,
        "macd": macd,
        "bbands": bbands,
        "multi_exchange": multi_price,
        "global_market": global_data,
        "symbol": symbol,
    }
