"""
PRADY TRADER — Versioned model save / load.
Models are stored in MODEL_DIR with timestamped filenames.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from config.constants import MODEL_DIR
from config.settings import ROOT_DIR

logger = logging.getLogger("prady.ml.model_store")

MODELS_PATH = ROOT_DIR / MODEL_DIR


def _ensure_dir(symbol: str) -> Path:
    d = MODELS_PATH / symbol
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_model(model: Any, model_type: str, symbol: str, timestamp: str) -> Path:
    """
    Save a trained model to disk.
    model_type: 'lstm', 'xgboost', or 'tft'
    Returns the path to the saved file.
    """
    model_dir = _ensure_dir(symbol)
    filename = f"{model_type}_{timestamp}.pkl"
    filepath = model_dir / filename

    if model_type == "xgboost":
        xgb_path = model_dir / f"{model_type}_{timestamp}.json"
        model.save_model(str(xgb_path))
        meta = {
            "model_type": model_type,
            "symbol": symbol,
            "timestamp": timestamp,
            "saved_at": datetime.now(UTC).isoformat(),
            "path": str(xgb_path),
        }
        meta_path = model_dir / f"{model_type}_{timestamp}_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        logger.info("Saved %s model -> %s", model_type, xgb_path)
        return xgb_path
    else:
        state = model.state_dict()
        with open(filepath, "wb") as f:
            pickle.dump(state, f)
        meta = {
            "model_type": model_type,
            "symbol": symbol,
            "timestamp": timestamp,
            "saved_at": datetime.now(UTC).isoformat(),
            "path": str(filepath),
        }
        meta_path = model_dir / f"{model_type}_{timestamp}_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        logger.info("Saved %s model -> %s", model_type, filepath)
        return filepath


def load_model(model_instance: Any, model_type: str, symbol: str,
               timestamp: Optional[str] = None) -> bool:
    """
    Load model weights into an existing model instance.
    If timestamp is None, loads the latest version.
    Returns True if loading succeeded.
    """
    model_dir = MODELS_PATH / symbol
    if not model_dir.exists():
        logger.warning("No models directory for %s", symbol)
        return False

    if timestamp is None:
        path = get_latest_model_path(model_type, symbol)
    else:
        if model_type == "xgboost":
            json_path = model_dir / f"{model_type}_{timestamp}.json"
            legacy_path = model_dir / f"{model_type}_{timestamp}.pkl"
            path = json_path if json_path.exists() else legacy_path
        else:
            path = model_dir / f"{model_type}_{timestamp}.pkl"

    if path is None or not path.exists():
        logger.warning("Model file not found: %s", path)
        return False

    try:
        if model_type == "xgboost":
            model_instance.load_model(str(path))
        else:
            with open(path, "rb") as f:
                state = pickle.load(f)  # noqa: S301
            model_instance.load_state_dict(state)
        logger.info("Loaded %s model from %s", model_type, path)
        return True
    except Exception as exc:
        logger.exception("Failed to load %s model: %s", model_type, exc)
        return False


def get_latest_model_path(model_type: str, symbol: str) -> Optional[Path]:
    """Find the most recent model file for a given type and symbol."""
    model_dir = MODELS_PATH / symbol
    if not model_dir.exists():
        return None

    if model_type == "xgboost":
        candidates = sorted(
            [
                *[f for f in model_dir.glob(f"{model_type}_*.json") if "_meta" not in f.name],
                *[f for f in model_dir.glob(f"{model_type}_*.pkl") if "_meta" not in f.name],
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None
    else:
        suffix = ".pkl"

    candidates = sorted(
        [f for f in model_dir.glob(f"{model_type}_*{suffix}")
         if "_meta" not in f.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def list_models(symbol: Optional[str] = None) -> list[dict]:
    """List all saved models, optionally filtered by symbol."""
    results = []

    if symbol:
        dirs = [MODELS_PATH / symbol] if (MODELS_PATH / symbol).exists() else []
    else:
        dirs = [d for d in MODELS_PATH.iterdir() if d.is_dir()] if MODELS_PATH.exists() else []

    for model_dir in dirs:
        for meta_file in sorted(model_dir.glob("*_meta.json")):
            try:
                meta = json.loads(meta_file.read_text())
                results.append(meta)
            except Exception:
                continue

    return results


def cleanup_old_models(symbol: str, keep: int = 5):
    """Keep only the N most recent versions of each model type per symbol."""
    model_dir = MODELS_PATH / symbol
    if not model_dir.exists():
        return

    for model_type in ["lstm", "xgboost", "tft"]:
        if model_type == "xgboost":
            candidates = sorted(
                [
                    *[f for f in model_dir.glob(f"{model_type}_*.json") if "_meta" not in f.name],
                    *[f for f in model_dir.glob(f"{model_type}_*.pkl") if "_meta" not in f.name],
                ],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        else:
            suffix = ".pkl"
            candidates = sorted(
                [f for f in model_dir.glob(f"{model_type}_*{suffix}")
                 if "_meta" not in f.name],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

        for old_file in candidates[keep:]:
            meta_name = old_file.stem + "_meta.json"
            meta_file = model_dir / meta_name
            old_file.unlink(missing_ok=True)
            meta_file.unlink(missing_ok=True)
            logger.info("Cleaned up old model: %s", old_file.name)
