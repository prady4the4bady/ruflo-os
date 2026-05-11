from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import utils.provider_status as provider_status


class TestProviderStatus(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.status_file = Path(self.tempdir.name) / "provider_status.json"
        provider_status._STATE.clear()

    def tearDown(self):
        provider_status._STATE.clear()
        self.tempdir.cleanup()

    def test_suppress_provider_blocks_until_success(self):
        with patch.object(provider_status, "STATUS_FILE", self.status_file):
            provider_status.suppress_provider(
                "CoinGecko",
                "Temporary backoff",
                cooldown_sec=60,
                configured=True,
                optional=False,
            )

            self.assertTrue(provider_status.is_provider_suppressed("CoinGecko"))

            provider_status.mark_provider_success(
                "CoinGecko",
                "Recovered",
                configured=True,
                optional=False,
            )

            self.assertFalse(provider_status.is_provider_suppressed("CoinGecko"))

    def test_recommended_suppression_seconds_classifies_error_types(self):
        self.assertGreaterEqual(
            provider_status.recommended_suppression_seconds("401 Unauthorized", default_cooldown=300),
            3600,
        )
        self.assertGreaterEqual(
            provider_status.recommended_suppression_seconds(
                "Timeout on reading data from socket", default_cooldown=300
            ),
            900,
        )
        self.assertEqual(
            provider_status.recommended_suppression_seconds("plain value error", default_cooldown=300),
            0,
        )

    def test_optional_provider_warning_is_suppressed_during_startup_grace(self):
        with patch.object(provider_status, "STATUS_FILE", self.status_file), patch.object(
            provider_status, "_PROCESS_STARTED_AT", time.time()
        ):
            provider_status.mark_provider_failure(
                "NewsAPI",
                "startup timeout",
                configured=True,
                optional=True,
            )

            self.assertFalse(
                provider_status.should_emit_runtime_warning(
                    "NewsAPI",
                    cooldown_sec=300,
                    startup_grace_sec=180,
                    warn_after_failures=2,
                )
            )

    def test_optional_provider_warns_only_after_second_failure_outside_startup_grace(self):
        with patch.object(provider_status, "STATUS_FILE", self.status_file), patch.object(
            provider_status, "_PROCESS_STARTED_AT", time.time() - 600
        ):
            provider_status.mark_provider_failure(
                "NewsAPI",
                "timeout",
                configured=True,
                optional=True,
            )
            self.assertFalse(
                provider_status.should_emit_runtime_warning(
                    "NewsAPI",
                    cooldown_sec=300,
                    startup_grace_sec=180,
                    warn_after_failures=2,
                )
            )

            provider_status.mark_provider_failure(
                "NewsAPI",
                "timeout",
                configured=True,
                optional=True,
            )
            self.assertTrue(
                provider_status.should_emit_runtime_warning(
                    "NewsAPI",
                    cooldown_sec=300,
                    startup_grace_sec=180,
                    warn_after_failures=2,
                )
            )

    def test_required_provider_warns_immediately_outside_startup_grace(self):
        with patch.object(provider_status, "STATUS_FILE", self.status_file), patch.object(
            provider_status, "_PROCESS_STARTED_AT", time.time() - 600
        ):
            provider_status.mark_provider_failure(
                "CoinGecko",
                "timeout",
                configured=True,
                optional=False,
            )
            self.assertTrue(
                provider_status.should_emit_runtime_warning(
                    "CoinGecko",
                    cooldown_sec=300,
                    startup_grace_sec=180,
                    warn_after_failures=1,
                )
            )

    def test_persist_falls_back_to_direct_write_when_replace_is_blocked(self):
        with patch.object(provider_status, "STATUS_FILE", self.status_file), patch(
            "pathlib.Path.replace", side_effect=PermissionError("locked")
        ):
            provider_status.mark_provider_success(
                "CoinGecko",
                "Recovered",
                configured=True,
                optional=False,
            )

        persisted = json.loads(self.status_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted["coingecko"]["status"], "healthy")
        temp_files = list(self.status_file.parent.glob(f"{self.status_file.name}.*.tmp"))
        self.assertEqual(temp_files, [])


class _FakeRedisClient:
    def ping(self):
        raise RuntimeError("connection refused")


class _FakeRedisModule:
    class Redis:
        @staticmethod
        def from_url(*args, **kwargs):
            return _FakeRedisClient()


class TestLocalFallbackLogging(unittest.TestCase):
    def test_local_redis_fallback_logs_info(self):
        from data.data_store import DataStore

        settings = type("Settings", (), {"redis_url": "redis://localhost:6379/0"})()
        with patch("data.data_store.get_settings", return_value=settings), patch(
            "data.data_store.logger"
        ) as mock_logger, patch.dict("sys.modules", {"redis": _FakeRedisModule}):
            store = DataStore()

        self.assertIsNone(store._redis)
        mock_logger.info.assert_called_once()
        mock_logger.warning.assert_not_called()

    def test_local_database_fallback_logs_info(self):
        from execution.trade_journal import TradeJournal

        settings = type("Settings", (), {"database_url": "postgresql://user:pass@localhost:5433/testdb"})()
        with patch("execution.trade_journal.get_settings", return_value=settings), patch(
            "execution.trade_journal.create_engine", side_effect=RuntimeError("db down")
        ), patch("execution.trade_journal.logger") as mock_logger:
            journal = TradeJournal()

        self.assertFalse(journal._available)
        mock_logger.info.assert_called_once()
        mock_logger.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()