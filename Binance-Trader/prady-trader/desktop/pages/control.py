"""PRADY TRADER — Control Room page."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from desktop.widgets import MetricCard, Separator, page_title, section_label

ROOT = Path(__file__).resolve().parent.parent.parent


class ControlRoomPage(QScrollArea):
    start_trading = pyqtSignal(str)
    stop_trading = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(page_title("Control Room"))

        self._summary = QLabel("Operator controls are standing by.")
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
        self._engine = MetricCard("Engine")
        self._health = MetricCard("Health")
        self._providers = MetricCard("Providers")
        self._cycle = MetricCard("Cycle")
        for card in (self._runtime, self._execution, self._engine, self._health, self._providers, self._cycle):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        layout.addWidget(section_label("Runtime Mode"))
        mode_row = QHBoxLayout()
        self._mode_label = QLabel("Current: <b>PAPER</b>")
        self._mode_label.setStyleSheet("font-size: 14px; padding: 8px;")
        mode_row.addWidget(self._mode_label)

        self._paper_btn = QPushButton("Paper")
        self._paper_btn.setObjectName("successButton")
        self._paper_btn.clicked.connect(lambda: self._switch_mode("paper"))
        mode_row.addWidget(self._paper_btn)

        self._testnet_btn = QPushButton("Testnet")
        self._testnet_btn.setObjectName("warningButton")
        self._testnet_btn.clicked.connect(lambda: self._switch_mode("testnet"))
        mode_row.addWidget(self._testnet_btn)

        self._live_btn = QPushButton("Live")
        self._live_btn.setObjectName("dangerButton")
        self._live_btn.clicked.connect(lambda: self._switch_mode("live"))
        mode_row.addWidget(self._live_btn)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self._execution_hint = QLabel(
            "Paper keeps orders simulated. Testnet routes to Binance Spot Testnet. Live routes to Binance Spot mainnet."
        )
        self._execution_hint.setWordWrap(True)
        self._execution_hint.setStyleSheet("color: #8b949e; padding: 0 8px 8px 8px; font-size: 12px;")
        layout.addWidget(self._execution_hint)

        layout.addWidget(Separator())

        layout.addWidget(section_label("Kill Switch"))
        kill_row = QHBoxLayout()
        self._kill_btn = QPushButton("Activate Kill Switch")
        self._kill_btn.setObjectName("killButton")
        self._kill_btn.clicked.connect(self._activate_kill)
        kill_row.addWidget(self._kill_btn)

        self._clear_kill_btn = QPushButton("Clear Kill Switch")
        self._clear_kill_btn.setObjectName("successButton")
        self._clear_kill_btn.clicked.connect(self._clear_kill)
        kill_row.addWidget(self._clear_kill_btn)
        kill_row.addStretch()
        layout.addLayout(kill_row)

        self._kill_status = QLabel("")
        layout.addWidget(self._kill_status)

        layout.addWidget(Separator())

        layout.addWidget(section_label("Trading Engine"))
        engine_row = QHBoxLayout()
        self._start_btn = QPushButton("Start Paper Trading")
        self._start_btn.setObjectName("successButton")
        self._start_btn.clicked.connect(self._on_start_clicked)
        engine_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop Trading")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        engine_row.addWidget(self._stop_btn)

        self._engine_status = QLabel("Engine: stopped")
        self._engine_status.setStyleSheet("color: #8b949e; padding: 8px;")
        engine_row.addWidget(self._engine_status)
        engine_row.addStretch()
        layout.addLayout(engine_row)

        layout.addWidget(section_label("Operator Notes"))
        self._ops_text = QTextEdit()
        self._ops_text.setReadOnly(True)
        self._ops_text.setMinimumHeight(280)
        layout.addWidget(self._ops_text)
        layout.addStretch()

        self._refresh_kill_status()
        self._update_environment_controls()
        self._update_start_button_label()

    def set_engine_status(self, status: str):
        if status == "running":
            self._engine_status.setText("Engine: running")
            self._engine_status.setStyleSheet("color: #00d4aa; padding: 8px; font-weight: 700;")
            self._engine.set("RUNNING", positive=True)
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
        elif status == "stopped":
            self._engine_status.setText("Engine: stopped")
            self._engine_status.setStyleSheet("color: #8b949e; padding: 8px;")
            self._engine.set("STOPPED")
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(True)
        else:
            self._engine_status.setText(f"Engine: {status}")
            self._engine_status.setStyleSheet("color: #ff9800; padding: 8px;")
            self._engine.set("ATTN", status[:24], False)
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(True)

    def _get_current_mode(self) -> str:
        try:
            from config.settings import get_settings

            return get_settings().trading_mode
        except Exception:
            return "paper"

    def _on_start_clicked(self):
        mode = self._get_current_mode()
        if mode == "live":
            reply = QMessageBox.warning(
                self,
                "Start LIVE Trading",
                "This will route orders against real capital. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.start_trading.emit(mode)
        self.set_engine_status("running")

    def _on_stop_clicked(self):
        self.stop_trading.emit()
        self.set_engine_status("stopped")

    def _update_start_button_label(self):
        mode = self._get_current_mode()
        if mode == "live":
            self._start_btn.setText("Start LIVE Trading")
            self._start_btn.setObjectName("dangerButton")
        elif mode == "testnet":
            self._start_btn.setText("Start TESTNET Trading")
            self._start_btn.setObjectName("warningButton")
        else:
            self._start_btn.setText("Start Paper Trading")
            self._start_btn.setObjectName("successButton")
        self._start_btn.style().unpolish(self._start_btn)
        self._start_btn.style().polish(self._start_btn)

    def _update_environment_controls(self):
        mode = self._get_current_mode()
        execution = "PAPER SIMULATION" if mode == "paper" else "TESTNET SPOT" if mode == "testnet" else "LIVE SPOT"
        self._mode_label.setText(f"Current: <b>{mode.upper()}</b> | Execution: <b>{execution}</b>")
        self._paper_btn.setEnabled(mode != "paper")
        self._testnet_btn.setEnabled(mode != "testnet")
        self._live_btn.setEnabled(mode != "live")

    def _switch_mode(self, mode: str):
        if mode == "live":
            reply = QMessageBox.warning(
                self,
                "Switch to LIVE",
                "This will arm real-money routing. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            from config.settings import apply_runtime_mode

            apply_runtime_mode(mode, persist=True)
        except Exception:
            pass

        try:
            from desktop.worker import DataWorker

            DataWorker._binance_cache = {}
            DataWorker._binance_cache_ts = 0.0
            DataWorker._binance_cache_signature = None
        except Exception:
            pass

        try:
            from dashboard.state import invalidate_account_overview_cache

            invalidate_account_overview_cache()
        except Exception:
            pass

        self._update_environment_controls()
        self._update_start_button_label()

    def _activate_kill(self):
        kill_file = ROOT / "data" / "kill_switch"
        kill_file.parent.mkdir(parents=True, exist_ok=True)
        kill_file.write_text("kill", encoding="utf-8")
        self._refresh_kill_status()

    def _clear_kill(self):
        kill_file = ROOT / "data" / "kill_switch"
        if kill_file.exists():
            kill_file.unlink()
        self._refresh_kill_status()

    def _refresh_kill_status(self):
        kill_file = ROOT / "data" / "kill_switch"
        if kill_file.exists():
            self._kill_status.setText("Kill switch ACTIVE — trading is halted until cleared.")
            self._kill_status.setStyleSheet("color: #ff4444; font-weight: 700; padding: 4px;")
        else:
            self._kill_status.setText("Kill switch clear.")
            self._kill_status.setStyleSheet("color: #00d4aa; padding: 4px;")

    def update_data(self, data: dict):
        runtime = str(data.get("trading_mode", "paper")).upper()
        execution = str(data.get("execution_environment", "paper")).upper()
        health = data.get("health_data", {}) or {}
        overall = str(health.get("overall", "unknown") or "unknown").upper()
        providers = len(data.get("provider_statuses", {}) or {})
        cycle = int(data.get("cycle_count", 0) or 0)

        self._runtime.set(runtime)
        self._execution.set(execution)
        if self._engine_status.text().lower().endswith("running"):
            self._engine.set("RUNNING", positive=True)
        else:
            self._engine.set("STOPPED")
        self._health.set(overall)
        self._providers.set(str(providers))
        self._cycle.set(f"#{cycle}")

        policy = data.get("active_mode_policy", {}) or {}
        self._summary.setText(
            "  |  ".join(
                [
                    f"Runtime {runtime}",
                    f"Execution {execution}",
                    f"Health {overall}",
                    f"Policy {policy.get('title', 'n/a')}",
                    f"Guardrail {policy.get('guardrail', 'n/a')}",
                ]
            )
        )

        process_data = data.get("process_data", {}) or {}
        notes = {
            "runtime_mode": runtime,
            "execution_environment": execution,
            "health": health,
            "process_manager": process_data,
            "kill_switch": bool(data.get("kill_switch")),
            "providers_tracked": providers,
            "latest_decisions": list((data.get("decision_log", []) or [])[-3:]),
        }
        self._ops_text.setPlainText(json.dumps(notes, indent=2, default=str))
        self._refresh_kill_status()
        self._update_environment_controls()
        self._update_start_button_label()