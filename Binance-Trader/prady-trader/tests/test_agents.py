"""
PRADY TRADER — Unit tests for agent modules.
Tests base agent, signal creation, and individual agent analysis.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import AgentSignal, BaseAgent


class ConcreteAgent(BaseAgent):
    """Minimal concrete agent for testing the ABC."""

    def __init__(self):
        super().__init__(name="test_agent", weight=0.5)

    async def analyze(self, symbol: str) -> AgentSignal:
        return AgentSignal(
            agent_name=self.name,
            direction="LONG",
            confidence=0.85,
            score=70.0,
            reasoning="Test signal",
        )


class FailingAgent(BaseAgent):
    """Agent that always raises an exception."""

    def __init__(self):
        super().__init__(name="failing_agent", weight=0.1)

    async def analyze(self, symbol: str) -> AgentSignal:
        raise ValueError("Intentional test failure")


class TestAgentSignal(unittest.TestCase):
    """Tests for AgentSignal dataclass."""

    def test_create_signal(self):
        sig = AgentSignal(
            agent_name="oracle",
            direction="LONG",
            confidence=0.9,
            score=80.0,
            reasoning="Strong uptrend",
        )
        self.assertEqual(sig.agent_name, "oracle")
        self.assertEqual(sig.direction, "LONG")
        self.assertEqual(sig.confidence, 0.9)
        self.assertEqual(sig.score, 80.0)

    def test_is_bullish(self):
        sig = AgentSignal(agent_name="t", direction="LONG", confidence=0.8, score=70)
        self.assertTrue(sig.is_bullish)
        self.assertFalse(sig.is_bearish)

    def test_is_bearish(self):
        sig = AgentSignal(agent_name="t", direction="SHORT", confidence=0.7, score=-60)
        self.assertTrue(sig.is_bearish)
        self.assertFalse(sig.is_bullish)

    def test_neutral_signal(self):
        sig = AgentSignal(agent_name="t", direction="NEUTRAL", confidence=0.3, score=0)
        self.assertFalse(sig.is_bullish)
        self.assertFalse(sig.is_bearish)

    def test_low_confidence_not_bullish(self):
        sig = AgentSignal(agent_name="t", direction="LONG", confidence=0.3, score=50)
        self.assertFalse(sig.is_bullish)

    def test_signal_metadata_default(self):
        sig = AgentSignal(agent_name="t", direction="LONG", confidence=0.5, score=50)
        self.assertIsInstance(sig.metadata, dict)
        self.assertEqual(len(sig.metadata), 0)

    def test_signal_has_timestamp(self):
        sig = AgentSignal(agent_name="t", direction="LONG", confidence=0.5, score=50)
        self.assertIsInstance(sig.timestamp, float)
        self.assertGreater(sig.timestamp, 0)


class TestBaseAgent(unittest.TestCase):
    """Tests for BaseAgent ABC."""

    def test_concrete_agent_init(self):
        agent = ConcreteAgent()
        self.assertEqual(agent.name, "test_agent")
        self.assertEqual(agent.weight, 0.5)
        self.assertIsNone(agent.last_signal)

    def test_run_returns_signal(self):
        agent = ConcreteAgent()
        signal = asyncio.run(agent.run("BTCUSDT"))
        self.assertIsInstance(signal, AgentSignal)
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.confidence, 0.85)
        self.assertEqual(signal.score, 70.0)

    def test_run_stores_last_signal(self):
        agent = ConcreteAgent()
        asyncio.run(agent.run("ETHUSDT"))
        self.assertIsNotNone(agent.last_signal)
        self.assertEqual(agent.last_signal.direction, "LONG")

    def test_failing_agent_returns_neutral(self):
        agent = FailingAgent()
        signal = asyncio.run(agent.run("BTCUSDT"))
        self.assertIsInstance(signal, AgentSignal)
        self.assertEqual(signal.direction, "NEUTRAL")
        self.assertEqual(signal.confidence, 0.0)
        self.assertEqual(signal.score, 0.0)
        self.assertIn("Error", signal.reasoning)


class TestOracleAgent(unittest.TestCase):
    """Tests for OracleAgent with mocked data store."""

    @patch("agents.oracle_agent.get_data_store")
    def test_oracle_returns_signal(self, mock_store_fn):
        """Oracle should return a valid signal even with empty data."""
        import numpy as np
        import pandas as pd

        n = 300
        np.random.seed(42)
        close = 100 * np.cumprod(1 + np.random.randn(n) * 0.01)
        mock_df = pd.DataFrame({
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.random.uniform(1000, 10000, n),
        })

        mock_store = MagicMock()
        mock_store.get_dataframe.return_value = mock_df
        mock_store_fn.return_value = mock_store

        from agents.oracle_agent import OracleAgent

        agent = OracleAgent()
        signal = asyncio.run(agent.run("BTCUSDT"))
        self.assertIsInstance(signal, AgentSignal)
        self.assertIn(signal.direction, ("LONG", "SHORT", "NEUTRAL"))
        self.assertGreaterEqual(signal.confidence, 0.0)
        self.assertLessEqual(signal.confidence, 1.0)

    @patch("agents.oracle_agent.get_data_store")
    def test_oracle_empty_data(self, mock_store_fn):
        """Oracle should return NEUTRAL on empty data."""
        import pandas as pd  # noqa

        mock_store = MagicMock()
        mock_store.get_dataframe.return_value = pd.DataFrame()
        mock_store_fn.return_value = mock_store
        from agents.oracle_agent import OracleAgent

        agent = OracleAgent()
        signal = asyncio.run(agent.run("BTCUSDT"))
        self.assertEqual(signal.direction, "NEUTRAL")


class TestWardenAgent(unittest.TestCase):
    """Tests for WardenAgent veto logic."""

    def test_warden_default_no_veto(self):
        """Warden should not veto by default with fresh state."""
        from agents.warden_agent import WardenAgent

        warden = WardenAgent()
        veto, reason = asyncio.run(warden.check_veto("BTCUSDT"))
        self.assertIsInstance(veto, bool)
        self.assertIsInstance(reason, str)

    def test_warden_veto_logs_info_for_expected_policy_block(self):
        from agents.warden_agent import WardenAgent

        settings = SimpleNamespace(
            max_daily_loss=Decimal("0.05"),
            max_concurrent_positions=3,
            uses_binance_execution=True,
        )
        client = MagicMock()
        client.get_positions.return_value = [
            {"estimated_usdt_value": 25},
            {"estimated_usdt_value": 30},
            {"estimated_usdt_value": 40},
        ]
        client.get_execution_account_info.return_value = {
            "account_summary": {"estimated_total_usdt": 1000.0, "free_usdt": 500.0}
        }

        with patch("agents.warden_agent.get_settings", return_value=settings), patch(
            "agents.warden_agent.get_binance_client", return_value=client
        ), patch("agents.warden_agent.logger") as mock_logger:
            veto, reason = asyncio.run(WardenAgent().check_veto("BTCUSDT"))

        self.assertTrue(veto)
        self.assertIn("Max concurrent positions reached", reason)
        mock_logger.info.assert_called_once()
        mock_logger.warning.assert_not_called()


class TestDebaterAgent(unittest.TestCase):
    """Tests for DebaterAgent provider fallback behavior."""

    def test_debater_timeout_is_capped_for_live_loop(self):
        from agents.debater_agent import _reasoning_timeout_sec

        settings = SimpleNamespace(ollama_timeout_sec=60)

        with patch("agents.debater_agent.get_settings", return_value=settings):
            self.assertEqual(_reasoning_timeout_sec(), 8)

    def test_query_ollama_can_be_disabled_in_settings(self):
        from agents.debater_agent import _query_ollama

        settings = SimpleNamespace(enable_ollama_reasoning=False, provider_warning_cooldown_sec=300)

        with patch("agents.debater_agent.get_settings", return_value=settings), patch(
            "agents.debater_agent.mark_provider_disabled"
        ) as mock_disabled:
            result = asyncio.run(_query_ollama("prompt", "mistral", "http://localhost:11434"))

        self.assertEqual(result, "")
        mock_disabled.assert_called_once()

    def test_query_ollama_skips_temporarily_suppressed_provider(self):
        from agents.debater_agent import _query_ollama

        settings = SimpleNamespace(enable_ollama_reasoning=True, provider_warning_cooldown_sec=300)

        with patch("agents.debater_agent.get_settings", return_value=settings), patch(
            "agents.debater_agent.is_provider_suppressed", return_value=True
        ), patch(
            "agents.debater_agent.mark_provider_failure"
        ) as mock_failure:
            result = asyncio.run(_query_ollama("prompt", "mistral", "http://localhost:11434"))

        self.assertEqual(result, "")
        mock_failure.assert_not_called()

    def test_debater_uses_nvidia_nim_when_ollama_fails(self):
        from agents.debater_agent import DebaterAgent

        agent = DebaterAgent()
        agent.set_other_signals(
            {
                "oracle": {"direction": "LONG", "confidence": 0.82, "reasoning": "Trend up"},
                "sentinel": {"direction": "LONG", "confidence": 0.76, "reasoning": "Sentiment strong"},
            }
        )

        settings = SimpleNamespace(
            ollama_model="mistral",
            ollama_host="http://localhost:11434",
            nvidia_nim_api_key="test-token",
            nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
            nvidia_nim_model="meta/llama-3.1-70b-instruct",
        )

        with patch("agents.debater_agent.get_settings", return_value=settings), patch(
            "agents.debater_agent._query_ollama", new=AsyncMock(return_value="")
        ), patch(
            "agents.debater_agent._query_nvidia_nim",
            new=AsyncMock(
                return_value='{"consensus_direction": "LONG", "counter_arguments": ["overextended"], '
                '"verdict": "DISAGREE", "conviction": 0.8, "summary": "Fade the crowd."}'
            ),
        ):
            signal = asyncio.run(agent.analyze("BTCUSDT"))

        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(signal.metadata.get("llm_provider"), "nvidia_nim")
        self.assertTrue(signal.metadata.get("llm_fallback_used"))
        self.assertIn("NVIDIA NIM", signal.reasoning)

    def test_debater_rule_based_when_all_llms_fail(self):
        from agents.debater_agent import DebaterAgent

        agent = DebaterAgent()
        agent.set_other_signals(
            {
                "oracle": {"direction": "SHORT", "confidence": 0.55, "reasoning": "Momentum weak"},
                "prophet": {"direction": "SHORT", "confidence": 0.52, "reasoning": "ML down"},
                "sentinel": {"direction": "LONG", "confidence": 0.20, "reasoning": "Sentiment mixed"},
            }
        )

        settings = SimpleNamespace(
            ollama_model="mistral",
            ollama_host="http://localhost:11434",
            nvidia_nim_api_key="test-token",
            nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
            nvidia_nim_model="meta/llama-3.1-70b-instruct",
        )

        with patch("agents.debater_agent.get_settings", return_value=settings), patch(
            "agents.debater_agent._query_ollama", new=AsyncMock(return_value="")
        ), patch(
            "agents.debater_agent._query_nvidia_nim", new=AsyncMock(return_value="")
        ):
            signal = asyncio.run(agent.analyze("BTCUSDT"))

        self.assertIn("Rule-based", signal.reasoning)
        self.assertIn(signal.direction, ("LONG", "SHORT", "NEUTRAL"))

    def test_debater_normalizes_malformed_llm_payload(self):
        from agents.debater_agent import DebaterAgent

        agent = DebaterAgent()
        agent.set_other_signals(
            {
                "oracle": {"direction": "LONG", "confidence": 0.82, "reasoning": "Trend up"},
                "sentinel": {"direction": "LONG", "confidence": 0.76, "reasoning": "Sentiment strong"},
            }
        )

        with patch(
            "agents.debater_agent._query_reasoning_model",
            new=AsyncMock(
                return_value=(
                    '{"consensus_direction": "long", "counter_arguments": {"risk": "overextended"}, '
                    '"verdict": "disagree", "conviction": "oops", "summary": 123}',
                    "ollama",
                )
            ),
        ):
            signal = asyncio.run(agent.analyze("BTCUSDT"))

        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(signal.metadata.get("llm_provider"), "ollama")
        self.assertEqual(signal.metadata.get("counter_arguments"), [])
        self.assertIn("Ollama verdict: DISAGREE", signal.reasoning)

    def test_debater_falls_back_when_llm_payload_processing_raises(self):
        from agents.debater_agent import DebaterAgent

        agent = DebaterAgent()
        agent.set_other_signals(
            {
                "oracle": {"direction": "SHORT", "confidence": 0.55, "reasoning": "Momentum weak"},
                "prophet": {"direction": "SHORT", "confidence": 0.52, "reasoning": "ML down"},
                "sentinel": {"direction": "LONG", "confidence": 0.20, "reasoning": "Sentiment mixed"},
            }
        )

        with patch(
            "agents.debater_agent._query_reasoning_model",
            new=AsyncMock(return_value=("{\"verdict\": \"agree\"}", "ollama")),
        ), patch(
            "agents.debater_agent._parse_llm_response",
            side_effect=RuntimeError("boom"),
        ):
            signal = asyncio.run(agent.analyze("BTCUSDT"))

        self.assertEqual(signal.metadata.get("llm_provider"), "rule_based")
        self.assertTrue(signal.metadata.get("llm_fallback_used"))
        self.assertIn("LLM parse fallback", signal.reasoning)


class TestProphetAgent(unittest.TestCase):
    def test_prophet_uses_feature_sized_models_and_reloads_per_symbol(self):
        from agents.prophet_agent import ProphetAgent

        initial_ensemble = MagicMock()
        initial_ensemble.input_size = 10
        sized_ensemble = MagicMock()
        sized_ensemble.input_size = 125

        with patch("agents.prophet_agent.EnsemblePredictor", side_effect=[initial_ensemble, sized_ensemble]) as ensemble_cls, patch(
            "agents.prophet_agent.load_model", return_value=True
        ) as load_model_mock:
            agent = ProphetAgent()

            self.assertIs(agent.ensemble, initial_ensemble)

            self.assertTrue(agent._load_models("BTCUSDT", 125))
            self.assertIs(agent.ensemble, sized_ensemble)
            self.assertEqual(ensemble_cls.call_args_list[1].kwargs, {"input_size": 125})
            self.assertEqual(load_model_mock.call_count, 3)

            self.assertTrue(agent._load_models("BTCUSDT", 125))
            self.assertEqual(load_model_mock.call_count, 3)

            self.assertTrue(agent._load_models("ETHUSDT", 125))
            self.assertEqual(load_model_mock.call_count, 6)

    @patch("agents.prophet_agent.get_data_store")
    def test_prophet_returns_neutral_when_models_are_missing(self, mock_store_fn):
        import numpy as np
        import pandas as pd

        n = 260
        close = np.linspace(100.0, 120.0, n)
        mock_df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": np.full(n, 1000.0),
            }
        )

        mock_store = MagicMock()
        mock_store.get_dataframe.return_value = mock_df
        mock_store_fn.return_value = mock_store

        with patch("agents.prophet_agent.engineer_features", side_effect=lambda df: df.copy()), patch(
            "agents.prophet_agent.get_feature_columns", return_value=["close", "volume"]
        ), patch("agents.prophet_agent.load_model", return_value=False):
            from agents.prophet_agent import ProphetAgent

            agent = ProphetAgent()
            signal = asyncio.run(agent.run("ADAUSDT"))

        self.assertEqual(signal.direction, "NEUTRAL")
        self.assertEqual(signal.confidence, 0.0)
        self.assertEqual(signal.score, 0.0)
        self.assertFalse(signal.metadata.get("models_loaded", True))


if __name__ == "__main__":
    unittest.main()
