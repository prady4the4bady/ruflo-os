"""Regression tests for model artifact save/load behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml.model_store import get_latest_model_path, load_model, save_model


class _DummyXGBoostModel:
    def __init__(self) -> None:
        self.loaded_path: str | None = None

    def save_model(self, path: str) -> None:
        Path(path).write_text("{}", encoding="utf-8")

    def load_model(self, path: str) -> None:
        self.loaded_path = path


class TestModelStore(unittest.TestCase):
    def test_xgboost_models_save_as_json_and_load_latest(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch("ml.model_store.MODELS_PATH", Path(temp_dir)):
            model = _DummyXGBoostModel()

            path = save_model(model, "xgboost", "BTCUSDT", "20260415_120000")
            latest = get_latest_model_path("xgboost", "BTCUSDT")
            loaded = load_model(model, "xgboost", "BTCUSDT")

        self.assertTrue(path.name.endswith(".json"))
        self.assertEqual(latest, path)
        self.assertTrue(loaded)
        self.assertEqual(model.loaded_path, str(path))

    def test_xgboost_load_supports_legacy_pkl_files(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch("ml.model_store.MODELS_PATH", Path(temp_dir)):
            symbol_dir = Path(temp_dir) / "BTCUSDT"
            symbol_dir.mkdir(parents=True, exist_ok=True)
            legacy_path = symbol_dir / "xgboost_20260415_120000.pkl"
            legacy_path.write_text("{}", encoding="utf-8")

            model = _DummyXGBoostModel()
            loaded = load_model(model, "xgboost", "BTCUSDT", "20260415_120000")

        self.assertTrue(loaded)
        self.assertEqual(model.loaded_path, str(legacy_path))


if __name__ == "__main__":
    unittest.main()