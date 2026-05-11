"""
PRADY TRADER — Bidirectional LSTM price direction predictor (PyTorch).
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config.constants import LSTM_DENSE_1, LSTM_FEATURES, LSTM_HIDDEN_1, LSTM_HIDDEN_2, LSTM_SEQUENCE_LEN

logger = logging.getLogger("prady.ml.lstm_model")


class BiLSTMModel(nn.Module):
    def __init__(
        self,
        input_size: int = LSTM_FEATURES,
        hidden1: int = LSTM_HIDDEN_1,
        hidden2: int = LSTM_HIDDEN_2,
        dense: int = LSTM_DENSE_1,
    ):
        super().__init__()
        self.lstm1 = nn.LSTM(input_size, hidden1, batch_first=True, bidirectional=True)
        self.lstm2 = nn.LSTM(hidden1 * 2, hidden2, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(0.3)
        self.fc1 = nn.Linear(hidden2 * 2, dense)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(dense, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm1(x)
        out = self.dropout(out)
        out, _ = self.lstm2(out)
        out = self.dropout(out)
        out = out[:, -1, :]  # last time step
        out = self.relu(self.fc1(out))
        out = self.dropout(out)
        out = self.sigmoid(self.fc2(out))
        return out.squeeze(-1)


class LSTMPredictor:
    """Wrapper for training and inference of BiLSTM model."""

    def __init__(self, device: Optional[str] = None, input_size: int = LSTM_FEATURES):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.input_size = input_size
        self.model = BiLSTMModel(input_size=input_size).to(self.device)
        self.scaler_mean: Optional[np.ndarray] = None
        self.scaler_std: Optional[np.ndarray] = None
        self._trained = False

    def _create_sequences(
        self, data: np.ndarray, seq_len: int = LSTM_SEQUENCE_LEN
    ) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        for i in range(len(data) - seq_len):
            X.append(data[i : i + seq_len, :-1])
            y.append(data[i + seq_len - 1, -1])
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)

    def fit(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        epochs: int = 50,
        batch_size: int = 64,
        lr: float = 0.001,
        validation_split: float = 0.1,
    ) -> dict:
        self.scaler_mean = features.mean(axis=0)
        self.scaler_std = features.std(axis=0) + 1e-8
        normed = (features - self.scaler_mean) / self.scaler_std
        combined = np.column_stack([normed, targets])
        X, y = self._create_sequences(combined, LSTM_SEQUENCE_LEN)
        if len(X) == 0:
            logger.warning("Not enough data for LSTM sequences")
            return {"val_accuracy": 0.0}
        split = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]
        train_ds = TensorDataset(
            torch.tensor(X_train, device=self.device),
            torch.tensor(y_train, device=self.device),
        )
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
        criterion = nn.BCELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
        best_val_acc = 0.0
        for epoch in range(epochs):
            self.model.train()
            epoch_loss = 0.0
            for xb, yb in train_loader:
                optimizer.zero_grad()
                pred = self.model(xb)
                loss = criterion(pred, yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                epoch_loss += loss.item()
            self.model.eval()
            with torch.no_grad():
                val_pred = self.model(torch.tensor(X_val, device=self.device))
                val_labels = torch.tensor(y_val, device=self.device)
                val_loss = criterion(val_pred, val_labels).item()
                val_acc = ((val_pred > 0.5).float() == val_labels).float().mean().item()
            scheduler.step(val_loss)
            best_val_acc = max(best_val_acc, val_acc)
            if (epoch + 1) % 10 == 0:
                logger.info(
                    "LSTM Epoch %d/%d - loss=%.4f val_loss=%.4f val_acc=%.4f",
                    epoch + 1, epochs, epoch_loss / len(train_loader), val_loss, val_acc,
                )
        self._trained = True
        return {"val_accuracy": best_val_acc}

    def predict(self, features: np.ndarray) -> float:
        if not self._trained or self.scaler_mean is None:
            return 0.5
        normed = (features - self.scaler_mean) / self.scaler_std
        if len(normed) < LSTM_SEQUENCE_LEN:
            return 0.5
        seq = normed[-LSTM_SEQUENCE_LEN:]
        tensor = torch.tensor(seq[np.newaxis, :, :].astype(np.float32), device=self.device)
        self.model.eval()
        with torch.no_grad():
            prob = self.model(tensor).item()
        return prob

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
