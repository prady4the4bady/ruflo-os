"""PRADY TRADER — Ledger and capital-domain page."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from desktop.widgets import MetricCard, StatusCard, colored_item, make_table, page_title, section_label


def _format_money(value: float | int | None) -> str:
    return f"${float(value or 0.0):,.2f}"


def _badge_color(level: str, *, active: bool = False) -> str:
    if active:
        return "#58a6ff"
    return {
        "ok": "#00d4aa",
        "healthy": "#00d4aa",
        "info": "#8b949e",
        "unknown": "#8b949e",
        "warning": "#ffcc00",
        "degraded": "#ff9800",
        "error": "#ff4444",
        "disabled": "#6e7681",
    }.get(str(level or "info").lower(), "#8b949e")


class LedgerPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(page_title("Ledger"))

        self._banner = QLabel("Waiting for capital domains…")
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            "background: #121b25; border: 1px solid #223142; border-radius: 12px; "
            "padding: 10px 12px; color: #d6e3ef; font-size: 12px;"
        )
        layout.addWidget(self._banner)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self._balance = MetricCard("Balance")
        self._equity = MetricCard("Equity")
        self._total_pnl = MetricCard("Total PnL")
        self._trades = MetricCard("Total Trades")
        self._win_rate = MetricCard("Win Rate")
        self._open_positions = MetricCard("Open Positions")
        for card in (
            self._balance,
            self._equity,
            self._total_pnl,
            self._trades,
            self._win_rate,
            self._open_positions,
        ):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        layout.addWidget(section_label("Capital Domains"))
        domains = QHBoxLayout()
        domains.setSpacing(10)
        self._domain_cards = {
            "paper": StatusCard("Paper"),
            "testnet": StatusCard("Testnet"),
            "live": StatusCard("Live"),
        }
        for card in self._domain_cards.values():
            domains.addWidget(card)
        layout.addLayout(domains)

        layout.addWidget(section_label("Open Positions"))
        self._open_table = make_table(["Symbol", "Direction", "Qty", "Entry", "Current", "PnL"], max_h=220)
        layout.addWidget(self._open_table)

        layout.addWidget(section_label("Recent Closed Trades"))
        self._closed_table = make_table(["Symbol", "Direction", "Entry", "Exit", "PnL", "Reason"], max_h=240)
        layout.addWidget(self._closed_table)

        layout.addWidget(section_label("Paper Ledger"))
        self._paper_table = make_table(["Symbol", "Direction", "Qty", "Entry", "Current", "PnL"], max_h=180)
        layout.addWidget(self._paper_table)

        layout.addWidget(section_label("Testnet Ledger"))
        self._testnet_table = make_table(["Asset", "Free", "Locked", "Total", "Est. USDT"], max_h=180)
        layout.addWidget(self._testnet_table)

        layout.addWidget(section_label("Live Ledger"))
        self._live_table = make_table(["Asset", "Free", "Locked", "Total", "Est. USDT"], max_h=180)
        layout.addWidget(self._live_table)
        layout.addStretch()

    def update_data(self, data: dict):
        balance = float(data.get("balance", 0.0) or 0.0)
        equity = float(data.get("equity", 0.0) or 0.0)
        total_pnl = float(data.get("total_pnl", 0.0) or 0.0)
        total_trades = int(data.get("total_trades", 0) or 0)
        win_rate = float(data.get("win_rate", 0.0) or 0.0)
        open_positions = list(data.get("open_positions", []) or [])

        self._balance.set(_format_money(balance))
        self._equity.set(_format_money(equity))
        self._total_pnl.set(_format_money(total_pnl), f"{total_pnl:+,.2f}", total_pnl >= 0)
        self._trades.set(str(total_trades))
        self._win_rate.set(f"{win_rate:.1%}")
        self._open_positions.set(str(len(open_positions)))

        views = data.get("mode_account_views", {}) or {}
        active_mode = str(data.get("trading_mode", "paper")).lower()
        execution_environment = str(data.get("execution_environment", active_mode)).lower()
        active_view = views.get(active_mode, {}) if isinstance(views.get(active_mode), dict) else {}
        execution_view = views.get(execution_environment, active_view) if isinstance(views.get(execution_environment), dict) else active_view

        if active_view:
            banner_parts = [
                f"Active domain {active_view.get('title', active_mode.upper())}",
                f"Role {active_view.get('role_label', 'capital ledger')}",
                str(active_view.get("status_detail", "State synced from live data")),
            ]
            if execution_view.get("account_label"):
                banner_parts.append(f"Execution ledger {execution_view.get('account_label')}")
            self._banner.setText("  |  ".join(banner_parts))
        else:
            self._banner.setText("Capital domains are waiting for the shared state writer to publish fresh snapshots.")

        for mode, card in self._domain_cards.items():
            view = views.get(mode, {}) if isinstance(views.get(mode), dict) else {}
            status_level = str(view.get("status_level", "info") or "info")
            card.set(
                value=_format_money(view.get("equity", 0.0)),
                badge="ACTIVE" if view.get("is_active") else status_level.upper(),
                badge_color=_badge_color(status_level, active=bool(view.get("is_active"))),
                subtitle=str(view.get("role_label", "Awaiting domain telemetry")),
                details=(
                    f"{int(view.get('asset_count', view.get('open_positions', 0)) or 0)} asset(s)\n"
                    f"Trades {int(view.get('total_trades', 0) or 0)} | Return {float(view.get('total_return_pct', 0.0) or 0.0):+.2f}%"
                ),
            )

        self._open_table.setRowCount(len(open_positions))
        for row, position in enumerate(open_positions):
            direction = str(position.get("direction", "") or "")
            color = "#00d4aa" if direction == "LONG" else "#ff4444" if direction == "SHORT" else "#8b949e"
            self._open_table.setCellWidget(row, 0, QLabel(str(position.get("symbol", "—"))))
            self._open_table.setItem(row, 1, colored_item(direction or "—", color))
            self._open_table.setCellWidget(row, 2, QLabel(f"{float(position.get('quantity', 0.0) or 0.0):,.6f}".rstrip("0").rstrip(".")))
            self._open_table.setCellWidget(row, 3, QLabel(_format_money(position.get("entry_price", 0.0))))
            self._open_table.setCellWidget(row, 4, QLabel(_format_money(position.get("current_price", 0.0))))
            self._open_table.setItem(row, 5, colored_item(_format_money(position.get("pnl", 0.0)), "#00d4aa" if float(position.get("pnl", 0.0) or 0.0) >= 0 else "#ff4444"))

        closed_trades = list(data.get("closed_trades", []) or [])[-20:]
        self._closed_table.setRowCount(len(closed_trades))
        for row, trade in enumerate(reversed(closed_trades)):
            direction = str(trade.get("direction", "") or "")
            color = "#00d4aa" if direction == "LONG" else "#ff4444" if direction == "SHORT" else "#8b949e"
            self._closed_table.setCellWidget(row, 0, QLabel(str(trade.get("symbol", "—"))))
            self._closed_table.setItem(row, 1, colored_item(direction or "—", color))
            self._closed_table.setCellWidget(row, 2, QLabel(_format_money(trade.get("entry_price", 0.0))))
            self._closed_table.setCellWidget(row, 3, QLabel(_format_money(trade.get("exit_price", 0.0))))
            pnl = float(trade.get("pnl", 0.0) or 0.0)
            self._closed_table.setItem(row, 4, colored_item(_format_money(pnl), "#00d4aa" if pnl >= 0 else "#ff4444"))
            self._closed_table.setCellWidget(row, 5, QLabel(str(trade.get("exit_reason", "—"))))

        self._populate_paper_table(self._paper_table, (views.get("paper", {}) or {}).get("asset_rows", []))
        self._populate_balance_table(self._testnet_table, (views.get("testnet", {}) or {}).get("asset_rows", []))
        self._populate_balance_table(self._live_table, (views.get("live", {}) or {}).get("asset_rows", []))

    def _populate_paper_table(self, table, rows):
        rows = list(rows or [])
        table.setRowCount(len(rows))
        for row, position in enumerate(rows):
            direction = str(position.get("direction", "") or "")
            color = "#00d4aa" if direction == "LONG" else "#ff4444" if direction == "SHORT" else "#8b949e"
            table.setCellWidget(row, 0, QLabel(str(position.get("symbol", "—"))))
            table.setItem(row, 1, colored_item(direction or "—", color))
            table.setCellWidget(row, 2, QLabel(f"{float(position.get('quantity', 0.0) or 0.0):,.6f}".rstrip("0").rstrip(".")))
            table.setCellWidget(row, 3, QLabel(_format_money(position.get("entry_price", 0.0))))
            table.setCellWidget(row, 4, QLabel(_format_money(position.get("current_price", 0.0))))
            table.setItem(row, 5, colored_item(_format_money(position.get("pnl", 0.0)), "#00d4aa" if float(position.get("pnl", 0.0) or 0.0) >= 0 else "#ff4444"))

    def _populate_balance_table(self, table, rows):
        rows = list(rows or [])
        table.setRowCount(len(rows))
        for row, balance in enumerate(rows):
            free = float(balance.get("free", 0.0) or 0.0)
            locked = float(balance.get("locked", 0.0) or 0.0)
            total = float(balance.get("total", free + locked) or 0.0)
            estimated = float(balance.get("estimated_usdt", 0.0) or 0.0)
            table.setCellWidget(row, 0, QLabel(str(balance.get("asset", "—"))))
            table.setCellWidget(row, 1, QLabel(f"{free:,.8f}".rstrip("0").rstrip(".")))
            table.setCellWidget(row, 2, QLabel(f"{locked:,.8f}".rstrip("0").rstrip(".")))
            table.setCellWidget(row, 3, QLabel(f"{total:,.8f}".rstrip("0").rstrip(".")))
            table.setCellWidget(row, 4, QLabel(_format_money(estimated)))