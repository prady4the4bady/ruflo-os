"""
PRADY TRADER — Prophet Agent (weight: 0.25).
ML-ensemble price predictor using LSTM + XGBoost + TFT.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent, AgentSignal
from config.constants import (
    AGENT_WEIGHTS,
    LSTM_SEQUENCE_LEN,
    PROPHET_MIN_SIGNAL_STRENGTH,
    PROPHET_NEUTRAL_EDGE,
)
from data.data_store import get_data_store
from ml.ensemble import EnsemblePredictor
from ml.feature_engineer import engineer_features, get_feature_columns
from ml.model_store import load_model

logger = logging.getLogger("prady.agents.prophet")


class ProphetAgent(BaseAgent):
    """
    ML-based price direction predictor.
    Combines LSTM, XGBoost, and TFT via weighted ensemble.
    """

    def __init__(self):
        super().__init__(name="prophet", weight=AGENT_WEIGHTS["prophet"])
        self.ensemble = EnsemblePredictor()
        self._models_loaded = False
        self._loaded_symbol: Optional[str] = None
        self._loaded_input_size: Optional[int] = None

    def _ensure_ensemble(self, input_size: int) -> None:
        if getattr(self.ensemble, "input_size", None) != input_size:
            self.ensemble = EnsemblePredictor(input_size=input_size)
            self._models_loaded = False

    def _load_models(self, symbol: str, input_size: int) -> bool:
        """Attempt to load latest trained models for the symbol."""
        if self._loaded_symbol == symbol and self._loaded_input_size == input_size:
            return self._models_loaded

        try:
            self._ensure_ensemble(input_size)
            lstm_ok = load_model(self.ensemble.lstm, "lstm", symbol)
            xgb_ok = load_model(self.ensemble.xgboost, "xgboost", symbol)
            tft_ok = load_model(self.ensemble.tft, "tft", symbol)
            self._models_loaded = lstm_ok or xgb_ok or tft_ok
            self._loaded_symbol = symbol
            self._loaded_input_size = input_size
            if not self._models_loaded:
                logger.warning("No trained models found for %s - Prophet will stay neutral", symbol)
            return self._models_loaded
        except Exception as exc:
            logger.warning("Model loading failed: %s", exc)
            self._loaded_symbol = symbol
            self._loaded_input_size = input_size
            return False

    async def analyze(self, symbol: str) -> AgentSignal:
        store = get_data_store()

        df = store.get_dataframe(symbol, "1h")
        if df is None or len(df) < 250:
            return AgentSignal(
                agent_name=self.name,
                direction="NEUTRAL",
                confidence=0.0,
                score=0.0,
                reasoning="Insufficient data for ML prediction",
            )

        featured = engineer_features(df)
        featured.dropna(inplace=True)
        if len(featured) < LSTM_SEQUENCE_LEN:
            return AgentSignal(
                agent_name=self.name,
                direction="NEUTRAL",
                confidence=0.0,
                score=0.0,
                reasoning="Insufficient featured rows for sequence model",
            )

        feature_cols = get_feature_columns(featured)
        models_loaded = self._load_models(symbol, len(feature_cols))
        if not models_loaded:
            return AgentSignal(
                agent_name=self.name,
                direction="NEUTRAL",
                confidence=0.0,
                score=0.0,
                reasoning="No trained models available for ML prediction",
                metadata={"models_loaded": False},
            )

        X = featured[feature_cols].values

        # Prepare sequences for LSTM/TFT
        seq = X[-LSTM_SEQUENCE_LEN:]
        # Latest single row for XGBoost
        xgb_row = X[-1:].copy()

        result = self.ensemble.predict(
            lstm_features=seq,
            xgb_features=xgb_row,
            tft_features=seq,
        )

        prob = result["probability"]
        agreement = result["model_agreement"]
        direction_raw = result["prediction"]

        edge = (prob - 0.5) * 2.0
        signal_strength = abs(edge) * max(agreement, 0.35)

        if abs(edge) < PROPHET_NEUTRAL_EDGE or signal_strength < PROPHET_MIN_SIGNAL_STRENGTH:
            direction = "NEUTRAL"
            score = 0.0
        elif direction_raw == "UP":
            direction = "LONG"
            score = edge * 100.0 * max(agreement, 0.5)
        else:
            direction = "SHORT"
            score = edge * 100.0 * max(agreement, 0.5)

        confidence = min(signal_strength, 1.0)

        individual_str = ", ".join(
            f"{k}={v:.3f}" for k, v in result["individual"].items()
        )
        reasoning = (
            f"Ensemble → {direction_raw} (prob={prob:.3f}, edge={edge:+.3f}). "
            f"Agreement={agreement:.2f}, strength={signal_strength:.3f}. "
            f"Individual: [{individual_str}]"
        )

        result = dict(result)
        result["edge"] = edge
        result["signal_strength"] = signal_strength
        result["models_loaded"] = self._models_loaded

        return AgentSignal(
            agent_name=self.name,
            direction=direction,
            confidence=round(confidence, 4),
            score=round(score, 2),
            reasoning=reasoning,
            metadata=result,
        )
