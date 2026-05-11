"""
PRADY TRADER — Temporal Fusion Transformer (simplified).
Multi-horizon quantile forecaster built in PyTorch.
"""

from __future__ import annotations

import logging
import math
from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config.constants import TFT_ATTENTION_HEADS, TFT_HIDDEN_SIZE, TFT_NUM_LAYERS

logger = logging.getLogger("prady.ml.transformer_model")


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 500):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        if d_model > 1:
            pe[:, 1::2] = torch.cos(position * div_term[: d_model // 2])
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]


class TemporalFusionTransformer(nn.Module):
    """Simplified TFT outputting quantile predictions."""

    def __init__(
        self,
        input_size: int = 10,
        hidden_size: int = TFT_HIDDEN_SIZE,
        num_heads: int = TFT_ATTENTION_HEADS,
        num_layers: int = TFT_NUM_LAYERS,
        num_quantiles: int = 3,
    ):
        super().__init__()
        self.input_proj = nn.Linear(input_size, hidden_size)
        self.pos_enc = PositionalEncoding(hidden_size)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_size,
            nhead=num_heads,
            dim_feedforward=hidden_size * 4,
            dropout=0.1,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.gate = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.Sigmoid(),
        )
        self.fc = nn.Linear(hidden_size, num_quantiles)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.input_proj(x)
        h = self.pos_enc(h)
        h = self.encoder(h)
        h = h[:, -1, :]
        g = self.gate(h)
        h = h * g
        return self.fc(h)


class TFTPredictor:
    """Wrapper for training and inference."""

    QUANTILES = [0.1, 0.5, 0.9]

    def __init__(self, input_size: int = 10, device: Optional[str] = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.input_size = input_size
        self.model = TemporalFusionTransformer(input_size=input_size).to(self.device)
        self.scaler_mean: Optional[np.ndarray] = None
        self.scaler_std: Optional[np.ndarray] = None
        self._trained = False

    def _create_sequences(
        self, data: np.ndarray, seq_len: int = 100
    ) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        for i in range(len(data) - seq_len):
            X.append(data[i : i + seq_len, :-1])
            future_return = data[i + seq_len - 1, -1]
            y.append(future_return)
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)

    def _quantile_loss(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        losses = []
        for i, q in enumerate(self.QUANTILES):
            error = target - pred[:, i]
            losses.append(torch.max(q * error, (q - 1) * error).mean())
        return torch.stack(losses).mean()

    def fit(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        epochs: int = 30,
        batch_size: int = 64,
        lr: float = 0.001,
        seq_len: int = 100,
    ) -> dict:
        self.scaler_mean = features.mean(axis=0)
        self.scaler_std = features.std(axis=0) + 1e-8
        normed = (features - self.scaler_mean) / self.scaler_std
        combined = np.column_stack([normed, targets])
        X, y = self._create_sequences(combined, seq_len)
        if len(X) == 0:
            logger.warning("Not enough data for TFT sequences")
            return {"val_loss": 999.0}
        split = int(len(X) * 0.9)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]
        train_ds = TensorDataset(
            torch.tensor(X_train, device=self.device),
            torch.tensor(y_train, device=self.device),
        )
        loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        best_val = 999.0
        for epoch in range(epochs):
            self.model.train()
            for xb, yb in loader:
                optimizer.zero_grad()
                pred = self.model(xb)
                loss = self._quantile_loss(pred, yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
            self.model.eval()
            with torch.no_grad():
                vp = self.model(torch.tensor(X_val, device=self.device))
                vl = self._quantile_loss(vp, torch.tensor(y_val, device=self.device)).item()
            best_val = min(best_val, vl)
            if (epoch + 1) % 10 == 0:
                logger.info("TFT Epoch %d/%d - val_loss=%.4f", epoch + 1, epochs, vl)
        self._trained = True
        return {"val_loss": best_val}

    def predict(self, features: np.ndarray, seq_len: int = 100) -> dict:
        if not self._trained or self.scaler_mean is None:
            return {"q10": 0.5, "q50": 0.5, "q90": 0.5, "direction_prob": 0.5}
        normed = (features - self.scaler_mean) / self.scaler_std
        if len(normed) < seq_len:
            return {"q10": 0.5, "q50": 0.5, "q90": 0.5, "direction_prob": 0.5}
        seq = normed[-seq_len:]
        tensor = torch.tensor(seq[np.newaxis, :, :].astype(np.float32), device=self.device)
        self.model.eval()
        with torch.no_grad():
            out = self.model(tensor).cpu().numpy()[0]
        q10, q50, q90 = float(out[0]), float(out[1]), float(out[2])
        direction_prob = 1.0 / (1.0 + np.exp(-q50))
        return {"q10": q10, "q50": q50, "q90": q90, "direction_prob": float(direction_prob)}

    def state_dict(self) -> dict:
        return {
            "model": self.model.state_dict(),
            "scaler_mean": self.scaler_mean,
            "scaler_std": self.scaler_std,
            "trained": self._trained,
        }

    def load_state_dict(self, state: dict) -> None:
        self.model.load_state_dict(state["model"])
        self.scaler_mean = state["scaler_mean"]
        self.scaler_std = state["scaler_std"]
        self._trained = state.get("trained", True)
