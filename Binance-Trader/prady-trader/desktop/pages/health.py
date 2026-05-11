"""PRADY TRADER — System & API Health page."""

from __future__ import annotations

import platform, psutil

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.widgets import MetricCard, page_title, section_label


class HealthPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        c = QWidget()
        self.setWidget(c)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 8, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(page_title("System Health"))

        # ── Health checks ────────────────────────────────────
        lay.addWidget(section_label("Health Checks"))
        self._checks_area = QVBoxLayout()
        self._checks_widget = QWidget()
        self._checks_widget.setLayout(self._checks_area)
        lay.addWidget(self._checks_widget)

        # ── Process manager ──────────────────────────────────
        lay.addWidget(section_label("Process Manager"))
        self._proc_area = QVBoxLayout()
        self._proc_widget = QWidget()
        self._proc_widget.setLayout(self._proc_area)
        lay.addWidget(self._proc_widget)

        # ── System resources ─────────────────────────────────
        lay.addWidget(section_label("System Resources"))
        res = QGridLayout()

        self._cpu_label = QLabel("CPU")
        self._cpu_bar = self._make_bar()
        self._mem_label = QLabel("Memory")
        self._mem_bar = self._make_bar()
        self._disk_label = QLabel("Disk")
        self._disk_bar = self._make_bar()

        res.addWidget(self._cpu_label, 0, 0)
        res.addWidget(self._cpu_bar, 0, 1)
        res.addWidget(self._mem_label, 1, 0)
        res.addWidget(self._mem_bar, 1, 1)
        res.addWidget(self._disk_label, 2, 0)
        res.addWidget(self._disk_bar, 2, 1)
        lay.addLayout(res)

        # ── API rate limiter ─────────────────────────────────
        lay.addWidget(section_label("API Rate Limiter"))
        self._api_area = QVBoxLayout()
        self._api_widget = QWidget()
        self._api_widget.setLayout(self._api_area)
        lay.addWidget(self._api_widget)

        lay.addStretch()

    @staticmethod
    def _make_bar() -> QProgressBar:
        b = QProgressBar()
        b.setMinimum(0)
        b.setMaximum(100)
        b.setFixedHeight(22)
        b.setStyleSheet("""
            QProgressBar {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
                text-align: center;
                color: #e6edf3;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #00d4aa, stop:1 #00b894);
                border-radius: 3px;
            }
        """)
        return b

    def update_data(self, d: dict):
        # ── health checks ────────────────────────────────────
        self._clear(self._checks_area)

        hd = d.get("health_data", {})
        if hd:
            overall = hd.get("overall", "unknown")
            emoji = {"healthy": "✅", "degraded": "⚠️"}.get(overall, "❌")
            uptime = hd.get("uptime_sec", 0)
            h, m = int(uptime // 3600), int((uptime % 3600) // 60)
            lbl = QLabel(f"{emoji}  Overall: <b>{overall.upper()}</b>  —  Uptime: {h}h {m}m")
            lbl.setStyleSheet("font-size: 14px; padding: 6px;")
            self._checks_area.addWidget(lbl)

            for name, chk in hd.get("checks", {}).items():
                st = chk.get("status", "unknown")
                msg = chk.get("message", "")
                fails = chk.get("consecutive_failures", 0)
                e = {"healthy": "✅", "degraded": "⚠️"}.get(st, "❌")
                txt = f"{e}  <b>{name}</b>: {msg}"
                if fails:
                    txt += f"  (failures: {fails})"
                l = QLabel(txt)
                l.setStyleSheet("font-size: 12px; padding: 2px 8px;")
                self._checks_area.addWidget(l)
        else:
            l = QLabel("  Health monitor not active — start orchestrator to see data")
            l.setStyleSheet("color: #8b949e; padding: 8px;")
            self._checks_area.addWidget(l)

        # ── process manager ──────────────────────────────────
        self._clear(self._proc_area)
        pd = d.get("process_data", {})
        if pd:
            lbl = QLabel(f"  Manager PID: <b>{pd.get('manager_pid', '?')}</b>  —  "
                         f"Uptime: {pd.get('uptime_sec', 0):.0f}s")
            lbl.setStyleSheet("font-size: 12px; padding: 4px;")
            self._proc_area.addWidget(lbl)

            for name, proc in pd.get("processes", {}).items():
                alive = proc.get("alive", False)
                pid = proc.get("pid", "?")
                restarts = proc.get("restart_count", 0)
                e = "🟢" if alive else "🔴"
                l = QLabel(f"  {e} <b>{name}</b>: PID={pid}, restarts={restarts}")
                l.setStyleSheet("font-size: 12px; padding: 2px 8px;")
                self._proc_area.addWidget(l)
        else:
            l = QLabel("  Process manager not active")
            l.setStyleSheet("color: #8b949e; padding: 8px;")
            self._proc_area.addWidget(l)

        # ── system resources ─────────────────────────────────
        try:
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            self._cpu_bar.setValue(int(cpu))
            self._cpu_bar.setFormat(f"CPU: {cpu:.0f}%")
            self._update_bar_color(self._cpu_bar, cpu)

            mp = mem.percent
            self._mem_bar.setValue(int(mp))
            self._mem_bar.setFormat(f"RAM: {mp:.0f}%  ({mem.used / 1e9:.1f} / {mem.total / 1e9:.1f} GB)")
            self._update_bar_color(self._mem_bar, mp)

            dp = disk.percent
            self._disk_bar.setValue(int(dp))
            self._disk_bar.setFormat(f"Disk: {dp:.0f}%  ({disk.used / 1e9:.0f} / {disk.total / 1e9:.0f} GB)")
            self._update_bar_color(self._disk_bar, dp)
        except Exception:
            pass

        # ── API rate limiter ─────────────────────────────────
        self._clear(self._api_area)
        try:
            from utils.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            stats = rl.get_stats()
            if stats:
                for name, s in sorted(stats.items()):
                    if name == "default":
                        continue
                    used = s.get("daily_used", 0)
                    limit = s.get("daily_limit", 0)
                    tokens = s.get("tokens_available", 0)
                    pct = (used / limit * 100) if limit else 0
                    bar = self._make_bar()
                    bar.setValue(min(int(pct), 100))
                    bar.setFormat(f"{name}: {used}/{limit}  (tokens: {tokens:.0f})")
                    self._update_bar_color(bar, pct)
                    self._api_area.addWidget(bar)
            else:
                l = QLabel("  Rate limiter empty — will populate when API calls are made")
                l.setStyleSheet("color: #8b949e; padding: 8px;")
                self._api_area.addWidget(l)
        except Exception:
            l = QLabel("  Rate limiter not available")
            l.setStyleSheet("color: #8b949e; padding: 8px;")
            self._api_area.addWidget(l)

    @staticmethod
    def _update_bar_color(bar: QProgressBar, pct: float):
        if pct > 80:
            color = "#ff4444"
        elif pct > 60:
            color = "#ff9800"
        else:
            color = "#00d4aa"
        bar.setStyleSheet(bar.styleSheet().replace("#00d4aa", color).replace("#00b894", color))

    @staticmethod
    def _clear(layout):
        while layout.count():
            w = layout.takeAt(0).widget()
            if w:
                w.deleteLater()
