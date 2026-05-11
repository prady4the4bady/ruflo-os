"""PRADY TRADER - Runtime settings reference page."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from desktop.widgets import MetricCard, Separator, clear_layout, page_title, section_label

ROOT = Path(__file__).resolve().parent.parent.parent


def _mask_secret(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return "not configured"
    if len(value) <= 8:
        return "configured"
    return f"{value[:4]}...{value[-4:]}"


def _format_json(payload: object) -> str:
    return json.dumps(payload, indent=2, default=str)


class SettingsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        container = QWidget()
        self.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(page_title("Settings"))

        self._summary = QLabel("Waiting for configuration snapshot...")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(
            "background: #121b25; border: 1px solid #223142; border-radius: 12px; "
            "padding: 10px 12px; color: #d6e3ef; font-size: 12px;"
        )
        layout.addWidget(self._summary)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self._runtime = MetricCard("Runtime")
        self._execution = MetricCard("Execution")
        self._providers = MetricCard("Providers")
        self._predictions = MetricCard("Predictions")
        self._pairs = MetricCard("Pairs")
        self._news = MetricCard("News")
        for card in (
            self._runtime,
            self._execution,
            self._providers,
            self._predictions,
            self._pairs,
            self._news,
        ):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        layout.addWidget(section_label("Configuration Snapshot"))
        self._config_text = QTextEdit()
        self._config_text.setReadOnly(True)
        self._config_text.setMinimumHeight(280)
        layout.addWidget(self._config_text)

        layout.addWidget(Separator())

        layout.addWidget(section_label("Credentials Posture"))
        self._credentials_text = QTextEdit()
        self._credentials_text.setReadOnly(True)
        self._credentials_text.setMinimumHeight(180)
        layout.addWidget(self._credentials_text)

        layout.addWidget(Separator())

        layout.addWidget(section_label("Environment Notes"))
        self._notes = QTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setMinimumHeight(220)
        layout.addWidget(self._notes)

        layout.addWidget(Separator())

        layout.addWidget(section_label("Latest News"))
        self._news_widget = QWidget()
        self._news_area = QVBoxLayout(self._news_widget)
        self._news_area.setContentsMargins(0, 0, 0, 0)
        self._news_area.setSpacing(8)
        layout.addWidget(self._news_widget)

        layout.addStretch()

        self._refresh_config()

    def _refresh_config(self) -> None:
        try:
            from config.settings import get_settings

            settings = get_settings()
            config_snapshot = {
                "runtime_mode": settings.trading_mode,
                "execution_environment": settings.execution_environment,
                "trading_pairs": settings.trading_pairs,
                "database_url": settings.database_url,
                "redis_url": settings.redis_url or "not configured",
                "ollama_host": settings.ollama_host,
                "ollama_model": settings.ollama_model,
                "nvidia_nim_enabled": bool(settings.nvidia_nim_api_key),
                "nvidia_nim_model": settings.nvidia_nim_model,
                "effective_min_confidence": settings.effective_min_confidence,
                "max_risk_per_trade": settings.max_risk_per_trade,
                "max_daily_loss": settings.max_daily_loss,
                "max_concurrent_positions": settings.max_concurrent_positions,
                "default_leverage": settings.default_leverage,
                "max_hold_minutes": settings.max_hold_minutes,
                "daily_profit_target": settings.daily_profit_target,
                "provider_flags": {
                    "newsapi": settings.enable_newsapi,
                    "newsdata": settings.enable_newsdata,
                    "cryptocompare": settings.enable_cryptocompare,
                    "coinapi": settings.enable_coinapi,
                    "bitquery": settings.enable_bitquery,
                    "freecrypto": settings.enable_freecrypto,
                    "ollama_reasoning": settings.enable_ollama_reasoning,
                    "nvidia_reasoning": settings.enable_nvidia_nim_reasoning,
                },
                "kill_switch_present": (ROOT / "data" / "kill_switch").exists(),
            }
            self._config_text.setPlainText(_format_json(config_snapshot))

            credentials = {
                "live_credentials": settings.has_live_account_credentials,
                "testnet_credentials": settings.has_testnet_account_credentials,
                "live_api_key": _mask_secret(settings.live_binance_api_key),
                "testnet_api_key": _mask_secret(settings.testnet_binance_api_key),
                "telegram_bot": _mask_secret(settings.telegram_bot_token),
                "freecrypto_api": _mask_secret(settings.freecrypto_api_key),
                "nvidia_nim": _mask_secret(settings.nvidia_nim_api_key),
            }
            self._credentials_text.setPlainText(_format_json(credentials))
        except Exception as exc:
            self._config_text.setPlainText(f"Error loading config: {exc}")
            self._credentials_text.setPlainText(f"Error loading credentials posture: {exc}")

    def update_data(self, data: dict) -> None:
        try:
            from config.settings import get_settings

            settings = get_settings()
            runtime = settings.trading_mode.upper()
            execution = settings.execution_environment.upper()
            pair_count = len(settings.trading_pairs)
        except Exception:
            runtime = str(data.get("trading_mode", "paper") or "paper").upper()
            execution = str(data.get("execution_environment", "paper") or "paper").upper()
            pair_count = len(data.get("prices", {}) or {})

        provider_count = len(data.get("provider_statuses", {}) or {})
        prediction_count = len(data.get("ensemble_predictions", {}) or {})
        news_items = len(data.get("news", []) or [])
        health = str((data.get("health_data", {}) or {}).get("overall", "unknown") or "unknown").upper()

        self._runtime.set(runtime)
        self._execution.set(execution)
        self._providers.set(str(provider_count), positive=provider_count > 0)
        self._predictions.set(str(prediction_count), positive=prediction_count > 0)
        self._pairs.set(str(pair_count), positive=pair_count > 0)
        self._news.set(str(news_items), positive=news_items > 0)

        self._summary.setText(
            "  |  ".join(
                [
                    f"Runtime {runtime}",
                    f"Execution {execution}",
                    f"Providers {provider_count}",
                    f"Predictions {prediction_count}",
                    f"Health {health}",
                ]
            )
        )

        self._refresh_config()

        notes = {
            "active_mode_policy": data.get("active_mode_policy", {}),
            "health": data.get("health_data", {}),
            "journal_stats": data.get("journal_stats", {}),
            "process_manager": data.get("process_data", {}),
            "provider_statuses": data.get("provider_statuses", {}),
            "mode_account_views": data.get("mode_account_views", {}),
            "binance_account": data.get("binance_account", {}),
            "kill_switch": data.get("kill_switch", False),
        }
        self._notes.setPlainText(_format_json(notes))

        clear_layout(self._news_area)
        news = list(data.get("news", []) or [])
        if news:
            for article in news[:10]:
                sentiment = str(article.get("sentiment", "neutral") or "neutral").upper()
                title = str(article.get("title", "Untitled") or "Untitled")
                source = str(article.get("source", "Unknown source") or "Unknown source")
                label = QLabel(f"[{sentiment}] {title}\nSource: {source}")
                label.setWordWrap(True)
                label.setStyleSheet(
                    "background: #161b22; border: 1px solid #30363d; "
                    "border-radius: 6px; padding: 8px 10px; font-size: 12px;"
                )
                self._news_area.addWidget(label)
        else:
            empty_label = QLabel("No news articles available")
            empty_label.setStyleSheet("color: #8b949e; padding: 8px;")
            self._news_area.addWidget(empty_label)