"""Regression tests for FreeCryptoAPI transport fallbacks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data.freecrypto_api import get_live_data


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": "success",
            "symbols": [
                {
                    "symbol": "BTC",
                    "last": "74198.99",
                }
            ],
        }


class TestFreeCryptoApi(unittest.TestCase):
    def test_freecrypto_can_be_disabled_in_settings(self):
        settings = SimpleNamespace(enable_freecrypto=False, freecrypto_api_key="test-token", provider_warning_cooldown_sec=300)

        with patch("data.freecrypto_api.get_settings", return_value=settings), patch(
            "data.freecrypto_api.mark_provider_disabled"
        ) as mock_disabled, patch("data.freecrypto_api.aiohttp.ClientSession") as mock_session:
            result = asyncio.run(get_live_data("BTC"))

        self.assertEqual(result, {})
        mock_disabled.assert_called_once()
        mock_session.assert_not_called()

    def test_requests_fallback_when_aiohttp_fails(self):
        settings = SimpleNamespace(freecrypto_api_key="test-token")

        with patch("data.freecrypto_api.get_settings", return_value=settings), patch(
            "data.freecrypto_api.is_provider_suppressed", return_value=False
        ), patch(
            "data.freecrypto_api.aiohttp.ClientSession", side_effect=RuntimeError("aiohttp down")
        ), patch(
            "data.freecrypto_api.requests.get", return_value=_FakeResponse()
        ) as mock_requests_get:
            result = asyncio.run(get_live_data("BTC"))

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("symbols", [{}])[0].get("symbol"), "BTC")
        mock_requests_get.assert_called_once()

    def test_suppressed_provider_skips_network_calls(self):
        settings = SimpleNamespace(enable_freecrypto=True, freecrypto_api_key="test-token")

        with patch("data.freecrypto_api.get_settings", return_value=settings), patch(
            "data.freecrypto_api.is_provider_suppressed", return_value=True
        ), patch(
            "data.freecrypto_api.aiohttp.ClientSession"
        ) as mock_session, patch(
            "data.freecrypto_api.requests.get"
        ) as mock_requests_get:
            result = asyncio.run(get_live_data("BTC"))

        self.assertEqual(result, {})
        mock_session.assert_not_called()
        mock_requests_get.assert_not_called()

    def test_get_live_data_uses_endpoint_specific_suppression(self):
        settings = SimpleNamespace(enable_freecrypto=True, freecrypto_api_key="test-token")
        checked_providers: list[str] = []

        def _suppressed(provider: str) -> bool:
            checked_providers.append(provider)
            return "getBreakouts" in provider

        with patch("data.freecrypto_api.get_settings", return_value=settings), patch(
            "data.freecrypto_api.is_provider_suppressed", side_effect=_suppressed
        ), patch(
            "data.freecrypto_api.aiohttp.ClientSession", side_effect=RuntimeError("aiohttp down")
        ), patch(
            "data.freecrypto_api.requests.get", return_value=_FakeResponse()
        ) as mock_requests_get:
            result = asyncio.run(get_live_data("BTC"))

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("symbols", [{}])[0].get("symbol"), "BTC")
        self.assertTrue(any("getData" in provider for provider in checked_providers))
        self.assertFalse(any(provider == "FreeCryptoAPI" for provider in checked_providers))
        mock_requests_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()