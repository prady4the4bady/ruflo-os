"""
PRADY TRADER — Weighted voting ensemble of LSTM + XGBoost + TFT.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np

from config.constants import ENSEMBLE_DISAGREE_THRESHOLD, ENSEMBLE_WEIGHTS, LSTM_FEATURES
from ml.lstm_model import LSTMPredictor
from ml.xgboost_model import XGBoostPredictor
from ml.transformer_model import TFTPredictor

logger = logging.getLogger("prady.ml.ensemble")


class EnsemblePredictor:
    """Combines LSTM, XGBoost, and TFT predictions with weighted voting."""

    def __init__(self, input_size: int = LSTM_FEATURES):
        self.input_size = input_size
        self.lstm = LSTMPredictor(input_size=input_size)
        self.xgboost = XGBoostPredictor()
        self.tft = TFTPredictor(input_size=input_size)
        self.weights = ENSEMBLE_WEIGHTS.copy()

    def predict(
        self,
        lstm_features: Optional[np.ndarray] = None,
        xgb_features: Optional[np.ndarray] = None,
        tft_features: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        predictions = {}
        probs = []
        weights_used = []

        if lstm_features is not None:
            p = self.lstm.predict(lstm_features)
            predictions["lstm"] = p
            probs.append(p)
            weights_used.append(self.weights["lstm"])

        if xgb_features is not None:
            p = self.xgboost.predict_proba(xgb_features)
            predictions["xgboost"] = p
            probs.append(p)
            weights_used.append(self.weights["xgboost"])

        if tft_features is not None:
            result = self.tft.predict(tft_features)
            p = result["direction_prob"]
            predictions["tft"] = p
            probs.append(p)
            weights_used.append(self.weights["tft"])

        if not probs:
            return {
                "prediction": "UP",
                "probability": 0.5,
                "model_agreement": 0.0,
                "horizon_bars": 5,
                "individual": predictions,
            }

        total_w = sum(weights_used)
        weighted_prob = sum(p * w for p, w in zip(probs, weights_used)) / total_w

        spread = max(probs) - min(probs)
        if spread > ENSEMBLE_DISAGREE_THRESHOLD:
            agreement = 1.0 - spread
        else:
            agreement = 1.0 - spread * 0.5

        direction = "UP" if weighted_prob > 0.5 else "DOWN"

        return {
            "prediction": direction,
            "probability": round(float(weighted_prob), 4),
            "model_agreement": round(float(agreement), 4),
            "horizon_bars": 5,
            "individual": predictions,
        }
