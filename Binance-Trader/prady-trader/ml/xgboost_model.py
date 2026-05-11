"""
PRADY TRADER — XGBoost direction classifier.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split

from config.constants import XGB_LEARNING_RATE, XGB_MAX_DEPTH, XGB_N_ESTIMATORS

logger = logging.getLogger("prady.ml.xgboost_model")


class XGBoostPredictor:
    def __init__(self):
        self.model: Optional[xgb.XGBClassifier] = None
        self._trained = False
        self._feature_names: list[str] = []

    def fit(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        feature_names: list[str] | None = None,
        validation_split: float = 0.1,
    ) -> dict:
        self._feature_names = feature_names or [f"f{i}" for i in range(features.shape[1])]
        X_train, X_val, y_train, y_val = train_test_split(
            features, targets, test_size=validation_split, shuffle=False
        )
        self.model = xgb.XGBClassifier(
            n_estimators=XGB_N_ESTIMATORS,
            max_depth=XGB_MAX_DEPTH,
            learning_rate=XGB_LEARNING_RATE,
            objective="binary:logistic",
            eval_metric="logloss",
            use_label_encoder=False,
            tree_method="hist",
            verbosity=0,
            random_state=42,
        )
        self.model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        val_pred = self.model.predict(X_val)
        val_acc = float(np.mean(val_pred == y_val))
        self._trained = True
        logger.info("XGBoost trained - val_acc=%.4f", val_acc)
        return {"val_accuracy": val_acc}

    def predict_proba(self, features: np.ndarray) -> float:
        if not self._trained or self.model is None:
            return 0.5
        if features.ndim == 1:
            features = features.reshape(1, -1)
        proba = self.model.predict_proba(features)
        return float(proba[0, 1])

    def feature_importance(self) -> dict:
        if self.model is None:
            return {}
        importance = self.model.feature_importances_
        return dict(zip(self._feature_names, importance.tolist()))

    def save_model(self, path: str) -> None:
        if self.model is not None:
            import pickle
            with open(path, "wb") as f:
                pickle.dump(self.model, f)
            logger.info("XGBoost model saved to %s", path)

    def load_model(self, path: str) -> None:
        import pickle
        with open(path, "rb") as f:
            self.model = pickle.load(f)
        self._trained = True
        self._trained = True
        logger.info("XGBoost model loaded from %s", path)
