from __future__ import annotations

import time
from unittest.mock import Mock, patch

import dashboard.state as dashboard_state


def _seed_dashboard_cache(now: float) -> None:
    dashboard_state._api_cache.clear()
    dashboard_state._api_cache.update(
        {
            "accounts": {"runtime_mode": "testnet", "execution_environment": "testnet"},
            "_ts_accounts": now,
            "accounts_signature": ("testnet", "testnet"),
            "overview": {},
            "_ts_overview": now,
            "fng": {},
            "_ts_fng": now,
            "news": [],
            "_ts_news": now,
            "trending": [],
            "_ts_trending": now,
        }
    )


def test_refresh_live_data_refreshes_account_overview_when_mode_changes():
    now = time.time()
    _seed_dashboard_cache(now)

    state = dashboard_state.DashboardState()
    fake_client = Mock()
    fake_client.get_account_overview.return_value = {
        "runtime_mode": "paper",
        "execution_environment": "paper",
        "display_account": {"disabled": True, "reason": "No live or testnet reference account configured"},
        "display_account_source": "none",
    }

    with patch("dashboard.state._load_all_mode_states", return_value={}):
        with patch(
            "dashboard.state._load_current_state",
            return_value={
                "trading_mode": "paper",
                "execution_environment": "paper",
                "system_running": False,
                "_updated_at": now,
            },
        ):
            with patch("data.binance_client.get_binance_client", return_value=fake_client):
                dashboard_state.refresh_live_data(state)

    assert state.binance_accounts["execution_environment"] == "paper"
    fake_client.get_account_overview.assert_called_once()


def test_refresh_live_data_builds_mode_views_and_policy():
    now = time.time()
    _seed_dashboard_cache(now)
    dashboard_state._api_cache["_ts_accounts"] = now - 60

    state = dashboard_state.DashboardState()
    fake_client = Mock()
    fake_client.get_account_overview.return_value = {
        "runtime_mode": "testnet",
        "execution_environment": "testnet",
        "testnet_account": {
            "label": "Spot Testnet Assets",
            "exchange_label": "Binance Spot Testnet",
            "balances": [
                {"asset": "USDT", "free": 250.0, "locked": 0.0, "estimated_usdt": 250.0},
                {"asset": "BTC", "free": 0.001, "locked": 0.0, "estimated_usdt": 65.0},
            ],
            "account_summary": {
                "free_usdt": 250.0,
                "estimated_total_usdt": 315.0,
                "asset_count": 2,
                "open_order_count": 1,
            },
        },
        "live_account": {
            "label": "Live Spot Assets",
            "exchange_label": "Binance Global",
            "balances": [
                {"asset": "USDT", "free": 100.0, "locked": 0.0, "estimated_usdt": 100.0},
            ],
            "account_summary": {
                "free_usdt": 100.0,
                "estimated_total_usdt": 100.0,
                "asset_count": 1,
                "open_order_count": 0,
            },
        },
        "execution_account": {
            "label": "Spot Testnet Execution Account",
            "balances": [],
            "account_summary": {},
        },
        "display_account": {},
        "display_account_source": "execution_account",
    }

    mode_states = {
        "paper": {
            "trading_mode": "paper",
            "execution_environment": "paper",
            "balance": 10000.0,
            "equity": 10020.0,
            "total_trades": 4,
            "win_rate": 0.5,
            "open_positions": [],
            "closed_trades": [],
            "last_decisions": {},
            "system_running": False,
            "_updated_at": now - 15,
            "_updated_iso": "2025-04-14 10:00:00",
        },
        "testnet": {
            "trading_mode": "testnet",
            "execution_environment": "testnet",
            "balance": 300.0,
            "equity": 315.0,
            "total_trades": 9,
            "win_rate": 0.66,
            "open_positions": [{"symbol": "BTCUSDT"}],
            "closed_trades": [],
            "last_decisions": {
                "BTCUSDT": {
                    "action": "LONG",
                    "confidence": 0.91,
                    "weighted_score": 81.0,
                    "reasoning": "Trend and liquidity aligned",
                }
            },
            "journal_stats": {"total_trades": 9, "total_pnl": 15.0},
            "system_running": True,
            "_updated_at": now,
            "_updated_iso": "2025-04-14 10:00:15",
        },
        "live": {
            "trading_mode": "live",
            "execution_environment": "live",
            "balance": 90.0,
            "equity": 100.0,
            "total_trades": 2,
            "win_rate": 0.5,
            "open_positions": [],
            "closed_trades": [],
            "last_decisions": {},
            "system_running": False,
            "_updated_at": now - 30,
            "_updated_iso": "2025-04-14 09:59:45",
        },
    }

    with patch("dashboard.state._load_all_mode_states", return_value=mode_states):
        with patch("dashboard.state._load_current_state", return_value=mode_states["testnet"]):
            with patch("data.binance_client.get_binance_client", return_value=fake_client):
                dashboard_state.refresh_live_data(state)

    assert state.active_mode_policy["mode"] == "testnet"
    assert state.mode_summaries["paper"]["result_label"] == "Practice PnL"
    assert state.mode_account_views["testnet"]["role_label"] == "Active execution domain"
    assert state.mode_account_views["testnet"]["asset_count"] == 2
    assert state.mode_account_views["live"]["role_label"] == "Live reference wealth domain"
    assert state.mode_account_views["live"]["asset_count"] == 1
    assert state.journal_stats["total_trades"] == 9


def test_refresh_live_data_includes_provider_telemetry():
    now = time.time()
    _seed_dashboard_cache(now)
    dashboard_state._api_cache["_ts_accounts"] = now - 60
    dashboard_state._api_cache["_ts_provider_telemetry"] = now - 60

    state = dashboard_state.DashboardState()
    fake_client = Mock()
    fake_client.get_account_overview.return_value = {}
    provider_statuses = {
        "coingecko": {
            "display_name": "CoinGecko",
            "status": "healthy",
            "message": "Simple price feed healthy",
        }
    }
    rate_limiter_stats = {
        "coingecko": {
            "tokens_available": 27.5,
            "daily_used": 10,
            "daily_limit": 50,
        }
    }

    with patch("dashboard.state._load_all_mode_states", return_value={}):
        with patch(
            "dashboard.state._load_current_state",
            return_value={
                "trading_mode": "paper",
                "execution_environment": "paper",
                "system_running": False,
                "_updated_at": now,
            },
        ):
            with patch("dashboard.state._load_provider_telemetry", return_value=(provider_statuses, rate_limiter_stats)):
                with patch("data.binance_client.get_binance_client", return_value=fake_client):
                    dashboard_state.refresh_live_data(state)

    assert state.provider_statuses["coingecko"]["status"] == "healthy"
    assert state.rate_limiter_stats["coingecko"]["daily_used"] == 10
