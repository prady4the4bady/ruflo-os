from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from data.crypto_indicators_api import (
    async_fetch_taapi_bbands,
    async_fetch_taapi_macd,
    async_fetch_taapi_rsi,
)
from data.data_store import get_data_store


class TestCryptoIndicatorsApi(unittest.IsolatedAsyncioTestCase):
    async def test_taapi_wrappers_fallback_to_local_candles(self):
        store = get_data_store()
        symbol = "BTCUSDT"
        store.clear_symbol(symbol)

        base_price = 100.0
        for index in range(140):
            close = base_price + (index * 0.45)
            store.push_candle(
                symbol,
                "1h",
                {
                    "timestamp": index * 3_600_000,
                    "open": close - 0.3,
                    "high": close + 0.8,
                    "low": close - 0.9,
                    "close": close,
                    "volume": 1_000 + (index * 3),
                },
            )

        try:
            with patch(
                "data.crypto_indicators_api.async_fetch_taapi_indicator",
                new=AsyncMock(return_value={}),
            ):
                rsi = await async_fetch_taapi_rsi("BTC/USDT", "1h")
                macd = await async_fetch_taapi_macd("BTC/USDT", "1h")
                bbands = await async_fetch_taapi_bbands("BTC/USDT", "1h")

            self.assertGreater(rsi, 50.0)
            self.assertNotEqual(macd["macd"], 0.0)
            self.assertNotEqual(macd["signal"], 0.0)
            self.assertGreater(bbands["upper"], bbands["middle"])
            self.assertGreater(bbands["middle"], bbands["lower"])
        finally:
            store.clear_symbol(symbol)


if __name__ == "__main__":
    unittest.main()