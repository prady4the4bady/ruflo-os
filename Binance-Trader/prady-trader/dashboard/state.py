"""
PRADY TRADER — Shared dashboard state.
Thread/process safe state container shared by the desktop shell and headless runtime.
Reads live trading state from JSON file written by TradingOrchestrator.
Falls back to free API data when no live state available.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.mode_policy import get_all_mode_policies, get_mode_policy
from config.settings import ROOT_DIR
from data.state_writer import MODE_STATE_FILES

logger = logging.getLogger("prady.dashboard.state")

LIVE_STATE_FILE = ROOT_DIR / "data" / "live_state.json"
STATE_TTL_SEC = 120


@dataclass
class DashboardState:
    """Global state shared across all dashboard pages."""

    # System status
    system_running: bool = False
    uptime_start: float = field(default_factory=time.time)
    trading_mode: str = "paper"
    execution_environment: str = "paper"

    # Account
    balance: float = 10_000.0
    equity: float = 10_000.0
    daily_pnl: float = 0.0
    total_pnl: float = 0.0

    # Positions
    open_positions: List[Dict] = field(default_factory=list)
    closed_trades: List[Dict] = field(default_factory=list)

    # Council
    last_decisions: Dict[str, Dict] = field(default_factory=dict)
    agent_signals: Dict[str, Dict] = field(default_factory=dict)
    agent_weights: Dict[str, float] = field(default_factory=dict)
    agent_accuracies: Dict[str, float] = field(default_factory=dict)

    # ML
    model_info: Dict[str, Any] = field(default_factory=dict)
    ensemble_predictions: Dict[str, Dict] = field(default_factory=dict)

    # Market
    prices: Dict[str, float] = field(default_factory=dict)
    composite_scores: Dict[str, Dict] = field(default_factory=dict)

    # Grid
    active_grids: Dict[str, Dict] = field(default_factory=dict)

    # Stats
    win_rate: float = 0.0
    total_trades: int = 0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    # Live market data (populated by refresh)
    market_overview: Dict[str, Any] = field(default_factory=dict)
    fear_greed: Dict[str, Any] = field(default_factory=dict)
    news: List[Dict[str, Any]] = field(default_factory=list)
    trending: List[Dict[str, Any]] = field(default_factory=list)

    # Paper trading specific
    cycle_count: int = 0
    kill_switch: bool = False
    initial_balance: float = 10_000.0
    total_return_pct: float = 0.0
    uptime_seconds: float = 0.0
    mode_snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    binance_accounts: Dict[str, Any] = field(default_factory=dict)
    mode_policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    active_mode_policy: Dict[str, Any] = field(default_factory=dict)
    mode_summaries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    mode_account_views: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    journal_stats: Dict[str, Any] = field(default_factory=dict)
    decision_log: List[Dict[str, Any]] = field(default_factory=list)
    agent_activity: List[Dict[str, Any]] = field(default_factory=list)
    provider_statuses: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    rate_limiter_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def uptime_str(self) -> str:
        elapsed = self.uptime_seconds if self.uptime_seconds > 0 else (time.time() - self.uptime_start)
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return f"{hours}h {minutes}m {seconds}s"


# Singleton
_state: Optional[DashboardState] = None

# Time-based API cache — prevents 11+ HTTP calls every 3s autorefresh
_api_cache: Dict[str, Any] = {}


def get_dashboard_state() -> DashboardState:
    global _state
    if _state is None:
        _state = DashboardState()
    return _state


def invalidate_account_overview_cache() -> None:
    _api_cache.pop("accounts", None)
    _api_cache.pop("_ts_accounts", None)
    _api_cache.pop("accounts_signature", None)


def _is_fresh_state(data: Dict[str, Any]) -> bool:
    updated = float(data.get("_updated_at", 0) or 0)
    return updated > 0 and (time.time() - updated) < STATE_TTL_SEC


def _load_redis_state(key: str) -> Optional[Dict[str, Any]]:
    try:
        from config.settings import get_settings
        url = get_settings().redis_url
        if url:
            import redis
            r = redis.from_url(url, decode_responses=True, socket_timeout=2)
            data_str = r.get(key)
            if data_str:
                data = json.loads(data_str)
                if _is_fresh_state(data):
                    return data
    except Exception as exc:
        logger.debug("Redis state read failed for %s: %s", key, exc)

    return None


def _load_json_state(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if _is_fresh_state(data):
                return data
            logger.debug("State file %s is stale", path.name)
    except Exception as exc:
        logger.warning("Failed to read state file %s: %s", path.name, exc)

    return None


def _load_mode_state(mode: str) -> Optional[Dict[str, Any]]:
    return _load_redis_state(f"prady:state:{mode}") or _load_json_state(MODE_STATE_FILES[mode])


def _load_current_state() -> Optional[Dict[str, Any]]:
    return (
        _load_redis_state("prady:state:current")
        or _load_redis_state("prady:live_state")
        or _load_json_state(LIVE_STATE_FILE)
    )


def _load_live_state() -> Optional[Dict[str, Any]]:
    return _load_current_state()


def _load_all_mode_states() -> Dict[str, Dict[str, Any]]:
    states: Dict[str, Dict[str, Any]] = {}
    for mode in ("paper", "testnet", "live"):
        snapshot = _load_mode_state(mode)
        if snapshot:
            states[mode] = snapshot
    return states


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_recent_decision_log(limit: int = 30) -> List[Dict[str, Any]]:
    log_dir = ROOT_DIR / "logs" / "decisions"
    if not log_dir.exists():
        return []

    candidates = sorted(log_dir.glob("decisions_*.jsonl"))
    if not candidates:
        return []

    results: List[Dict[str, Any]] = []
    try:
        lines = candidates[-1].read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        logger.debug("Failed to read decision log feed: %s", exc)
    return results


def _load_recent_agent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    structured_log = ROOT_DIR / "logs" / "structured.jsonl"
    if not structured_log.exists():
        return []

    results: List[Dict[str, Any]] = []
    try:
        lines = structured_log.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            record = entry.get("record", {}) if isinstance(entry, dict) else {}
            level = record.get("level", {}) if isinstance(record.get("level"), dict) else {}
            event_time = record.get("time", {}) if isinstance(record.get("time"), dict) else {}
            results.append(
                {
                    "timestamp": str(event_time.get("repr", ""))[:19],
                    "level": level.get("name", "INFO"),
                    "module": record.get("module", ""),
                    "message": record.get("message", ""),
                }
            )
    except Exception as exc:
        logger.debug("Failed to read agent activity feed: %s", exc)
    return results


def _build_mode_summaries(
    mode_states: Dict[str, Dict[str, Any]],
    current_mode: str,
) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    for mode, policy in get_all_mode_policies().items():
        snapshot = mode_states.get(mode, {})
        balance = _safe_float(snapshot.get("balance"))
        equity = _safe_float(snapshot.get("equity"), balance)
        summaries[mode] = {
            "mode": mode,
            "title": policy["title"],
            "purpose": policy["purpose"],
            "capital_source": policy["capital_source"],
            "execution_model": policy["execution_model"],
            "result_label": policy["result_label"],
            "primary_goal": policy["primary_goal"],
            "guardrail": policy["guardrail"],
            "system_running": bool(snapshot.get("system_running")),
            "is_active": current_mode == mode,
            "updated": snapshot.get("_updated_iso", "—"),
            "balance": balance,
            "equity": equity,
            "daily_pnl": _safe_float(snapshot.get("daily_pnl")),
            "total_pnl": _safe_float(snapshot.get("total_pnl")),
            "total_return_pct": _safe_float(snapshot.get("total_return_pct")),
            "open_positions": len(snapshot.get("open_positions", []) or []),
            "total_trades": _safe_int(snapshot.get("total_trades")),
            "win_rate": _safe_float(snapshot.get("win_rate")),
            "journal_stats": snapshot.get("journal_stats", {}) if isinstance(snapshot.get("journal_stats"), dict) else {},
            "snapshot": snapshot,
        }
    return summaries


def _paper_asset_rows(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pos in snapshot.get("open_positions", []) or []:
        rows.append(
            {
                "symbol": pos.get("symbol", ""),
                "direction": pos.get("direction", ""),
                "quantity": _safe_float(pos.get("quantity")),
                "entry_price": _safe_float(pos.get("entry_price")),
                "current_price": _safe_float(pos.get("current_price")),
                "pnl": _safe_float(pos.get("pnl")),
                "holding_minutes": _safe_float(pos.get("holding_minutes")),
            }
        )
    return rows


def _binance_asset_rows(account: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for balance in account.get("balances", []) or []:
        rows.append(
            {
                "asset": balance.get("asset", ""),
                "free": _safe_float(balance.get("free")),
                "locked": _safe_float(balance.get("locked")),
                "estimated_usdt": _safe_float(balance.get("estimated_usdt")),
            }
        )
    rows.sort(key=lambda item: item.get("estimated_usdt", 0.0), reverse=True)
    return rows


def _build_mode_role(mode: str, execution_environment: str) -> str:
    if mode == execution_environment:
        return "Active execution domain"
    if mode == "live":
        return "Live reference wealth domain"
    if mode == "testnet":
        return "Exchange rehearsal reference"
    return "Simulation reference ledger"


def _build_mode_account_views(
    mode_summaries: Dict[str, Dict[str, Any]],
    account_overview: Dict[str, Any],
    execution_environment: str,
) -> Dict[str, Dict[str, Any]]:
    views: Dict[str, Dict[str, Any]] = {}

    for mode in ("paper", "testnet", "live"):
        summary = mode_summaries.get(mode, {})
        snapshot = summary.get("snapshot", {}) if isinstance(summary.get("snapshot"), dict) else {}
        role_label = _build_mode_role(mode, execution_environment)

        if mode == "paper":
            asset_rows = _paper_asset_rows(snapshot)
            status_detail = "Simulated ledger" if snapshot else "No paper snapshot available"
            status_level = "ok" if snapshot else "info"
            views[mode] = {
                **summary,
                "role_label": role_label,
                "account_label": "Paper Trading Ledger",
                "source_label": "Paper engine snapshot",
                "status_detail": status_detail,
                "status_level": status_level,
                "asset_rows": asset_rows,
                "asset_count": len(asset_rows),
            }
            continue

        account = account_overview.get(f"{mode}_account", {}) if isinstance(account_overview, dict) else {}
        account = account if isinstance(account, dict) else {}
        account_summary = account.get("account_summary", {}) if isinstance(account.get("account_summary"), dict) else {}
        asset_rows = _binance_asset_rows(account)

        if account.get("error"):
            status_detail = str(account.get("error", "Account fetch failed"))
            status_level = "error"
        elif account.get("disabled"):
            status_detail = str(account.get("reason", "Account unavailable"))
            status_level = "warning"
        elif asset_rows:
            status_detail = f"{_safe_int(account_summary.get('asset_count'), len(asset_rows))} funded assets"
            status_level = "ok"
        else:
            status_detail = "No funded assets reported"
            status_level = "info"

        views[mode] = {
            **summary,
            "role_label": role_label,
            "account_label": account.get("label") or summary.get("execution_model", "Binance account"),
            "source_label": account.get("exchange_label") or summary.get("execution_model", "Binance account"),
            "status_detail": status_detail,
            "status_level": status_level,
            "balance": _safe_float(account_summary.get("free_usdt"), summary.get("balance", 0.0)),
            "equity": _safe_float(account_summary.get("estimated_total_usdt"), summary.get("equity", 0.0)),
            "asset_rows": asset_rows,
            "asset_count": _safe_int(account_summary.get("asset_count"), len(asset_rows)),
            "open_order_count": _safe_int(account_summary.get("open_order_count")),
            "account_error": account.get("error", ""),
            "account_disabled": bool(account.get("disabled")),
        }

    return views


def _select_current_state(mode_states: Dict[str, Dict[str, Any]], current_state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = list(mode_states.values())
    if current_state:
        candidates.append(current_state)
    if not candidates:
        return None

    running = [state for state in candidates if state.get("system_running")]
    pool = running or candidates
    return max(pool, key=lambda state: float(state.get("_updated_at", 0) or 0))


def _load_provider_telemetry() -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    provider_statuses: Dict[str, Dict[str, Any]] = {}
    rate_limiter_stats: Dict[str, Dict[str, Any]] = {}

    try:
        from utils.provider_status import load_provider_statuses

        provider_statuses = load_provider_statuses()
    except Exception as exc:
        logger.debug("Provider status load failed: %s", exc)

    try:
        from utils.rate_limiter import get_rate_limiter

        rate_limiter_stats = get_rate_limiter().get_stats()
    except Exception as exc:
        logger.debug("Rate limiter stats load failed: %s", exc)

    return provider_statuses, rate_limiter_stats


def refresh_live_data(state: DashboardState) -> None:
    """Pull latest data from live state file + free APIs into state.
    Uses time-based caching so expensive API calls don't fire every 3s autorefresh.
    """
    global _api_cache

    now = time.time()
    cache = _api_cache

    mode_states = _load_all_mode_states()
    current_state = _load_current_state()
    if current_state:
        current_mode = str(current_state.get("trading_mode", "")).strip().lower()
        if current_mode and current_mode not in mode_states:
            mode_states[current_mode] = current_state
    live = _select_current_state(mode_states, current_state)
    state.mode_snapshots = mode_states
    state.mode_policies = get_all_mode_policies()

    # 1. Try to load current trading state from orchestrator (fast — Redis/file)
    if live:
        state.system_running = live.get("system_running", False)
        state.trading_mode = live.get("trading_mode", state.trading_mode)
        state.execution_environment = live.get("execution_environment", state.execution_environment)
        state.balance = live.get("balance", 10_000.0)
        state.equity = live.get("equity", 10_000.0)
        state.initial_balance = live.get("initial_balance", 10_000.0)
        state.daily_pnl = live.get("daily_pnl", 0.0)
        fallback_total_pnl = (
            state.equity - state.initial_balance
            if state.trading_mode == "paper"
            else live.get("daily_pnl", 0.0)
        )
        state.total_pnl = live.get("total_pnl", fallback_total_pnl)
        state.total_trades = live.get("total_trades", 0)
        state.win_rate = live.get("win_rate", 0.0)
        state.best_trade = live.get("best_trade", 0.0)
        state.worst_trade = live.get("worst_trade", 0.0)
        state.open_positions = live.get("open_positions", [])
        state.closed_trades = live.get("closed_trades", [])
        state.last_decisions = live.get("last_decisions", {})
        state.agent_signals = live.get("agent_signals", {})
        state.prices = live.get("prices", {})
        state.kill_switch = live.get("kill_switch", False)
        state.cycle_count = live.get("cycle_count", 0)
        state.total_return_pct = live.get("total_return_pct", 0.0)
        state.uptime_seconds = live.get("uptime_seconds", 0.0)
        state.ensemble_predictions = live.get("ensemble_predictions", {})
        state.journal_stats = live.get("journal_stats", {}) if isinstance(live.get("journal_stats"), dict) else {}
    else:
        state.system_running = False
        state.trading_mode = "paper"
        state.execution_environment = "paper"
        state.balance = 10_000.0
        state.equity = 10_000.0
        state.initial_balance = 10_000.0
        state.daily_pnl = 0.0
        state.total_pnl = 0.0
        state.total_trades = 0
        state.win_rate = 0.0
        state.best_trade = 0.0
        state.worst_trade = 0.0
        state.open_positions = []
        state.closed_trades = []
        state.last_decisions = {}
        state.agent_signals = {}
        state.prices = {}
        state.kill_switch = False
        state.cycle_count = 0
        state.total_return_pct = 0.0
        state.uptime_seconds = 0.0
        state.ensemble_predictions = {}
        state.journal_stats = {}

    account_signature = (str(state.trading_mode), str(state.execution_environment))
    cached_signature = cache.get("accounts_signature")
    should_refresh_accounts = (
        now - cache.get("_ts_accounts", 0) > 30
        or cached_signature != account_signature
    )

    if should_refresh_accounts:
        try:
            from data.binance_client import get_binance_client

            state.binance_accounts = get_binance_client().get_account_overview()
            cache["accounts"] = state.binance_accounts
            cache["_ts_accounts"] = now
            cache["accounts_signature"] = account_signature
        except Exception as exc:
            logger.warning("Binance account overview refresh failed: %s", exc)
            if cached_signature == account_signature:
                state.binance_accounts = cache.get("accounts", {})
            else:
                state.binance_accounts = {}
    else:
        state.binance_accounts = cache.get("accounts", {})

    state.active_mode_policy = get_mode_policy(state.trading_mode)
    state.mode_summaries = _build_mode_summaries(mode_states, state.trading_mode)
    state.mode_account_views = _build_mode_account_views(
        state.mode_summaries,
        state.binance_accounts,
        state.execution_environment,
    )
    state.decision_log = _load_recent_decision_log()
    state.agent_activity = _load_recent_agent_activity()

    if now - cache.get("_ts_provider_telemetry", 0) > 10:
        provider_statuses, rate_limiter_stats = _load_provider_telemetry()
        cache["provider_statuses"] = provider_statuses
        cache["rate_limiter_stats"] = rate_limiter_stats
        cache["_ts_provider_telemetry"] = now

    state.provider_statuses = dict(cache.get("provider_statuses", {}))
    state.rate_limiter_stats = dict(cache.get("rate_limiter_stats", {}))

    # 2. Refresh free API data with per-endpoint TTL caching
    #    Market overview: 30s | Fear & Greed: 120s | News: 120s | Trending: 300s
    if now - cache.get("_ts_overview", 0) > 30:
        try:
            from data.free_apis import fetch_market_overview
            state.market_overview = fetch_market_overview()
            cache["overview"] = state.market_overview
            cache["_ts_overview"] = now
        except Exception as exc:
            logger.warning("Market overview refresh failed: %s", exc)
            state.market_overview = cache.get("overview", {})
    else:
        state.market_overview = cache.get("overview", {})

    if now - cache.get("_ts_fng", 0) > 120:
        try:
            from data.sentiment_feeds import fetch_fear_greed
            state.fear_greed = fetch_fear_greed()
            cache["fng"] = state.fear_greed
            cache["_ts_fng"] = now
        except Exception as exc:
            logger.warning("Fear & Greed refresh failed: %s", exc)
            state.fear_greed = cache.get("fng", {})
    else:
        state.fear_greed = cache.get("fng", {})

    if now - cache.get("_ts_news", 0) > 120:
        try:
            from data.sentiment_feeds import fetch_crypto_news
            state.news = fetch_crypto_news(limit=10)
            cache["news"] = state.news
            cache["_ts_news"] = now
        except Exception as exc:
            logger.warning("News refresh failed: %s", exc)
            state.news = cache.get("news", [])
    else:
        state.news = cache.get("news", [])

    if now - cache.get("_ts_trending", 0) > 300:
        try:
            from data.free_apis import fetch_coingecko_trending
            state.trending = fetch_coingecko_trending()
            cache["trending"] = state.trending
            cache["_ts_trending"] = now
        except Exception as exc:
            logger.warning("Trending refresh failed: %s", exc)
            state.trending = cache.get("trending", [])
    else:
        state.trending = cache.get("trending", [])

    # Update prices dict from market overview (fallback when orchestrator not running)
    overview = state.market_overview
    if overview.get("btc_price") and "BTCUSDT" not in state.prices:
        state.prices["BTCUSDT"] = overview["btc_price"]
    if overview.get("eth_price") and "ETHUSDT" not in state.prices:
        state.prices["ETHUSDT"] = overview["eth_price"]
