"""Regression tests for shared free API aggregation helpers."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from data.free_apis import async_fetch_all_news, async_fetch_market_overview, async_fetch_newsapi


class TestFreeApis(unittest.IsolatedAsyncioTestCase):
    async def test_newsapi_can_be_disabled_without_network_calls(self):
        settings = SimpleNamespace(enable_newsapi=False, provider_warning_cooldown_sec=300)

        with patch("data.free_apis.get_settings", return_value=settings), patch(
            "data.free_apis.mark_provider_disabled"
        ) as mock_disabled, patch("data.free_apis._get_session") as mock_session:
            articles = await async_fetch_newsapi()

        self.assertEqual(articles, [])
        mock_disabled.assert_called_once()
        mock_session.assert_not_called()

    async def test_async_fetch_all_news_includes_yahoo_and_dedupes(self):
        rss_articles = [{"title": "Duplicate", "url": "https://example.com/a", "published_at": "2026-04-15T10:00:00Z"}]
        yahoo_articles = [
            {"title": "Duplicate", "url": "https://example.com/a", "published_at": "2026-04-15T10:00:00Z"},
            {"title": "Yahoo Only", "url": "https://example.com/b", "published_at": "2026-04-15T11:00:00Z"},
        ]

        with patch("data.free_apis.async_fetch_rss_news", new=AsyncMock(return_value=rss_articles)), patch(
            "data.free_apis.async_fetch_messari_news", new=AsyncMock(return_value=[])
        ), patch(
            "data.free_apis.async_fetch_newsapi", new=AsyncMock(return_value=[])
        ), patch(
            "data.free_apis.async_fetch_newsdata", new=AsyncMock(return_value=[])
        ), patch(
            "data.free_apis.async_fetch_cryptocompare_news", new=AsyncMock(return_value=[])
        ), patch(
            "data.free_apis.async_fetch_yahoo_finance_news", new=AsyncMock(return_value=yahoo_articles)
        ):
            articles = await async_fetch_all_news()

        providers = {article.get("_provider") for article in articles}
        duplicate_urls = [article for article in articles if article.get("url") == "https://example.com/a"]

        self.assertIn("YahooFinance", providers)
        self.assertEqual(len(duplicate_urls), 1)

    async def test_market_overview_uses_yahoo_fallback_and_macro_snapshot(self):
        yahoo_prices = {
            "BTC-USD": {"price": 70123.45, "change_pct_24h": 1.25},
            "ETH-USD": {"price": 3456.78, "change_pct_24h": -0.75},
        }
        macro_snapshot = {"dxy": 104.2, "gold": 2310.5, "sp500": 5225.1}

        async def _fake_to_thread(_func, *args, **kwargs):
            return macro_snapshot

        with patch("data.free_apis.async_fetch_coingecko_price", new=AsyncMock(return_value={})), patch(
            "data.free_apis.async_fetch_coingecko_global", new=AsyncMock(return_value={})
        ), patch(
            "data.free_apis.async_fetch_blockchain_stats", new=AsyncMock(return_value={})
        ), patch(
            "data.free_apis.async_fetch_fear_greed", new=AsyncMock(return_value={})
        ), patch(
            "data.free_apis.async_fetch_cryptocompare_price", new=AsyncMock(return_value={})
        ), patch(
            "data.free_apis.async_fetch_yahoo_finance_prices", new=AsyncMock(return_value=yahoo_prices)
        ), patch(
            "data.free_apis.asyncio.to_thread", new=_fake_to_thread
        ):
            overview = await async_fetch_market_overview()

        self.assertEqual(overview.get("btc_price"), yahoo_prices["BTC-USD"]["price"])
        self.assertEqual(overview.get("btc_price_yahoo"), yahoo_prices["BTC-USD"]["price"])
        self.assertEqual(overview.get("macro_dxy"), macro_snapshot["dxy"])


if __name__ == "__main__":
    unittest.main()