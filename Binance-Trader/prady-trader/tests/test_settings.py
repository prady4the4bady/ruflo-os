from config.settings import Settings


def test_testnet_execution_prefers_dedicated_testnet_keys():
    settings = Settings(
        trading_mode="testnet",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        binance_testnet=True,
        binance_testnet_api_key="spot-testnet-key",
        binance_testnet_secret_key="spot-testnet-secret",
    )

    assert settings.trading_binance_api_key == "spot-testnet-key"
    assert settings.trading_binance_secret_key == "spot-testnet-secret"
    assert settings.display_binance_api_key == "legacy-live-key"
    assert settings.execution_environment == "testnet"


def test_live_execution_falls_back_to_legacy_live_keys():
    settings = Settings(
        trading_mode="live",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        binance_testnet=False,
    )

    assert settings.trading_binance_api_key == "legacy-live-key"
    assert settings.trading_binance_secret_key == "legacy-live-secret"
    assert settings.execution_environment == "live"


def test_explicit_live_keys_override_legacy_fallback():
    settings = Settings(
        trading_mode="live",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        binance_live_api_key="dedicated-live-key",
        binance_live_secret_key="dedicated-live-secret",
        binance_testnet=False,
    )

    assert settings.trading_binance_api_key == "dedicated-live-key"
    assert settings.trading_binance_secret_key == "dedicated-live-secret"
    assert settings.display_binance_api_key == "dedicated-live-key"


def test_testnet_credentials_do_not_fall_back_to_legacy_live_keys():
    settings = Settings(
        _env_file=None,
        trading_mode="paper",
        binance_api_key="legacy-live-key",
        binance_secret_key="legacy-live-secret",
        binance_testnet=True,
        binance_testnet_api_key="",
        binance_testnet_secret_key="",
    )

    assert settings.display_binance_api_key == "legacy-live-key"
    assert settings.testnet_binance_api_key == ""
    assert settings.testnet_binance_secret_key == ""
    assert settings.has_testnet_account_credentials is False


def test_live_exchange_tld_normalizes_and_defaults_to_com():
    settings = Settings(trading_mode="live", binance_tld="US")
    default_settings = Settings(trading_mode="paper")

    assert settings.live_binance_tld == "us"
    assert default_settings.live_binance_tld == "com"