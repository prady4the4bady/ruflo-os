"""
PRADY TRADER — Auto-retraining pipeline.
Fetches historical data, engineers features, trains all 3 models, validates.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import get_settings
from config.constants import MODEL_DIR
from data.binance_client import get_binance_client
from ml.feature_engineer import engineer_features, get_feature_columns
from ml.lstm_model import LSTMPredictor
from ml.xgboost_model import XGBoostPredictor
from ml.transformer_model import TFTPredictor
from ml.model_store import save_model, get_latest_model_path
from utils.time_utils import utc_now

logger = logging.getLogger("prady.ml.trainer")

TRAIN_TIMEFRAME = "1h"
TRAIN_LOOKBACK_DAYS = 730  # 2 years


async def fetch_training_data(symbol: str, days: int = TRAIN_LOOKBACK_DAYS) -> pd.DataFrame:
    """Fetch historical klines from Binance free REST API.
    Returns raw OHLCV DataFrame with columns: timestamp, open, high, low, close, volume.
    Binance limit is 1500 per request, so we paginate for longer histories.
    """
    client = get_binance_client()

    # Binance max per request is 1500 klines
    hours_needed = days * 24
    limit_per_req = 1500

    all_candles = []
    end_time = int(utc_now().timestamp() * 1000)
    start_time = int((utc_now() - timedelta(days=days)).timestamp() * 1000)

    current_end = end_time
    while current_end > start_time and len(all_candles) < hours_needed:
        klines = client.get_klines(
            symbol=symbol,
            interval=TRAIN_TIMEFRAME,
            limit=limit_per_req,
            end_time=current_end,
        )
        if not klines:
            break

        all_candles = klines + all_candles  # prepend older data
        earliest = int(klines[0][0])
        if earliest <= start_time:
            break
        if len(klines) < limit_per_req:
            break
        current_end = earliest - 1

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df = df[df["timestamp"] >= start_time].copy()
    df.sort_values("timestamp", inplace=True)
    df.drop_duplicates(subset=["timestamp"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def prepare_datasets(df: pd.DataFrame):
    """Engineer features and split into train/validation sets (80/20)."""
    featured = engineer_features(df)
    # engineer_features already handles NaN via ffill+bfill

    if len(featured) < 500:
        logger.warning("Insufficient data for training: %d rows", len(featured))
        return None, None, None, None

    feature_cols = get_feature_columns(featured)
    X = featured[feature_cols].values
    y = featured["target"].values

    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    return X_train, y_train, X_val, y_val


def train_lstm(X_train: np.ndarray, y_train: np.ndarray,
               X_val: np.ndarray, y_val: np.ndarray) -> LSTMPredictor:
    """Train the BiLSTM model."""
    logger.info("Training LSTM on %d samples, %d features ...", len(X_train), X_train.shape[1])
    model = LSTMPredictor(input_size=X_train.shape[1])
    model.fit(X_train, y_train, epochs=30, batch_size=64)
    val_pred_list = []
    for i in range(len(X_val)):
        seq_start = max(0, i - 200 + 1)
        seq = X_val[seq_start:i + 1]
        val_pred_list.append(model.predict(seq))
    val_pred = np.array(val_pred_list)
    acc = float(np.mean((val_pred > 0.5).astype(int) == y_val))
    logger.info("LSTM validation accuracy: %.4f", acc)
    return model


def train_xgboost(X_train: np.ndarray, y_train: np.ndarray,
                   X_val: np.ndarray, y_val: np.ndarray) -> XGBoostPredictor:
    """Train the XGBoost classifier."""
    logger.info("Training XGBoost on %d samples ...", len(X_train))
    model = XGBoostPredictor()
    model.fit(X_train, y_train)
    val_proba = np.array([model.predict_proba(X_val[i:i + 1]) for i in range(len(X_val))])
    val_pred = (val_proba > 0.5).astype(int)
    acc = np.mean(val_pred == y_val)
    logger.info("XGBoost validation accuracy: %.4f", acc)
    return model


def train_tft(X_train: np.ndarray, y_train: np.ndarray,
              X_val: np.ndarray, y_val: np.ndarray) -> TFTPredictor:
    """Train the Temporal Fusion Transformer."""
    logger.info("Training TFT on %d samples ...", len(X_train))
    model = TFTPredictor(input_size=X_train.shape[1])
    model.fit(X_train, y_train, epochs=30, batch_size=64)
    correct = 0
    for i in range(len(X_val)):
        seq_start = max(0, i - 200 + 1)
        seq = X_val[seq_start:i + 1]
        result = model.predict(seq)
        pred = 1 if result["direction_prob"] > 0.5 else 0
        if pred == int(y_val[i]):
            correct += 1
    acc = correct / len(y_val) if len(y_val) > 0 else 0.0
    logger.info("TFT validation accuracy: %.4f", acc)
    return model


async def run_training_pipeline(symbol: str = "BTCUSDT", days: int = TRAIN_LOOKBACK_DAYS) -> dict:
    """Full training pipeline: fetch → engineer → train → save."""
    logger.info("=" * 60)
    logger.info("Starting training pipeline for %s", symbol)
    logger.info("=" * 60)

    start = time.time()

    logger.info("Fetching historical data ...")
    df = await fetch_training_data(symbol, days=days)
    if df.empty:
        logger.error("No data fetched for %s", symbol)
        return {"status": "error", "reason": "no_data"}

    logger.info("Fetched %d candles", len(df))

    result = prepare_datasets(df)
    if result[0] is None:
        return {"status": "error", "reason": "insufficient_data"}

    X_train, y_train, X_val, y_val = result

    logger.info("Training set: %d | Validation set: %d", len(X_train), len(X_val))
    logger.info("Positive class ratio: %.2f%%", y_train.mean() * 100)

    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    saved_models = []

    lstm_model = train_lstm(X_train, y_train, X_val, y_val)
    save_model(lstm_model, "lstm", symbol, timestamp)
    saved_models.append("lstm")

    xgb_model = train_xgboost(X_train, y_train, X_val, y_val)
    save_model(xgb_model, "xgboost", symbol, timestamp)
    saved_models.append("xgboost")

    tft_model = train_tft(X_train, y_train, X_val, y_val)
    save_model(tft_model, "tft", symbol, timestamp)
    saved_models.append("tft")

    elapsed = time.time() - start
    logger.info("Training pipeline completed in %.1f seconds", elapsed)

    return {
        "status": "ok",
        "symbol": symbol,
        "days": days,
        "train_size": len(X_train),
        "val_size": len(X_val),
        "timestamp": timestamp,
        "saved_models": saved_models,
        "elapsed_sec": round(elapsed, 1),
    }


async def retrain_all_symbols(days: int = TRAIN_LOOKBACK_DAYS):
    """Retrain models for every configured trading pair."""
    settings = get_settings()
    results = {}
    for symbol in settings.trading_pairs:
        try:
            results[symbol] = await run_training_pipeline(symbol, days=days)
        except Exception as exc:
            logger.exception("Training failed for %s: %s", symbol, exc)
            results[symbol] = {"status": "error", "reason": str(exc)}
    return results
