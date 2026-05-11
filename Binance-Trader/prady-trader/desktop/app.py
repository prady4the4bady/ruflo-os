"""PRADY TRADER — Main desktop application window."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from desktop.theme import DARK_THEME
from desktop.worker import DataWorker, OrchestratorWorker
from desktop.widgets import MetricCard, Separator

from desktop.pages.home import HomePage
from desktop.pages.markets import MarketsPage
from desktop.pages.trading import TradingPage
from desktop.pages.agents import AgentsPage
from desktop.pages.ledger import LedgerPage
from desktop.pages.performance import PerformancePage
from desktop.pages.health import HealthPage
from desktop.pages.strategy import StrategyBuilderPage
from desktop.pages.control import ControlRoomPage
from desktop.pages.settings import SettingsPage


NAV_ITEMS = [
    ("Home", HomePage),
    ("Markets", MarketsPage),
    ("Trading Floor", TradingPage),
    ("Agent Matrix", AgentsPage),
    ("Ledger", LedgerPage),
    ("Performance", PerformancePage),
    ("System Health", HealthPage),
    ("Strategy Builder", StrategyBuilderPage),
    ("Control Room", ControlRoomPage),
    ("Settings", SettingsPage),
]

PAGE_META = [
    ("DESK OVERVIEW", "Home", "Command snapshot across runtime, market pulse, and operator readiness."),
    ("MARKET INTELLIGENCE", "Markets", "Live prices, macro state, provider health, and news flow in one view."),
    ("MISSION CONTROL", "Trading Floor", "Execution, capital domains, and live provider telemetry."),
    ("COUNCIL OVERSIGHT", "Agent Matrix", "Signal quality, voting context, and reasoning breakdowns."),
    ("CAPITAL LEDGER", "Ledger", "Open risk, closed trades, and account domains across paper, testnet, and live."),
    ("P&L ANALYTICS", "Performance", "Equity behavior, outcomes, and risk posture over time."),
    ("OPERATIONS", "System Health", "Infrastructure health, processes, and rate-limiter posture."),
    ("STRATEGY LAB", "Strategy Builder", "Model coverage, prediction posture, and signal-building inputs."),
    ("GOVERNANCE", "Control Room", "Runtime modes, execution routing, and operator controls."),
    ("RUNTIME SETTINGS", "Settings", "Environment snapshot, credentials posture, and configuration reference."),
]


def _configure_qt_fontdir() -> None:
    import os

    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if font_dir.exists():
        os.environ.setdefault("QT_QPA_FONTDIR", str(font_dir))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PRADY TRADER | Autonomous Trading Desk")
        self.setMinimumSize(1200, 760)
        self.resize(1480, 920)

        # ── Central widget ───────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QHBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(286)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(18, 18, 18, 18)
        sb_lay.setSpacing(14)

        brand = QWidget()
        brand_lay = QVBoxLayout(brand)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(2)
        brand_mark = QLabel("AUTONOMOUS CRYPTO DESK")
        brand_mark.setObjectName("brandMark")
        brand_word = QLabel("PRADY TRADER")
        brand_word.setObjectName("brandWord")
        brand_subtitle = QLabel("Execution, oversight, and live telemetry in one control surface.")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_subtitle.setWordWrap(True)
        brand_lay.addWidget(brand_mark)
        brand_lay.addWidget(brand_word)
        brand_lay.addWidget(brand_subtitle)
        sb_lay.addWidget(brand)

        status_label = QLabel("SYSTEM")
        status_label.setObjectName("sidebarSectionLabel")
        sb_lay.addWidget(status_label)

        status_panel = QFrame()
        status_panel.setObjectName("sidebarPanel")
        status_lay = QVBoxLayout(status_panel)
        status_lay.setContentsMargins(16, 14, 16, 14)
        status_lay.setSpacing(6)

        self._status_lbl = QLabel("ENGINE OFFLINE")
        self._status_lbl.setObjectName("sidebarStatValue")
        self._mode_lbl = QLabel("Runtime: PAPER")
        self._mode_lbl.setObjectName("sidebarStat")
        self._cycle_lbl = QLabel("Cycle: #0")
        self._cycle_lbl.setObjectName("sidebarStat")
        self._uptime_lbl = QLabel("Uptime: 0h 0m 0s")
        self._uptime_lbl.setObjectName("sidebarStat")
        self._balance_lbl = QLabel("Balance: $10,000.00")
        self._balance_lbl.setObjectName("sidebarStatValue")

        status_lay.addWidget(self._status_lbl)
        status_lay.addWidget(self._mode_lbl)
        status_lay.addWidget(self._cycle_lbl)
        status_lay.addWidget(self._uptime_lbl)
        status_lay.addWidget(self._balance_lbl)
        sb_lay.addWidget(status_panel)

        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("sidebarSectionLabel")
        sb_lay.addWidget(nav_label)

        # Navigation buttons
        self._nav_buttons: list[QPushButton] = []
        self._pages: list[QWidget] = []
        self._control_room_page: ControlRoomPage | None = None

        self._stack = QStackedWidget()

        for i, (text, PageCls) in enumerate(NAV_ITEMS):
            btn = QPushButton(text)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            sb_lay.addWidget(btn)
            self._nav_buttons.append(btn)

            page = PageCls()
            if PageCls is ControlRoomPage:
                self._control_room_page = page
            self._pages.append(page)
            self._stack.addWidget(page)

        pulse_label = QLabel("MARKET PULSE")
        pulse_label.setObjectName("sidebarSectionLabel")
        sb_lay.addWidget(pulse_label)

        pulse_panel = QFrame()
        pulse_panel.setObjectName("sidebarPanel")
        pulse_lay = QVBoxLayout(pulse_panel)
        pulse_lay.setContentsMargins(16, 14, 16, 14)
        pulse_lay.setSpacing(8)

        price_header = QLabel("Live Prices")
        price_header.setObjectName("sidebarStat")
        pulse_lay.addWidget(price_header)

        self._price_labels: dict[str, QLabel] = {}
        self._prices_container = QVBoxLayout()
        self._prices_container.setContentsMargins(0, 0, 0, 0)
        self._prices_container.setSpacing(2)
        self._prices_widget = QWidget()
        self._prices_widget.setLayout(self._prices_container)
        pulse_lay.addWidget(self._prices_widget)

        fng_header = QLabel("Fear & Greed Index")
        fng_header.setObjectName("sidebarStat")
        pulse_lay.addWidget(fng_header)

        self._fng_value_lbl = QLabel("—")
        self._fng_value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fng_value_lbl.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #8ea2b6; padding: 2px 0;"
        )
        pulse_lay.addWidget(self._fng_value_lbl)

        self._fng_class_lbl = QLabel("")
        self._fng_class_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fng_class_lbl.setStyleSheet("font-size: 11px; color: #8ea2b6; padding: 0;")
        pulse_lay.addWidget(self._fng_class_lbl)

        self._fng_bar = QFrame()
        self._fng_bar.setFixedHeight(8)
        self._fng_bar.setStyleSheet("background: #1c2b3c; border-radius: 4px;")
        pulse_lay.addWidget(self._fng_bar)

        self._fng_fill = QFrame(self._fng_bar)
        self._fng_fill.setFixedHeight(8)
        self._fng_fill.setStyleSheet("background: #8ea2b6; border-radius: 4px;")
        self._fng_fill.setGeometry(0, 0, 0, 8)

        sb_lay.addWidget(pulse_panel)

        sb_lay.addStretch()

        ver = QLabel("v1.0.0  |  production runtime")
        ver.setObjectName("sidebarFooter")
        sb_lay.addWidget(ver)

        root_lay.addWidget(sidebar)

        # ── Main content area ────────────────────────────────
        content_shell = QFrame()
        content_shell.setObjectName("contentShell")
        content_lay = QVBoxLayout(content_shell)
        content_lay.setContentsMargins(24, 20, 24, 20)
        content_lay.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("shellHero")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(22, 20, 22, 20)
        hero_lay.setSpacing(16)

        hero_top = QHBoxLayout()
        hero_top.setSpacing(16)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(4)
        self._hero_eyebrow = QLabel()
        self._hero_eyebrow.setObjectName("shellEyebrow")
        self._hero_title = QLabel()
        self._hero_title.setObjectName("shellTitle")
        self._hero_subtitle = QLabel()
        self._hero_subtitle.setObjectName("shellSubtitle")
        self._hero_subtitle.setWordWrap(True)
        hero_text.addWidget(self._hero_eyebrow)
        hero_text.addWidget(self._hero_title)
        hero_text.addWidget(self._hero_subtitle)
        hero_top.addLayout(hero_text, 1)

        self._hero_chip = QLabel("ENGINE OFFLINE")
        self._hero_chip.setObjectName("shellChip")
        self._hero_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_top.addWidget(self._hero_chip, 0, Qt.AlignmentFlag.AlignTop)
        hero_lay.addLayout(hero_top)

        hero_stats = QHBoxLayout()
        hero_stats.setSpacing(10)
        self._hero_runtime = MetricCard("Runtime")
        self._hero_execution = MetricCard("Execution")
        self._hero_balance = MetricCard("Balance")
        self._hero_cycle = MetricCard("Cycle")
        for card in (self._hero_runtime, self._hero_execution, self._hero_balance, self._hero_cycle):
            hero_stats.addWidget(card)
        hero_lay.addLayout(hero_stats)

        content_lay.addWidget(hero)

        stack_shell = QFrame()
        stack_shell.setObjectName("stackShell")
        stack_lay = QVBoxLayout(stack_shell)
        stack_lay.setContentsMargins(0, 0, 0, 0)
        stack_lay.addWidget(self._stack)
        content_lay.addWidget(stack_shell, 1)

        root_lay.addWidget(content_shell, 1)

        # ── Status bar ───────────────────────────────────────
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._sb_mode = QLabel("PAPER / PAPER")
        self._sb_cycle = QLabel("Cycle #0")
        self._sb_update = QLabel("Waiting for data…")
        self._statusbar.addWidget(self._sb_mode)
        self._statusbar.addWidget(QLabel("  |  "))
        self._statusbar.addWidget(self._sb_cycle)
        self._statusbar.addWidget(QLabel("  |  "))
        self._statusbar.addPermanentWidget(self._sb_update)

        # Select first page
        self._switch_page(0)

        # ── Workers ──────────────────────────────────────────
        self._data_worker = DataWorker(interval=5)
        self._data_worker.data_ready.connect(self._on_data)
        self._data_worker.start()

        self._orch_worker: OrchestratorWorker | None = None

        if self._control_room_page is not None:
            self._control_room_page.start_trading.connect(self._start_orchestrator)
            self._control_room_page.stop_trading.connect(self._stop_orchestrator)

    # ── data update (main thread via signal) ─────────────────
    def _on_data(self, d: dict):
        import time

        # Sidebar
        running = d.get("system_running", False)
        runtime_mode = str(d.get("trading_mode", "paper")).upper()
        execution_environment = str(d.get("execution_environment", "paper")).upper()
        if running:
            self._status_lbl.setText(f"{runtime_mode} ENGINE RUNNING")
            self._status_lbl.setStyleSheet("color: #7cf2d0; font-weight: 700;")
        else:
            self._status_lbl.setText("ENGINE OFFLINE")
            self._status_lbl.setStyleSheet("color: #ffb4ae; font-weight: 700;")

        cyc = d.get("cycle_count", 0)
        self._mode_lbl.setText(f"Runtime: {runtime_mode}")
        self._cycle_lbl.setText(f"Cycle: #{cyc} | Exec: {execution_environment}")
        self._sb_mode.setText(f"  {runtime_mode} / {execution_environment}  ")
        self._sb_cycle.setText(f"  Cycle #{cyc}  ")

        self._uptime_lbl.setText(f"Uptime: {d.get('uptime_str', '0h 0m 0s')}")

        bal = d.get("balance", 10_000)
        self._balance_lbl.setText(f"Balance: ${bal:,.2f}")
        self._hero_runtime.set(runtime_mode)
        self._hero_execution.set(execution_environment)
        self._hero_balance.set(f"${bal:,.2f}")
        self._hero_cycle.set(f"#{cyc}")

        if running:
            self._hero_chip.setText(f"{runtime_mode} ACTIVE • {execution_environment}")
            self._hero_chip.setStyleSheet(
                "background-color: #15362e; color: #7cf2d0; border: 1px solid #2e6b5b; "
                "border-radius: 14px; padding: 6px 10px; font-size: 11px; font-weight: 700;"
            )
        else:
            self._hero_chip.setText("ENGINE OFFLINE")
            self._hero_chip.setStyleSheet(
                "background-color: #3a2d16; color: #ffd27a; border: 1px solid #7f6530; "
                "border-radius: 14px; padding: 6px 10px; font-size: 11px; font-weight: 700;"
            )

        # Prices
        prices = d.get("prices", {})
        # Clear old
        while self._prices_container.count():
            w = self._prices_container.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._price_labels.clear()
        for sym, price in list(prices.items())[:6]:
            lbl = QLabel(f"{sym}: ${price:,.2f}")
            lbl.setObjectName("sidebarTicker")
            self._prices_container.addWidget(lbl)
            self._price_labels[sym] = lbl

        # Fear & Greed — visual gauge update
        fg = d.get("fear_greed", {})
        fv = fg.get("value", 0)
        fc = fg.get("classification", "")
        if fv:
            if fv < 25:
                color, emoji = "#ff4444", "😱"
            elif fv < 45:
                color, emoji = "#ff6b35", "😰"
            elif fv < 55:
                color, emoji = "#ffa726", "😐"
            elif fv < 75:
                color, emoji = "#66bb6a", "😊"
            else:
                color, emoji = "#00d4aa", "🤑"
            self._fng_value_lbl.setText(f"{emoji} {fv}")
            self._fng_value_lbl.setStyleSheet(
                f"font-size: 22px; font-weight: bold; color: {color}; padding: 2px 0;"
            )
            self._fng_class_lbl.setText(fc)
            self._fng_class_lbl.setStyleSheet(f"font-size: 11px; color: {color}; padding: 0;")
            # Update gauge bar width proportionally
            bar_width = self._fng_bar.width()
            fill_w = max(4, int(bar_width * fv / 100))
            self._fng_fill.setFixedWidth(fill_w)
            self._fng_fill.setStyleSheet(
                f"background: {color}; border-radius: 4px;"
            )
        else:
            self._fng_value_lbl.setText("—")
            self._fng_value_lbl.setStyleSheet(
                "font-size: 22px; font-weight: bold; color: #8b949e; padding: 2px 0;"
            )
            self._fng_class_lbl.setText("")

        # Status bar timestamp
        from datetime import datetime
        self._sb_update.setText(f"  Last update: {datetime.now().strftime('%H:%M:%S')}  ")

        # Update only the visible page (performance optimization)
        current_page = self._pages[self._stack.currentIndex()]
        try:
            current_page.update_data(d)
        except Exception as exc:
            print(f"[Page update error] {exc}")

        # Also cache data for when user switches pages
        self._last_data = d

    # ── page switch with cached data ─────────────────────────
    def _switch_page(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == idx)
            btn.setProperty("checked", "true" if i == idx else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        eyebrow, title, subtitle = PAGE_META[idx]
        self._hero_eyebrow.setText(eyebrow)
        self._hero_title.setText(title)
        self._hero_subtitle.setText(subtitle)

        # Immediately update new page with last known data
        if hasattr(self, "_last_data"):
            try:
                self._pages[idx].update_data(self._last_data)
            except Exception:
                pass

    # ── orchestrator control ─────────────────────────────────
    def _start_orchestrator(self, mode: str):
        if self._orch_worker and self._orch_worker.isRunning():
            return
        self._orch_worker = OrchestratorWorker(mode=mode)
        self._orch_worker.status.connect(self._on_orch_status)
        self._orch_worker.start()

    def _stop_orchestrator(self):
        if self._orch_worker:
            self._orch_worker.request_stop()

    def _on_orch_status(self, status: str):
        if self._control_room_page is not None:
            self._control_room_page.set_engine_status(status)

    # ── cleanup ──────────────────────────────────────────────
    def closeEvent(self, event):
        self._data_worker.stop()
        if self._orch_worker and self._orch_worker.isRunning():
            self._orch_worker.request_stop()
            self._orch_worker.wait(5000)
        try:
            from data.free_apis import close_session_sync

            close_session_sync()
        except Exception:
            pass
        event.accept()


def run_app():
    """Entry point — create QApplication, show MainWindow, exec."""
    import os

    os.chdir(ROOT)
    _configure_qt_fontdir()

    app = QApplication(sys.argv)
    app.setApplicationName("PRADY TRADER")
    app.setStyleSheet(DARK_THEME)

    # Configure pyqtgraph if available
    try:
        import pyqtgraph as pg
        pg.setConfigOptions(background="#0e1117", foreground="#e6edf3", antialias=True)
    except ImportError:
        pass

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
