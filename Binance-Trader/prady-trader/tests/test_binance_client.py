from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from data.binance_client import BinanceClientWrapper


def _make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        runtime_mode="testnet",
        trading_mode="testnet",
        binance_testnet=True,
        binance_tld="com",
        execution_environment="testnet",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        testnet_binance_api_key="test-key",
        testnet_binance_secret_key="test-secret",
        live_binance_api_key="live-key",
        live_binance_secret_key="live-secret",
        trading_pairs=["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"],
    )


def test_build_spot_account_snapshot_uses_prefetched_price_map():
    fake_client = Mock()
    fake_client.get_account.return_value = {
        "balances": [
            {"asset": "BTC", "free": "1.0", "locked": "0.0"},
            {"asset": "USDT", "free": "125.0", "locked": "0.0"},
        ]
    }
    fake_client.get_open_orders.return_value = []

    with patch("data.binance_client.get_settings", return_value=_make_settings()):
        wrapper = BinanceClientWrapper()

    wrapper._get_public_spot_price_map = Mock(return_value={"BTCUSDT": 50000.0})
    wrapper._get_public_spot_price = Mock(side_effect=AssertionError("per-asset lookup should not run"))

    snapshot = wrapper._build_spot_account_snapshot(
        fake_client,
        label="Execution Account",
        environment="testnet",
        is_testnet=True,
    )

    assert snapshot["account_summary"]["estimated_total_usdt"] == 50125.0
    assert snapshot["account_summary"]["free_usdt"] == 125.0
    assert snapshot["positions"] == [
        {
            "symbol": "BTCUSDT",
            "asset": "BTC",
            "positionAmt": 1.0,
            "free": 1.0,
            "locked": 0.0,
            "markPrice": 50000.0,
            "estimated_usdt_value": 50000.0,
        }
    ]
    wrapper._get_public_spot_price.assert_not_called()


def test_build_spot_account_snapshot_skips_per_asset_fetch_when_prefetch_fails():
    fake_client = Mock()
    fake_client.get_account.return_value = {
        "balances": [
            {"asset": "BTC", "free": "1.0", "locked": "0.0"},
            {"asset": "USDT", "free": "50.0", "locked": "0.0"},
        ]
    }
    fake_client.get_open_orders.return_value = []

    with patch("data.binance_client.get_settings", return_value=_make_settings()):
        wrapper = BinanceClientWrapper()

    wrapper._get_public_spot_price_map = Mock(side_effect=RuntimeError("network down"))
    wrapper._get_public_spot_price = Mock(side_effect=AssertionError("per-asset lookup should not run"))

    snapshot = wrapper._build_spot_account_snapshot(
        fake_client,
        label="Execution Account",
        environment="testnet",
        is_testnet=True,
    )

    btc_balance = next(item for item in snapshot["balances"] if item["asset"] == "BTC")
    assert btc_balance["estimated_usdt"] == 0.0
    assert snapshot["account_summary"]["estimated_total_usdt"] == 50.0
    assert snapshot["account_summary"]["free_usdt"] == 50.0
    wrapper._get_public_spot_price.assert_not_called()


def test_live_reference_account_is_disabled_without_effective_live_keys():
    no_live_settings = SimpleNamespace(
        runtime_mode="testnet",
        trading_mode="testnet",
        binance_testnet=True,
        execution_environment="testnet",
        binance_api_key="",
        binance_secret_key="",
        testnet_binance_api_key="test-key",
        testnet_binance_secret_key="test-secret",
        live_binance_api_key="",
        live_binance_secret_key="",
    )

    with patch("data.binance_client.get_settings", return_value=no_live_settings):
        wrapper = BinanceClientWrapper()

    with patch.object(wrapper, "_ensure_client", side_effect=AssertionError("live reference should stay disabled")):
        snapshot = wrapper.get_live_spot_account_info()

    assert snapshot["disabled"] is True
    assert snapshot["environment"] == "live"
    assert snapshot["reason"] == "Live reference account not configured"


def test_live_reference_account_uses_legacy_live_key_fallback():
    fallback_live_settings = SimpleNamespace(
        runtime_mode="paper",
        trading_mode="paper",
        binance_testnet=True,
        binance_tld="com",
        execution_environment="paper",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        display_binance_api_key="legacy-live-key",
        display_binance_secret_key="legacy-live-secret",
        testnet_binance_api_key="test-key",
        testnet_binance_secret_key="test-secret",
    )

    with patch("data.binance_client.get_settings", return_value=fallback_live_settings):
        wrapper = BinanceClientWrapper()

    with patch.object(wrapper, "get_spot_account_info", return_value={"label": "Live Spot Assets", "environment": "live"}) as get_spot:
        snapshot = wrapper.get_live_spot_account_info()

    get_spot.assert_called_once_with("live", label="Live Spot Assets")
    assert snapshot["environment"] == "live"


def test_testnet_reference_account_requires_explicit_testnet_keys():
    no_testnet_settings = SimpleNamespace(
        runtime_mode="paper",
        trading_mode="paper",
        binance_testnet=True,
        binance_tld="com",
        execution_environment="paper",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        live_binance_api_key="legacy-live-key",
        live_binance_secret_key="legacy-live-secret",
        testnet_binance_api_key="",
        testnet_binance_secret_key="",
    )

    with patch("data.binance_client.get_settings", return_value=no_testnet_settings):
        wrapper = BinanceClientWrapper()

    with patch.object(wrapper, "_ensure_client", side_effect=AssertionError("testnet reference should stay disabled")):
        snapshot = wrapper.get_testnet_spot_account_info()

    assert snapshot["disabled"] is True
    assert snapshot["environment"] == "testnet"
    assert "BINANCE_TESTNET_API_KEY" in snapshot["reason"]


def test_live_client_honors_configured_tld():
    live_us_settings = SimpleNamespace(
        runtime_mode="live",
        trading_mode="live",
        binance_testnet=False,
        binance_tld="us",
        execution_environment="live",
        testnet_binance_api_key="",
        testnet_binance_secret_key="",
        live_binance_api_key="live-key",
        live_binance_secret_key="live-secret",
    )

    with patch("data.binance_client.get_settings", return_value=live_us_settings):
        wrapper = BinanceClientWrapper()

    fake_client = Mock()
    with patch("data.binance_client.Client", return_value=fake_client) as client_cls:
        client = wrapper._ensure_client("live")

    assert client is fake_client
    client_cls.assert_called_once_with(
        api_key="live-key",
        api_secret="live-secret",
        testnet=False,
        tld="us",
    )


def test_live_account_error_includes_docs_backed_auth_hint():
    with patch("data.binance_client.get_settings", return_value=_make_settings()):
        wrapper = BinanceClientWrapper()

    with patch.object(
        wrapper,
        "_ensure_client",
        side_effect=RuntimeError("APIError(code=-2015): Invalid API-key, IP, or permissions for action."),
    ):
        snapshot = wrapper.get_live_spot_account_info()

    assert "USER_DATA endpoints" in snapshot["error"]
    assert "BINANCE_TLD=us" in snapshot["error"]


def test_account_overview_prefers_execution_account_in_testnet_mode():
    with patch("data.binance_client.get_settings", return_value=_make_settings()):
        wrapper = BinanceClientWrapper()

    execution_account = {
        "label": "Spot Testnet Execution Account",
        "environment": "testnet",
        "balances": [{"asset": "USDT", "free": 100.0, "locked": 0.0, "total": 100.0, "estimated_usdt": 100.0}],
        "account_summary": {"estimated_total_usdt": 100.0},
    }
    wrapper.get_execution_account_info = Mock(return_value=execution_account)
    wrapper.get_testnet_spot_account_info = Mock(side_effect=AssertionError("testnet reference should reuse execution account"))
    wrapper.get_live_spot_account_info = Mock(side_effect=AssertionError("live reference should not be polled in testnet mode"))

    overview = wrapper.get_account_overview()

    assert overview["display_account"] == execution_account
    assert overview["display_account_source"] == "execution_account"
    assert overview["testnet_account"] == execution_account
    assert overview["live_account"]["disabled"] is True
    assert overview["live_account"]["reason"] == "Live reference account not polled while testnet execution is active"


def test_account_overview_reuses_execution_account_in_live_mode():
    live_settings = SimpleNamespace(
        runtime_mode="live",
        trading_mode="live",
        binance_testnet=False,
        binance_tld="com",
        execution_environment="live",
        testnet_binance_api_key="test-key",
        testnet_binance_secret_key="test-secret",
        live_binance_api_key="live-key",
        live_binance_secret_key="live-secret",
    )

    with patch("data.binance_client.get_settings", return_value=live_settings):
        wrapper = BinanceClientWrapper()

    execution_account = {
        "label": "Live Spot Execution Account",
        "environment": "live",
        "balances": [{"asset": "USDT", "free": 325.0, "locked": 0.0, "total": 325.0, "estimated_usdt": 325.0}],
        "account_summary": {"estimated_total_usdt": 325.0},
    }

    wrapper.get_execution_account_info = Mock(return_value=execution_account)
    wrapper.get_testnet_spot_account_info = Mock(side_effect=AssertionError("testnet reference should not be polled in live mode"))
    wrapper.get_live_spot_account_info = Mock(side_effect=AssertionError("live reference should reuse execution account"))

    overview = wrapper.get_account_overview()

    assert overview["display_account"] == execution_account
    assert overview["display_account_source"] == "execution_account"
    assert overview["live_account"] == execution_account
    assert overview["testnet_account"]["disabled"] is True
    assert overview["testnet_account"]["reason"] == "Spot testnet reference account not polled while live execution is active"


def test_get_positions_returns_execution_spot_positions():
    with patch("data.binance_client.get_settings", return_value=_make_settings()):
        wrapper = BinanceClientWrapper()

    wrapper.get_execution_account_info = Mock(return_value={
        "positions": [
            {
                "symbol": "BTCUSDT",
                "asset": "BTC",
                "positionAmt": 0.5,
                "estimated_usdt_value": 25000.0,
            }
        ]
    })

    assert wrapper.get_positions() == [
        {
            "symbol": "BTCUSDT",
            "asset": "BTC",
            "positionAmt": 0.5,
            "estimated_usdt_value": 25000.0,
        }
    ]


def test_build_stable_conversion_plan_prefers_buying_target_asset_pair():
    with patch("data.binance_client.get_settings", return_value=_make_settings()):
        wrapper = BinanceClientWrapper()

    with patch.object(wrapper, "_symbol_exists", side_effect=lambda symbol: symbol == "USDCUSDT"):
        plan = wrapper._build_stable_conversion_plan("USDT", "USDC")

    assert plan == {"symbol": "USDCUSDT", "side": "BUY", "mode": "quote"}


def test_convert_stable_asset_uses_quote_order_qty_for_buy_side():
    with patch("data.binance_client.get_settings", return_value=_make_settings()):
        wrapper = BinanceClientWrapper()

    wrapper.get_asset_balance = Mock(return_value=125.0)
    wrapper._build_stable_conversion_plan = Mock(return_value={"symbol": "USDCUSDT", "side": "BUY", "mode": "quote"})
    fake_client = Mock()
    fake_client.create_order.return_value = {"orderId": 991}
    wrapper._execution_client = fake_client

    result = wrapper.convert_stable_asset("USDT", "USDC", 100.0)

    fake_client.create_order.assert_called_once_with(
        symbol="USDCUSDT",
        side="BUY",
        type="MARKET",
        quoteOrderQty="100.00",
    )
    assert result["status"] == "converted"
    assert result["order_id"] == 991


def test_account_overview_falls_back_to_testnet_reference_in_paper_mode():
    paper_settings = SimpleNamespace(
        runtime_mode="paper",
        trading_mode="paper",
        binance_testnet=True,
        execution_environment="paper",
        testnet_binance_api_key="test-key",
        testnet_binance_secret_key="test-secret",
        live_binance_api_key="",
        live_binance_secret_key="",
    )

    with patch("data.binance_client.get_settings", return_value=paper_settings):
        wrapper = BinanceClientWrapper()

    execution_account = {
        "disabled": True,
        "label": "Paper Trading Execution",
        "environment": "paper",
        "balances": [],
        "account_summary": {},
        "reason": "Paper mode does not use authenticated Binance execution",
    }
    testnet_account = {
        "label": "Spot Testnet Assets",
        "environment": "testnet",
        "balances": [{"asset": "USDT", "free": 250.0, "locked": 0.0, "total": 250.0, "estimated_usdt": 250.0}],
        "account_summary": {"estimated_total_usdt": 250.0},
    }
    live_account = {
        "disabled": True,
        "label": "Live Spot Assets",
        "environment": "live",
        "balances": [],
        "account_summary": {},
        "reason": "Live reference account not configured",
    }

    wrapper.get_execution_account_info = Mock(return_value=execution_account)
    wrapper.get_testnet_spot_account_info = Mock(return_value=testnet_account)
    wrapper.get_live_spot_account_info = Mock(return_value=live_account)

    overview = wrapper.get_account_overview()

    assert overview["display_account"] == testnet_account
    assert overview["display_account_source"] == "testnet_account"


def test_account_overview_prefers_live_reference_in_paper_mode_when_available():
    paper_settings = SimpleNamespace(
        runtime_mode="paper",
        trading_mode="paper",
        binance_testnet=True,
        execution_environment="paper",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        testnet_binance_api_key="test-key",
        testnet_binance_secret_key="test-secret",
        live_binance_api_key="",
        live_binance_secret_key="",
    )

    with patch("data.binance_client.get_settings", return_value=paper_settings):
        wrapper = BinanceClientWrapper()

    execution_account = {
        "disabled": True,
        "label": "Paper Trading Execution",
        "environment": "paper",
        "balances": [],
        "account_summary": {},
        "reason": "Paper mode does not use authenticated Binance execution",
    }
    testnet_account = {
        "label": "Spot Testnet Assets",
        "environment": "testnet",
        "balances": [{"asset": "USDT", "free": 250.0, "locked": 0.0, "total": 250.0, "estimated_usdt": 250.0}],
        "account_summary": {"estimated_total_usdt": 250.0},
    }
    live_account = {
        "label": "Live Spot Assets",
        "environment": "live",
        "balances": [{"asset": "USDT", "free": 750.0, "locked": 0.0, "total": 750.0, "estimated_usdt": 750.0}],
        "account_summary": {"estimated_total_usdt": 750.0},
    }

    wrapper.get_execution_account_info = Mock(return_value=execution_account)
    wrapper.get_testnet_spot_account_info = Mock(return_value=testnet_account)
    wrapper.get_live_spot_account_info = Mock(return_value=live_account)

    overview = wrapper.get_account_overview()

    assert overview["display_account"] == live_account
    assert overview["display_account_source"] == "live_account"
