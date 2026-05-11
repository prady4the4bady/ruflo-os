"""
PRADY TRADER — Binance REST + WebSocket client wrapper.
Handles execution routing, retry logic, and account snapshots.
Public market data continues to use free Binance REST endpoints.
Authenticated account and order methods use Binance Spot on the active
configured environment so testnet mode stays fully isolated from live keys.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional

import requests
from binance.client import Client
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from config.constants import API_MAX_RETRIES, API_RETRY_BACKOFF

logger = logging.getLogger("prady.data.binance_client")

# Free public REST endpoints (no API key required)
FAPI_BASE = "https://fapi.binance.com"
FAPI_TESTNET = "https://testnet.binancefuture.com"
SPOT_BASE = "https://api.binance.com"

STABLE_ASSETS = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USDP", "DAI"}
MIN_TRACKED_SPOT_NOTIONAL_USDT = 5.0


class BinanceClientWrapper:
    """Spot-authenticated Binance client with environment-aware routing.

    Public market-data methods always use Binance's live public endpoints.
    Authenticated account snapshots for testnet and live are kept separate,
    and order execution uses the explicitly selected runtime mode only.
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._runtime_mode = str(getattr(cfg, "runtime_mode", getattr(cfg, "trading_mode", "paper"))).lower()
        self._execution_environment = str(getattr(cfg, "execution_environment", "paper")).lower()
        self._execution_testnet = self._execution_environment == "testnet"
        self._live_tld = str(
            getattr(cfg, "live_binance_tld", getattr(cfg, "binance_tld", "com")) or "com"
        ).strip().lower()
        self._testnet_api_key = getattr(cfg, "testnet_binance_api_key", "")
        self._testnet_api_secret = getattr(cfg, "testnet_binance_secret_key", "")
        self._live_api_key = getattr(cfg, "live_binance_api_key", getattr(cfg, "display_binance_api_key", ""))
        self._live_api_secret = getattr(cfg, "live_binance_secret_key", getattr(cfg, "display_binance_secret_key", ""))
        self._execution_client: Optional[Client] = None
        self._testnet_client: Optional[Client] = None
        self._live_client: Optional[Client] = None
        self._base_url = FAPI_BASE
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._symbol_info_cache: Dict[str, Dict[str, Any]] = {}
        self._entry_price_cache: Dict[str, tuple[float, float]] = {}

    def _ensure_client(self, environment: str) -> Client:
        if environment == "testnet":
            if self._testnet_client is None:
                if not self._testnet_api_key or not self._testnet_api_secret:
                    raise RuntimeError(
                        "Binance Spot Testnet credentials required. "
                        "Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_SECRET_KEY."
                    )
                self._testnet_client = Client(
                    api_key=self._testnet_api_key,
                    api_secret=self._testnet_api_secret,
                    testnet=True,
                )
                logger.info("Binance testnet client initialised (market=spot)")
            return self._testnet_client

        if environment == "live":
            if self._live_client is None:
                if not self._live_api_key or not self._live_api_secret:
                    raise RuntimeError(
                        "Binance live spot credentials required. "
                        "Set BINANCE_LIVE_API_KEY/BINANCE_LIVE_SECRET_KEY or legacy BINANCE_API_KEY/BINANCE_SECRET_KEY."
                    )
                self._live_client = Client(
                    api_key=self._live_api_key,
                    api_secret=self._live_api_secret,
                    testnet=False,
                    tld=self._live_tld,
                )
                logger.info("Binance live client initialised (market=spot, tld=%s)", self._live_tld)
            return self._live_client

        raise RuntimeError(f"Unsupported Binance account environment: {environment}")

    def _ensure_execution_client(self) -> Client:
        if self._execution_environment not in {"testnet", "live"}:
            raise RuntimeError("Paper mode does not use authenticated Binance execution")
        if self._execution_client is None:
            self._execution_client = self._ensure_client(self._execution_environment)
            logger.info(
                "Binance execution client initialised (mode=%s, env=%s, market=spot)",
                self._runtime_mode,
                self._execution_environment,
            )
        return self._execution_client

    def _ensure_trading_client(self) -> Client:
        return self._ensure_execution_client()

    def _ensure_display_client(self) -> Client:
        return self._ensure_client("live")

    def _environment_from_display_flag(self, use_display: bool = False) -> str:
        if use_display:
            return "live"
        if self._execution_environment in {"testnet", "live"}:
            return self._execution_environment
        return "testnet" if self._testnet_api_key and self._testnet_api_secret else "live"

    @staticmethod
    def _disabled_account_snapshot(
        *,
        label: str,
        environment: str,
        market_type: str = "spot",
        testnet: bool = False,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "disabled": True,
            "label": label,
            "environment": environment,
            "market_type": market_type,
            "testnet": testnet,
            "balances": [],
            "positions": [],
            "account_summary": {},
            "reason": reason,
        }

    def _can_fetch_live_reference_account(self) -> bool:
        return bool(self._live_api_key and self._live_api_secret)

    def _can_fetch_testnet_reference_account(self) -> bool:
        return bool(self._testnet_api_key and self._testnet_api_secret)

    def _spot_base_for_tld(self, tld: Optional[str] = None) -> str:
        normalized_tld = str(tld or "com").strip().lower()
        if normalized_tld == "com":
            return SPOT_BASE
        return f"https://api.binance.{normalized_tld}"

    def _exchange_label_for_environment(self, environment: str) -> str:
        normalized_environment = environment.lower().strip()
        if normalized_environment == "testnet":
            return "Binance Spot Testnet"
        if normalized_environment == "live" and self._live_tld == "us":
            return "Binance US Spot"
        return "Binance Spot"

    def _format_account_error(self, exc: Exception, *, environment: str) -> str:
        message = str(exc)
        if "-2015" not in message:
            return message

        hint = (
            " Check that the API key is enabled for USER_DATA endpoints and that any API IP allowlist "
            "includes this machine."
        )
        if environment == "live" and self._live_tld == "com":
            hint += " If this key belongs to Binance US, set BINANCE_TLD=us."
        return f"{message}{hint}"

    @staticmethod
    def _account_is_usable(account: Dict[str, Any]) -> bool:
        return bool(account) and not account.get("disabled") and not account.get("error")

    def _select_display_account(
        self,
        *,
        execution_account: Dict[str, Any],
        testnet_account: Dict[str, Any],
        live_account: Dict[str, Any],
    ) -> tuple[Dict[str, Any], str]:
        if self._execution_environment in {"testnet", "live"}:
            return execution_account, "execution_account"

        if self._account_is_usable(live_account):
            return live_account, "live_account"
        if self._account_is_usable(testnet_account):
            return testnet_account, "testnet_account"
        if not live_account.get("disabled"):
            return live_account, "live_account"
        if not testnet_account.get("disabled"):
            return testnet_account, "testnet_account"

        return (
            self._disabled_account_snapshot(
                label="Reference Account Unavailable",
                environment="paper",
                market_type="paper",
                reason="No live or testnet reference account configured",
            ),
            "none",
        )

    @property
    def client(self) -> Client:
        return self._ensure_execution_client()

    @property
    def execution_environment(self) -> str:
        return self._execution_environment

    @property
    def supports_short_entries(self) -> bool:
        return False

    # ── FREE public market data (no API key) ─────────────────

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List]:
        logger.debug("Fetching klines %s %s limit=%d", symbol, interval, limit)
        params: Dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        resp = self._session.get(
            f"{self._base_url}/fapi/v1/klines",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        resp = self._session.get(
            f"{self._base_url}/fapi/v1/depth",
            params={"symbol": symbol, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_funding_rate(self, symbol: str) -> List[Dict[str, Any]]:
        resp = self._session.get(
            f"{self._base_url}/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        resp = self._session.get(
            f"{self._base_url}/fapi/v1/openInterest",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_long_short_ratio(self, symbol: str, period: str = "5m") -> List[Dict]:
        resp = self._session.get(
            f"{self._base_url}/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        resp = self._session.get(
            f"{self._base_url}/fapi/v1/ticker/24hr",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Authenticated spot helpers ───────────────────────────

    def _get_account(self, use_display: bool = False) -> Dict[str, Any]:
        client = self._ensure_client(self._environment_from_display_flag(use_display))
        return client.get_account()

    def _get_symbol_info(self, symbol: str, use_display: bool = False) -> Dict[str, Any]:
        environment = self._environment_from_display_flag(use_display)
        cache_key = f"{environment}:{symbol}"
        if cache_key not in self._symbol_info_cache:
            client = self._ensure_client(environment)
            self._symbol_info_cache[cache_key] = client.get_symbol_info(symbol) or {}
        return self._symbol_info_cache[cache_key]

    def _symbol_exists(self, symbol: str, use_display: bool = False) -> bool:
        try:
            info = self._get_symbol_info(symbol, use_display=use_display)
        except Exception:
            return False
        return bool(info and info.get("symbol", symbol) == symbol)

    def get_symbol_assets(self, symbol: str, use_display: bool = False) -> tuple[str, str]:
        info = self._get_symbol_info(symbol, use_display=use_display)
        base_asset = str(info.get("baseAsset") or "").upper().strip()
        quote_asset = str(info.get("quoteAsset") or "").upper().strip()
        if base_asset and quote_asset:
            return base_asset, quote_asset
        if symbol.endswith("USDT"):
            return symbol[:-4], "USDT"
        if symbol.endswith("USDC"):
            return symbol[:-4], "USDC"
        return symbol, "USDT"

    @staticmethod
    def _quantize(value: Decimal, step: Decimal) -> Decimal:
        if step <= 0:
            return value
        units = (value / step).to_integral_value(rounding=ROUND_DOWN)
        return units * step

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return format(value, "f")

    def normalize_quantity(self, symbol: str, quantity: float, use_display: bool = False) -> float:
        info = self._get_symbol_info(symbol, use_display=use_display)
        step = Decimal("0.000001")
        min_qty = Decimal("0")
        for flt in info.get("filters", []):
            if flt.get("filterType") == "LOT_SIZE":
                step = Decimal(str(flt.get("stepSize", step)))
                min_qty = Decimal(str(flt.get("minQty", min_qty)))
                break
        normalized = self._quantize(Decimal(str(quantity)), step)
        if normalized < min_qty:
            return 0.0
        return float(normalized)

    def normalize_price(self, symbol: str, price: float, use_display: bool = False) -> float:
        info = self._get_symbol_info(symbol, use_display=use_display)
        tick = Decimal("0.000001")
        for flt in info.get("filters", []):
            if flt.get("filterType") == "PRICE_FILTER":
                tick = Decimal(str(flt.get("tickSize", tick)))
                break
        return float(self._quantize(Decimal(str(price)), tick))

    def _get_public_spot_price(self, symbol: str, *, tld: Optional[str] = None) -> float:
        resp = self._session.get(
            f"{self._spot_base_for_tld(tld)}/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data.get("price", 0))

    def _get_public_spot_price_map(self, *, tld: Optional[str] = None) -> Dict[str, float]:
        resp = self._session.get(
            f"{self._spot_base_for_tld(tld)}/api/v3/ticker/price",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        prices: Dict[str, float] = {}
        if not isinstance(data, list):
            return prices
        for item in data:
            symbol = item.get("symbol")
            price = item.get("price")
            if not symbol:
                continue
            try:
                prices[symbol] = float(price)
            except (TypeError, ValueError):
                continue
        return prices

    def _estimate_asset_usdt_value(
        self,
        asset: str,
        amount: float,
        price_cache: Dict[str, float],
        *,
        tld: Optional[str] = None,
        allow_price_fetch: bool = True,
    ) -> float:
        if amount <= 0:
            return 0.0
        if asset in STABLE_ASSETS:
            return amount
        symbol = f"{asset}USDT"
        if symbol not in price_cache:
            if not allow_price_fetch:
                return 0.0
            try:
                price_cache[symbol] = self._get_public_spot_price(symbol, tld=tld)
            except Exception:
                price_cache[symbol] = 0.0
        return amount * price_cache[symbol]

    def estimate_spot_entry_price(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        *,
        max_trades: int = 200,
    ) -> float:
        """Estimate weighted-average entry for remaining spot inventory from trade history."""
        if self._execution_environment not in {"testnet", "live"}:
            return 0.0

        if quantity is None:
            quantity = float(self.get_symbol_base_balance(symbol, include_locked=True))
        quantity = float(quantity or 0.0)
        if quantity <= 0:
            return 0.0

        cache_key = f"{symbol}:{quantity:.8f}"
        cached = self._entry_price_cache.get(cache_key)
        now = time.time()
        if cached and (now - cached[0]) < 60.0:
            return cached[1]

        base_asset, _ = self.get_symbol_assets(symbol)
        try:
            trades = self._ensure_execution_client().get_my_trades(symbol=symbol, limit=max_trades)
        except Exception as exc:
            logger.debug("Failed to estimate spot entry price for %s: %s", symbol, exc)
            return 0.0

        if not isinstance(trades, list):
            return 0.0

        position_qty = Decimal("0")
        cost_basis = Decimal("0")
        for trade in sorted(trades, key=lambda item: item.get("time", 0)):
            qty = Decimal(str(trade.get("qty", 0) or 0))
            price = Decimal(str(trade.get("price", 0) or 0))
            commission = Decimal(str(trade.get("commission", 0) or 0))
            commission_asset = str(trade.get("commissionAsset", "") or "").upper()
            if qty <= 0 or price <= 0:
                continue

            if bool(trade.get("isBuyer")):
                net_qty = qty
                if commission_asset == base_asset.upper():
                    net_qty = max(Decimal("0"), qty - commission)
                trade_cost = price * qty
                if commission_asset in STABLE_ASSETS:
                    trade_cost += commission
                if net_qty <= 0:
                    continue
                position_qty += net_qty
                cost_basis += trade_cost
                continue

            if position_qty <= 0:
                continue
            reduce_qty = min(position_qty, qty)
            avg_cost = (cost_basis / position_qty) if position_qty > 0 else Decimal("0")
            cost_basis -= avg_cost * reduce_qty
            position_qty -= reduce_qty

        avg_entry = float(cost_basis / position_qty) if position_qty > 0 else 0.0
        if avg_entry > 0:
            self._entry_price_cache[cache_key] = (now, avg_entry)
        return avg_entry

    def _build_spot_account_snapshot(
        self,
        client: Client,
        *,
        label: str,
        environment: str,
        is_testnet: bool,
    ) -> Dict[str, Any]:
        public_price_tld = self._live_tld if environment == "live" else "com"
        account = client.get_account()
        try:
            price_cache = self._get_public_spot_price_map(tld=public_price_tld)
        except Exception as exc:
            logger.debug("Failed to prefetch public spot prices for %s: %s", label, exc)
            price_cache = {}
        balances = []
        for raw in account.get("balances", []):
            free = float(raw.get("free", 0) or 0)
            locked = float(raw.get("locked", 0) or 0)
            total = free + locked
            if total <= 0:
                continue
            estimated_total = self._estimate_asset_usdt_value(
                raw.get("asset", ""),
                total,
                price_cache,
                tld=public_price_tld,
                allow_price_fetch=False,
            )
            estimated_locked = self._estimate_asset_usdt_value(
                raw.get("asset", ""),
                locked,
                price_cache,
                tld=public_price_tld,
                allow_price_fetch=False,
            )
            balances.append({
                "asset": raw.get("asset", ""),
                "free": free,
                "locked": locked,
                "total": total,
                "estimated_usdt": estimated_total,
                "locked_estimated_usdt": estimated_locked,
            })
        balances.sort(key=lambda item: item["estimated_usdt"], reverse=True)
        tracked_symbols = set(getattr(get_settings(), "trading_pairs", []) or [])
        positions = []
        for balance in balances:
            asset = balance.get("asset", "")
            if asset in STABLE_ASSETS:
                continue
            symbol = f"{asset}USDT"
            if tracked_symbols and symbol not in tracked_symbols:
                continue
            estimated_usdt = float(balance.get("estimated_usdt", 0.0) or 0.0)
            if estimated_usdt < MIN_TRACKED_SPOT_NOTIONAL_USDT:
                continue
            mark_price = float(price_cache.get(symbol, 0.0) or 0.0)
            positions.append({
                "symbol": symbol,
                "asset": asset,
                "positionAmt": float(balance.get("total", 0.0) or 0.0),
                "free": float(balance.get("free", 0.0) or 0.0),
                "locked": float(balance.get("locked", 0.0) or 0.0),
                "markPrice": mark_price,
                "estimated_usdt_value": estimated_usdt,
            })
        positions.sort(key=lambda item: item["estimated_usdt_value"], reverse=True)

        free_usdt = next((b["free"] for b in balances if b["asset"] == "USDT"), 0.0)
        open_order_count = 0
        try:
            open_order_count = len(client.get_open_orders())
        except Exception:
            open_order_count = 0

        return {
            "label": label,
            "environment": environment,
            "exchange_label": self._exchange_label_for_environment(environment),
            "exchange_tld": public_price_tld,
            "market_type": "spot",
            "testnet": is_testnet,
            "balances": balances,
            "positions": positions,
            "account_summary": {
                "estimated_total_usdt": sum(b["estimated_usdt"] for b in balances),
                "free_usdt": free_usdt,
                "locked_estimated_usdt": sum(b["locked_estimated_usdt"] for b in balances),
                "asset_count": len(balances),
                "open_order_count": open_order_count,
            },
        }

    # ── Authenticated endpoints (spot) ───────────────────────

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_account_balance(self) -> List[Dict[str, Any]]:
        return [
            balance
            for balance in self._get_account().get("balances", [])
            if float(balance.get("free", 0) or 0) > 0 or float(balance.get("locked", 0) or 0) > 0
        ]

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def get_positions(self) -> List[Dict[str, Any]]:
        snapshot = self.get_execution_account_info()
        positions = snapshot.get("positions", []) if isinstance(snapshot, dict) else []
        return positions if isinstance(positions, list) else []

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: str = "BOTH",
    ) -> Dict[str, Any]:
        normalized_qty = self.normalize_quantity(symbol, quantity)
        if normalized_qty <= 0:
            raise ValueError(f"Quantity too small for {symbol}: {quantity}")
        logger.info(
            "SPOT MARKET ORDER %s %s qty=%s env=%s",
            side,
            symbol,
            normalized_qty,
            self._execution_environment,
        )
        return self.client.create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=self._format_decimal(Decimal(str(normalized_qty))),
        )

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        position_side: str = "BOTH",
    ) -> Dict[str, Any]:
        normalized_qty = self.normalize_quantity(symbol, quantity)
        normalized_price = self.normalize_price(symbol, price)
        if normalized_qty <= 0 or normalized_price <= 0:
            raise ValueError(f"Invalid limit order for {symbol}: qty={quantity} price={price}")
        logger.info(
            "SPOT LIMIT ORDER %s %s qty=%s price=%s env=%s",
            side,
            symbol,
            normalized_qty,
            normalized_price,
            self._execution_environment,
        )
        return self.client.create_order(
            symbol=symbol,
            side=side,
            type="LIMIT",
            quantity=self._format_decimal(Decimal(str(normalized_qty))),
            price=self._format_decimal(Decimal(str(normalized_price))),
            timeInForce="GTC",
        )

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def place_stop_market(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        position_side: str = "BOTH",
    ) -> Dict[str, Any]:
        normalized_qty = self.normalize_quantity(symbol, quantity)
        normalized_stop = self.normalize_price(symbol, stop_price)
        if normalized_qty <= 0 or normalized_stop <= 0:
            raise ValueError(f"Invalid stop order for {symbol}: qty={quantity} stop={stop_price}")
        cushion = Decimal("0.995") if side == "SELL" else Decimal("1.005")
        limit_price = self.normalize_price(symbol, float(Decimal(str(normalized_stop)) * cushion))
        logger.info(
            "SPOT STOP_LOSS_LIMIT %s %s qty=%s stop=%s limit=%s env=%s",
            side,
            symbol,
            normalized_qty,
            normalized_stop,
            limit_price,
            self._execution_environment,
        )
        return self.client.create_order(
            symbol=symbol,
            side=side,
            type="STOP_LOSS_LIMIT",
            quantity=self._format_decimal(Decimal(str(normalized_qty))),
            stopPrice=self._format_decimal(Decimal(str(normalized_stop))),
            price=self._format_decimal(Decimal(str(limit_price))),
            timeInForce="GTC",
        )

    @retry(
        stop=stop_after_attempt(API_MAX_RETRIES),
        wait=wait_exponential(multiplier=API_RETRY_BACKOFF, min=1, max=30),
        reraise=True,
    )
    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        logger.warning("Cancelling ALL open spot orders for %s", symbol)
        cancelled: List[Dict[str, Any]] = []
        for order in self.client.get_open_orders(symbol=symbol):
            cancelled.append(
                self.client.cancel_order(symbol=symbol, orderId=order["orderId"])
            )
        return {"symbol": symbol, "cancelled": cancelled, "count": len(cancelled)}

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        logger.info("Spot execution does not use leverage for %s", symbol)
        return {"symbol": symbol, "leverage": 1, "status": "spot_no_leverage"}

    def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> None:
        logger.info("Spot execution does not use margin type for %s", symbol)

    def get_asset_balance(self, asset: str, use_display: bool = False, include_locked: bool = False) -> float:
        account = self._get_account(use_display=use_display)
        for balance in account.get("balances", []):
            if balance.get("asset") == asset:
                free = float(balance.get("free", 0) or 0)
                locked = float(balance.get("locked", 0) or 0)
                return free + locked if include_locked else free
        return 0.0

    def get_symbol_base_balance(self, symbol: str, use_display: bool = False, include_locked: bool = False) -> float:
        base_asset, _ = self.get_symbol_assets(symbol, use_display=use_display)
        return self.get_asset_balance(base_asset, use_display=use_display, include_locked=include_locked)

    def get_quote_balance(self, symbol: str, use_display: bool = False, include_locked: bool = False) -> float:
        _, quote_asset = self.get_symbol_assets(symbol, use_display=use_display)
        return self.get_asset_balance(quote_asset, use_display=use_display, include_locked=include_locked)

    def get_safe_reserve_asset(self) -> str:
        return str(getattr(get_settings(), "safe_reserve_asset", "USDT") or "USDT").upper().strip()

    def estimate_asset_usdt_value(self, asset: str, amount: float, *, use_display: bool = False) -> float:
        if amount <= 0:
            return 0.0
        public_price_tld = self._live_tld if self._environment_from_display_flag(use_display) == "live" else "com"
        return self._estimate_asset_usdt_value(
            asset,
            amount,
            {},
            tld=public_price_tld,
            allow_price_fetch=True,
        )

    def get_quote_balance_with_safe_reserve(self, symbol: str) -> float:
        quote_balance = self.get_quote_balance(symbol)
        reserve_asset = self.get_safe_reserve_asset()
        _, quote_asset = self.get_symbol_assets(symbol)
        if reserve_asset == quote_asset:
            return quote_balance
        reserve_balance = self.get_asset_balance(reserve_asset)
        if reserve_balance <= 0:
            return quote_balance
        if reserve_asset in STABLE_ASSETS and quote_asset in STABLE_ASSETS:
            return quote_balance + reserve_balance
        return quote_balance + self.estimate_asset_usdt_value(reserve_asset, reserve_balance)

    def _build_stable_conversion_plan(self, from_asset: str, to_asset: str) -> Optional[Dict[str, str]]:
        normalized_from = str(from_asset or "").upper().strip()
        normalized_to = str(to_asset or "").upper().strip()
        if not normalized_from or not normalized_to or normalized_from == normalized_to:
            return None

        candidates = [
            {
                "symbol": f"{normalized_to}{normalized_from}",
                "side": "BUY",
                "mode": "quote",
            },
            {
                "symbol": f"{normalized_from}{normalized_to}",
                "side": "SELL",
                "mode": "base",
            },
        ]
        for candidate in candidates:
            if self._symbol_exists(candidate["symbol"]):
                return candidate
        return None

    def convert_stable_asset(self, from_asset: str, to_asset: str, amount: Optional[float] = None) -> Dict[str, Any]:
        from config.constants import SAFE_RESERVE_MIN_NOTIONAL_USDT

        normalized_from = str(from_asset or "").upper().strip()
        normalized_to = str(to_asset or "").upper().strip()
        if self._execution_environment not in {"testnet", "live"}:
            return {"status": "skipped", "reason": "paper_mode", "from_asset": normalized_from, "to_asset": normalized_to}
        if normalized_from == normalized_to:
            return {"status": "skipped", "reason": "same_asset", "from_asset": normalized_from, "to_asset": normalized_to}

        available = self.get_asset_balance(normalized_from)
        target_amount = float(amount if amount is not None else available)
        target_amount = min(target_amount, available)
        if target_amount < float(SAFE_RESERVE_MIN_NOTIONAL_USDT):
            return {
                "status": "skipped",
                "reason": "amount_below_min_notional",
                "from_asset": normalized_from,
                "to_asset": normalized_to,
                "amount": target_amount,
            }

        plan = self._build_stable_conversion_plan(normalized_from, normalized_to)
        if plan is None:
            return {
                "status": "skipped",
                "reason": "conversion_pair_unavailable",
                "from_asset": normalized_from,
                "to_asset": normalized_to,
                "amount": target_amount,
            }

        if plan["mode"] == "quote":
            quote_qty = Decimal(str(target_amount)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            if quote_qty <= 0:
                return {
                    "status": "skipped",
                    "reason": "amount_below_precision",
                    "from_asset": normalized_from,
                    "to_asset": normalized_to,
                    "amount": target_amount,
                }
            order = self.client.create_order(
                symbol=plan["symbol"],
                side=plan["side"],
                type="MARKET",
                quoteOrderQty=self._format_decimal(quote_qty),
            )
            return {
                "status": "converted",
                "symbol": plan["symbol"],
                "side": plan["side"],
                "mode": plan["mode"],
                "amount": float(quote_qty),
                "order_id": order.get("orderId"),
                "from_asset": normalized_from,
                "to_asset": normalized_to,
            }

        quantity = self.normalize_quantity(plan["symbol"], target_amount)
        if quantity <= 0:
            return {
                "status": "skipped",
                "reason": "quantity_below_lot_size",
                "symbol": plan["symbol"],
                "from_asset": normalized_from,
                "to_asset": normalized_to,
                "amount": target_amount,
            }
        order = self.place_market_order(plan["symbol"], plan["side"], quantity)
        return {
            "status": "converted",
            "symbol": plan["symbol"],
            "side": plan["side"],
            "mode": plan["mode"],
            "amount": float(quantity),
            "order_id": order.get("orderId"),
            "from_asset": normalized_from,
            "to_asset": normalized_to,
        }

    def ensure_quote_liquidity(self, symbol: str, required_quote: float) -> Dict[str, Any]:
        _, quote_asset = self.get_symbol_assets(symbol)
        available_quote = self.get_asset_balance(quote_asset)
        if available_quote >= required_quote:
            return {
                "status": "ready",
                "symbol": symbol,
                "quote_asset": quote_asset,
                "available_quote": available_quote,
                "required_quote": required_quote,
            }

        settings = get_settings()
        reserve_asset = self.get_safe_reserve_asset()
        if not getattr(settings, "enable_safe_reserve_conversion", True) or reserve_asset == quote_asset:
            return {
                "status": "skipped",
                "reason": "reserve_conversion_disabled",
                "symbol": symbol,
                "quote_asset": quote_asset,
                "available_quote": available_quote,
                "required_quote": required_quote,
            }

        deficit = max(required_quote - available_quote, 0.0)
        result = self.convert_stable_asset(reserve_asset, quote_asset, deficit)
        result.update(
            {
                "symbol": symbol,
                "quote_asset": quote_asset,
                "available_quote_before": available_quote,
                "required_quote": required_quote,
            }
        )
        return result

    def park_quote_in_safe_reserve(self, symbol: str) -> Dict[str, Any]:
        from config.constants import SAFE_RESERVE_BUFFER_USDT, SAFE_RESERVE_MIN_NOTIONAL_USDT

        settings = get_settings()
        reserve_asset = self.get_safe_reserve_asset()
        _, quote_asset = self.get_symbol_assets(symbol)
        if not getattr(settings, "enable_safe_reserve_conversion", True):
            return {"status": "skipped", "reason": "reserve_conversion_disabled", "symbol": symbol}
        if reserve_asset == quote_asset:
            return {"status": "skipped", "reason": "quote_already_safe_reserve", "symbol": symbol}

        available_quote = self.get_asset_balance(quote_asset)
        amount_to_convert = max(0.0, available_quote - float(SAFE_RESERVE_BUFFER_USDT))
        if amount_to_convert < float(SAFE_RESERVE_MIN_NOTIONAL_USDT):
            return {
                "status": "skipped",
                "reason": "insufficient_quote_to_park",
                "symbol": symbol,
                "quote_asset": quote_asset,
                "available_quote": available_quote,
            }

        result = self.convert_stable_asset(quote_asset, reserve_asset, amount_to_convert)
        result.update(
            {
                "symbol": symbol,
                "quote_asset": quote_asset,
                "reserve_asset": reserve_asset,
                "buffer_retained": float(SAFE_RESERVE_BUFFER_USDT),
            }
        )
        return result

    def get_usdt_balance(self) -> float:
        return self.get_asset_balance("USDT")

    def get_spot_account_info(self, environment: str, *, label: Optional[str] = None) -> Dict[str, Any]:
        normalized_environment = environment.lower().strip()
        is_testnet = normalized_environment == "testnet"
        account_label = label or (
            "Spot Testnet Assets" if is_testnet else "Live Spot Assets"
        )
        try:
            return self._build_spot_account_snapshot(
                self._ensure_client(normalized_environment),
                label=account_label,
                environment=normalized_environment,
                is_testnet=is_testnet,
            )
        except Exception as exc:
            logger.warning("Failed to fetch %s account info: %s", normalized_environment, exc)
            error_message = self._format_account_error(exc, environment=normalized_environment)
            return {
                "error": error_message,
                "label": account_label,
                "environment": normalized_environment,
                "exchange_label": self._exchange_label_for_environment(normalized_environment),
                "exchange_tld": self._live_tld if normalized_environment == "live" else "com",
                "market_type": "spot",
                "testnet": is_testnet,
                "balances": [],
                "positions": [],
                "account_summary": {},
            }

    def get_live_spot_account_info(self) -> Dict[str, Any]:
        if not self._can_fetch_live_reference_account():
            return self._disabled_account_snapshot(
                label="Live Spot Assets",
                environment="live",
                reason="Live reference account not configured",
            )
        return self.get_spot_account_info("live", label="Live Spot Assets")

    def get_testnet_spot_account_info(self) -> Dict[str, Any]:
        if not self._can_fetch_testnet_reference_account():
            return self._disabled_account_snapshot(
                label="Spot Testnet Assets",
                environment="testnet",
                testnet=True,
                reason="Spot testnet reference account not configured; set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_SECRET_KEY",
            )
        return self.get_spot_account_info("testnet", label="Spot Testnet Assets")

    def get_execution_account_info(self) -> Dict[str, Any]:
        if self._execution_environment not in {"testnet", "live"}:
            return {
                "disabled": True,
                "label": "Paper Trading Execution",
                "environment": "paper",
                "market_type": "paper",
                "testnet": False,
                "balances": [],
                "positions": [],
                "account_summary": {},
                "reason": "Paper mode does not use authenticated Binance execution",
            }

        label = (
            "Spot Testnet Execution Account"
            if self._execution_environment == "testnet"
            else "Live Spot Execution Account"
        )
        try:
            return self._build_spot_account_snapshot(
                self.client,
                label=label,
                environment=self._execution_environment,
                is_testnet=self._execution_testnet,
            )
        except Exception as exc:
            logger.warning("Failed to fetch execution account info: %s", exc)
            error_message = self._format_account_error(exc, environment=self._execution_environment)
            return {
                "error": error_message,
                "label": label,
                "environment": self._execution_environment,
                "exchange_label": self._exchange_label_for_environment(self._execution_environment),
                "exchange_tld": self._live_tld if self._execution_environment == "live" else "com",
                "market_type": "spot",
                "testnet": self._execution_testnet,
                "balances": [],
                "positions": [],
                "account_summary": {},
            }

    def get_account_overview(self) -> Dict[str, Any]:
        execution_account = self.get_execution_account_info()
        if self._execution_environment == "testnet":
            testnet_account = execution_account
            live_account = self._disabled_account_snapshot(
                label="Live Spot Assets",
                environment="live",
                reason="Live reference account not polled while testnet execution is active",
            )
        elif self._execution_environment == "live":
            testnet_account = self._disabled_account_snapshot(
                label="Spot Testnet Assets",
                environment="testnet",
                testnet=True,
                reason="Spot testnet reference account not polled while live execution is active",
            )
            live_account = execution_account
        else:
            testnet_account = self.get_testnet_spot_account_info()
            live_account = self.get_live_spot_account_info()
        display_account, display_account_source = self._select_display_account(
            execution_account=execution_account,
            testnet_account=testnet_account,
            live_account=live_account,
        )
        return {
            "runtime_mode": self._runtime_mode,
            "execution_environment": self._execution_environment,
            "testnet_account": testnet_account,
            "live_account": live_account,
            "execution_account": execution_account,
            "display_account": display_account,
            "display_account_source": display_account_source,
        }

    def get_full_account_info(self) -> Dict[str, Any]:
        return self.get_account_overview()


# ── Module-level singleton ───────────────────────────────────
_instance: Optional[BinanceClientWrapper] = None


def get_binance_client() -> BinanceClientWrapper:
    global _instance
    if _instance is None:
        _instance = BinanceClientWrapper()
    return _instance


def reset_binance_client() -> None:
    global _instance
    _instance = None
