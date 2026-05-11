"""PRADY TRADER — Live Trading page (enhanced with predictions & risk)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QGridLayout,
)

from desktop.widgets import MetricCard, StatusCard, colored_item, make_table, page_title, section_label, Separator

try:
    import pyqtgraph as pg
    HAS_PG = True
except ImportError:
    HAS_PG = False


def _badge_color(level: str, *, active: bool = False) -> str:
    if active:
        return "#58a6ff"
    return {
        "ok": "#00d4aa",
        "healthy": "#00d4aa",
        "info": "#8b949e",
        "unknown": "#8b949e",
        "warning": "#ffcc00",
        "disabled": "#6e7681",
        "degraded": "#ff9800",
        "error": "#ff4444",
    }.get(str(level or "info").lower(), "#8b949e")


def _format_money(value) -> str:
    return f"${float(value or 0.0):,.2f}"


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class TradingPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        c = QWidget()
        self.setWidget(c)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 8, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(page_title("Trading Floor"))

        # Status banner
        self._status = QLabel("Waiting for data…")
        self._status.setObjectName("statusBannerWarn")
        lay.addWidget(self._status)

        self._policy_banner = QLabel("Runtime policy loading…")
        self._policy_banner.setWordWrap(True)
        self._policy_banner.setStyleSheet(
            "background: #0d1b2a; border: 1px solid #1f6feb; border-radius: 6px; "
            "padding: 8px 12px; font-size: 12px; color: #c9d1d9;"
        )
        lay.addWidget(self._policy_banner)

        # ── Row 1: Metrics ───────────────────────────────────
        mrow = QHBoxLayout()
        mrow.setSpacing(10)
        self._balance = MetricCard("Balance")
        self._equity = MetricCard("Equity")
        self._daily_pnl = MetricCard("Daily PnL")
        self._win_rate = MetricCard("Win Rate")
        self._trades = MetricCard("Total Trades")
        self._open_cnt = MetricCard("Open Positions")
        for w in (self._balance, self._equity, self._daily_pnl,
                  self._win_rate, self._trades, self._open_cnt):
            mrow.addWidget(w)
        lay.addLayout(mrow)

        # ── Capital domains ─────────────────────────────────
        lay.addWidget(Separator())
        lay.addWidget(section_label("🧭  Capital Domains"))

        self._acct_mode = QLabel("⏳  Loading capital domains...")
        self._acct_mode.setStyleSheet(
            "background: #161b22; border: 1px solid #30363d; border-radius: 6px; "
            "padding: 8px 12px; font-size: 12px; color: #8b949e;"
        )
        lay.addWidget(self._acct_mode)

        domain_row = QHBoxLayout()
        domain_row.setSpacing(10)
        self._domain_cards = {
            "paper": StatusCard("📝 Paper Domain"),
            "testnet": StatusCard("🧪 Testnet Domain"),
            "live": StatusCard("🌐 Live Domain"),
        }
        for card in self._domain_cards.values():
            domain_row.addWidget(card)
        lay.addLayout(domain_row)

        # Account summary cards
        acct_row = QHBoxLayout()
        acct_row.setSpacing(10)
        self._acct_wallet = MetricCard("Active Domain Equity")
        self._acct_available = MetricCard("Active Free / Balance")
        self._acct_unrealized = MetricCard("Active Domain PnL")
        self._acct_margin = MetricCard("Assets / Positions")
        self._acct_pos_margin = MetricCard("Exec Free USDT")
        self._acct_order_margin = MetricCard("Exec Open Orders")
        for w in (self._acct_wallet, self._acct_available, self._acct_unrealized,
                  self._acct_margin, self._acct_pos_margin, self._acct_order_margin):
            acct_row.addWidget(w)
        lay.addLayout(acct_row)

        lay.addWidget(section_label("💼  Mode Asset Ledgers"))

        self._paper_assets_title = section_label("📝  Paper Ledger")
        lay.addWidget(self._paper_assets_title)
        self._paper_asset_table = make_table(
            ["Symbol", "Direction", "Qty", "Entry", "Current", "PnL"],
            max_h=180,
        )
        lay.addWidget(self._paper_asset_table)

        self._testnet_assets_title = section_label("🧪  Testnet Exchange Ledger")
        lay.addWidget(self._testnet_assets_title)
        self._testnet_asset_table = make_table(
            ["Asset", "Free", "Locked", "Total", "Est. USDT"],
            max_h=180,
        )
        lay.addWidget(self._testnet_asset_table)

        self._live_assets_title = section_label("🌐  Live Wealth Ledger")
        lay.addWidget(self._live_assets_title)
        self._live_asset_table = make_table(
            ["Asset", "Free", "Locked", "Total", "Est. USDT"],
            max_h=180,
        )
        lay.addWidget(self._live_asset_table)

        lay.addWidget(Separator())

        # ── Open positions table ─────────────────────────────
        lay.addWidget(section_label("Open Positions"))
        self._pos_table = make_table(["Symbol", "Direction", "Entry", "Current", "PnL", "Hold Time"])
        lay.addWidget(self._pos_table)

        # ── Equity curve ─────────────────────────────────────
        lay.addWidget(section_label("Equity Curve"))
        if HAS_PG:
            self._chart = pg.PlotWidget()
            self._chart.setBackground("#0e1117")
            self._chart.setMinimumHeight(250)
            self._chart.showGrid(x=True, y=True, alpha=0.15)
            self._chart.setLabel("left", "Equity ($)")
            self._chart.setLabel("bottom", "Trade #")
            self._equity_pen = pg.mkPen("#00d4aa", width=2)
            self._equity_line = self._chart.plot(pen=self._equity_pen)
            lay.addWidget(self._chart)
        else:
            self._chart = None
            lay.addWidget(QLabel("pyqtgraph not available"))

        # ── Market overview ──────────────────────────────────
        lay.addWidget(section_label("Market Overview"))
        mg = QHBoxLayout()
        mg.setSpacing(10)
        self._mcap = MetricCard("Total Market Cap")
        self._btcdom = MetricCard("BTC Dominance")
        self._hashrate = MetricCard("Hash Rate")
        self._mempool = MetricCard("Mempool")
        for w in (self._mcap, self._btcdom, self._hashrate, self._mempool):
            mg.addWidget(w)
        lay.addLayout(mg)

        # ── Live Prices ──────────────────────────────────────
        lay.addWidget(section_label("💰  Live Prices"))
        self._prices_row = QHBoxLayout()
        self._prices_row.setSpacing(10)
        self._price_cards: dict[str, MetricCard] = {}
        self._prices_widget = QWidget()
        self._prices_widget.setLayout(self._prices_row)
        lay.addWidget(self._prices_widget)

        lay.addWidget(Separator())

        # ── ML Predictions ───────────────────────────────────
        lay.addWidget(section_label("🤖  ML Ensemble Predictions"))
        self._pred_table = make_table(
            ["Symbol", "Direction", "Probability", "Agreement", "LSTM", "XGBoost", "TFT"],
            max_h=180,
        )
        lay.addWidget(self._pred_table)

        # ── Risk Metrics ─────────────────────────────────────
        lay.addWidget(section_label("⚠️  Risk Metrics"))
        rrow = QHBoxLayout()
        rrow.setSpacing(10)
        self._max_drawdown = MetricCard("Max Drawdown")
        self._sharpe = MetricCard("Sharpe Ratio")
        self._profit_factor = MetricCard("Profit Factor")
        self._avg_win = MetricCard("Avg Win")
        self._avg_loss = MetricCard("Avg Loss")
        self._consec_losses = MetricCard("Max Consec. Losses")
        for w in (self._max_drawdown, self._sharpe, self._profit_factor,
                  self._avg_win, self._avg_loss, self._consec_losses):
            rrow.addWidget(w)
        lay.addLayout(rrow)

        # ── Sentiment Gauge ──────────────────────────────────
        lay.addWidget(section_label("🧠  Market Sentiment"))
        sent_row = QHBoxLayout()
        sent_row.setSpacing(16)
        # Fear & Greed bar
        fg_box = QVBoxLayout()
        self._fg_label = QLabel("Fear & Greed: —")
        self._fg_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #c9d1d9;")
        self._fg_bar = QProgressBar()
        self._fg_bar.setRange(0, 100)
        self._fg_bar.setValue(50)
        self._fg_bar.setFixedHeight(22)
        self._fg_bar.setTextVisible(True)
        self._fg_bar.setFormat("%v / 100")
        fg_box.addWidget(self._fg_label)
        fg_box.addWidget(self._fg_bar)
        sent_row.addLayout(fg_box, 1)
        # Sentiment classification
        self._sent_class = QLabel("")
        self._sent_class.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sent_class.setStyleSheet(
            "background: #161b22; border: 1px solid #30363d; "
            "border-radius: 8px; padding: 12px; font-size: 14px; font-weight: bold; min-width: 120px;"
        )
        sent_row.addWidget(self._sent_class)
        lay.addLayout(sent_row)

        lay.addWidget(Separator())

        # ── Council Decisions — detailed per-agent breakdown ─
        lay.addWidget(section_label("Council Decisions — Per-Agent Signals"))
        self._decisions_table = make_table(
            ["Symbol", "Action", "Score", "Conf", "Oracle", "Prophet", "Sentinel",
             "Arbiter", "OracleExt", "Debater"],
            max_h=200,
        )
        lay.addWidget(self._decisions_table)

        # ── Decision reasoning area ──────────────────────────
        lay.addWidget(section_label("Decision Reasoning"))
        self._reasoning_area = QVBoxLayout()
        self._reasoning_widget = QWidget()
        self._reasoning_widget.setLayout(self._reasoning_area)
        lay.addWidget(self._reasoning_widget)

        lay.addWidget(Separator())

        lay.addWidget(section_label("🔎  Live Provider Telemetry"))
        self._provider_health = QLabel("Waiting for provider telemetry…")
        self._provider_health.setWordWrap(True)
        self._provider_health.setStyleSheet(
            "background: #161b22; border: 1px solid #30363d; border-radius: 6px; "
            "padding: 8px 12px; font-size: 12px; color: #8b949e;"
        )
        lay.addWidget(self._provider_health)
        self._provider_grid_widget = QWidget()
        self._provider_grid = QGridLayout(self._provider_grid_widget)
        self._provider_grid.setContentsMargins(0, 0, 0, 0)
        self._provider_grid.setSpacing(10)
        lay.addWidget(self._provider_grid_widget)

        lay.addWidget(Separator())

        # ── Agent Activity Log ───────────────────────────────
        lay.addWidget(section_label("📋  Agent Activity Log"))
        self._activity_log = QTextEdit()
        self._activity_log.setReadOnly(True)
        self._activity_log.setMaximumHeight(250)
        self._activity_log.setStyleSheet(
            "background: #0d1117; border: 1px solid #30363d; border-radius: 6px; "
            "color: #c9d1d9; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px; padding: 8px;"
        )
        lay.addWidget(self._activity_log)

        lay.addWidget(Separator())

        # ── Trending Coins ───────────────────────────────────
        lay.addWidget(section_label("🔥  Trending Coins"))
        self._trending_area = QHBoxLayout()
        self._trending_widget = QWidget()
        self._trending_widget.setLayout(self._trending_area)
        lay.addWidget(self._trending_widget)

        lay.addStretch()

    # ── update ───────────────────────────────────────────────
    def update_data(self, d: dict):
        running = d.get("system_running", False)
        cyc = d.get("cycle_count", 0)
        trading_mode = str(d.get("trading_mode", "paper")).lower()
        execution_environment = str(d.get("execution_environment", "paper")).upper()
        execution_label = "simulation" if execution_environment == "PAPER" else f"{execution_environment} spot"
        if running:
            if trading_mode == "live":
                status_prefix = "LIVE"
            elif trading_mode == "testnet":
                status_prefix = "TESTNET"
            else:
                status_prefix = "PAPER"
            self._status.setText(f"🟢  {status_prefix} trading active ({execution_label}) — Cycle #{cyc}")
            self._status.setObjectName("statusBannerOk")
        else:
            self._status.setText("🔴  Orchestrator not running — press Start in Settings")
            self._status.setObjectName("statusBannerWarn")
        self._status.setStyleSheet(self._status.styleSheet())

        active_policy = d.get("active_mode_policy", {}) or {}
        if active_policy:
            accent = "#00d4aa" if trading_mode == "live" else "#ffcc00" if trading_mode == "testnet" else "#58a6ff"
            self._policy_banner.setText(
                f"{active_policy.get('title', trading_mode.upper())} | "
                f"Goal: {active_policy.get('primary_goal', '—')} | "
                f"Guardrail: {active_policy.get('guardrail', '—')}"
            )
            self._policy_banner.setStyleSheet(
                f"background: #0d1117; border: 1px solid {accent}; border-radius: 6px; "
                f"padding: 8px 12px; font-size: 12px; color: #c9d1d9;"
            )
        else:
            self._policy_banner.setText("Runtime policy metadata not available yet")
            self._policy_banner.setStyleSheet(
                "background: #161b22; border: 1px solid #30363d; border-radius: 6px; "
                "padding: 8px 12px; font-size: 12px; color: #8b949e;"
            )

        # Metrics
        bal = d.get("balance", 10_000)
        ret = d.get("total_return_pct", 0)
        self._balance.set(f"${bal:,.2f}", f"{ret:+.2f}%" if ret else "", ret >= 0 if ret else None)
        self._equity.set(f"${d.get('equity', 10_000):,.2f}")
        dp = d.get("daily_pnl", 0)
        self._daily_pnl.set(f"${dp:,.2f}", f"{dp:+.2f}", dp >= 0)
        wr = d.get("win_rate", 0)
        self._win_rate.set(f"{wr:.1%}" if isinstance(wr, float) and wr <= 1 else f"{wr}%")
        self._trades.set(str(d.get("total_trades", 0)))
        ops = d.get("open_positions", [])
        self._open_cnt.set(str(len(ops)))

        # Positions table
        self._pos_table.setRowCount(len(ops))
        for i, p in enumerate(ops):
            self._pos_table.setItem(i, 0, QTableWidgetItem(str(p.get("symbol", ""))))
            dr = p.get("direction", "")
            self._pos_table.setItem(i, 1, colored_item(dr, "#00d4aa" if dr == "LONG" else "#ff4444"))
            self._pos_table.setItem(i, 2, QTableWidgetItem(f"${p.get('entry_price', 0):,.2f}"))
            self._pos_table.setItem(i, 3, QTableWidgetItem(f"${p.get('current_price', 0):,.2f}"))
            pnl = p.get("pnl", 0)
            self._pos_table.setItem(i, 4, colored_item(f"${pnl:,.2f}", "#00d4aa" if pnl >= 0 else "#ff4444"))
            hold = p.get("holding_minutes", 0)
            self._pos_table.setItem(i, 5, QTableWidgetItem(f"{int(hold)}m"))

        # Equity chart
        if self._chart:
            trades = d.get("closed_trades", [])
            if trades:
                init = d.get("initial_balance", 10_000)
                vals = [init]
                for t in trades:
                    vals.append(vals[-1] + t.get("pnl", 0))
                self._equity_line.setData(list(range(len(vals))), vals)

        # Market overview
        ov = d.get("market_overview", {})
        cap = ov.get("total_market_cap", 0)
        chg = ov.get("market_cap_change_24h", 0)
        self._mcap.set(f"${cap / 1e12:.2f}T" if cap else "—", f"{chg:+.1f}%" if chg else "", chg >= 0 if chg else None)
        self._btcdom.set(f"{ov.get('btc_dominance', 0):.1f}%" if ov.get("btc_dominance") else "—")
        hr = ov.get("btc_hash_rate", 0)
        self._hashrate.set(f"{hr / 1e12:.1f} TH/s" if hr else "—")
        mp = ov.get("btc_mempool", 0)
        self._mempool.set(f"{mp:,} txs" if mp else "—")

        # ── Council decisions with per-agent signals ─────────
        self._update_decisions(d)

        # ── ML predictions ───────────────────────────────────
        self._update_predictions(d)

        # ── Live prices ──────────────────────────────────────
        self._update_prices(d)

        # ── Capital domain transparency ─────────────────────
        self._update_mode_domains(d)

        # ── Risk metrics ─────────────────────────────────────
        self._update_risk_metrics(d)

        # ── Sentiment gauge ──────────────────────────────────
        self._update_sentiment(d)

        # ── Provider telemetry ───────────────────────────────
        self._update_provider_statuses(d)

        # ── Agent activity log ───────────────────────────────
        self._update_activity_log(d)

        # ── Trending coins ───────────────────────────────────
        self._update_trending(d)

    def _update_predictions(self, d: dict):
        """Show ML ensemble predictions per symbol."""
        preds = d.get("ensemble_predictions", {})
        self._pred_table.setRowCount(len(preds))
        for row, (sym, p) in enumerate(preds.items()):
            direction = p.get("direction", "—")
            prob = p.get("probability", 0.5)
            agreement = p.get("model_agreement", 0)
            individual = p.get("individual", {})

            dc = "#00d4aa" if direction == "UP" else "#ff4444" if direction == "DOWN" else "#8b949e"
            self._pred_table.setItem(row, 0, QTableWidgetItem(sym))
            self._pred_table.setItem(row, 1, colored_item(f"{'▲' if direction == 'UP' else '▼'} {direction}", dc))
            self._pred_table.setItem(row, 2, colored_item(f"{prob:.1%}", dc))

            # Model agreement color: green > 0.7, yellow > 0.4, red otherwise
            ac = "#00d4aa" if agreement > 0.7 else "#ff9800" if agreement > 0.4 else "#ff4444"
            self._pred_table.setItem(row, 3, colored_item(f"{agreement:.1%}", ac))

            # Individual model predictions
            for col, model in enumerate(["lstm", "xgboost", "tft"]):
                val = individual.get(model, 0.5)
                mc = "#00d4aa" if val > 0.55 else "#ff4444" if val < 0.45 else "#8b949e"
                self._pred_table.setItem(row, 4 + col, colored_item(f"{val:.1%}", mc))

    def _update_prices(self, d: dict):
        """Update live price ticker cards."""
        prices = d.get("prices", {})
        # Create cards for new symbols
        for sym in prices:
            if sym not in self._price_cards:
                card = MetricCard(sym)
                self._price_cards[sym] = card
                self._prices_row.addWidget(card)
        for sym, price in prices.items():
            if sym in self._price_cards:
                self._price_cards[sym].set(f"${price:,.2f}")

    def _update_mode_domains(self, d: dict):
        """Update explicit paper, testnet, and live domain views."""
        views = d.get("mode_account_views", {}) or {}
        active_mode = str(d.get("trading_mode", "paper")).lower()
        execution_environment = str(d.get("execution_environment", active_mode)).lower()

        if not views:
            self._acct_mode.setText("⚠️  Capital domains unavailable — waiting for shared dashboard state")
            self._acct_mode.setStyleSheet(
                "background: #1c1208; border: 1px solid #5a3e00; border-radius: 6px; "
                "padding: 8px 12px; font-size: 12px; color: #ff9800;"
            )
            self._paper_asset_table.setRowCount(0)
            self._testnet_asset_table.setRowCount(0)
            self._live_asset_table.setRowCount(0)
            for card in self._domain_cards.values():
                card.set(value="—", badge="WAIT", badge_color="#8b949e", subtitle="", details="")
            for card in (
                self._acct_wallet,
                self._acct_available,
                self._acct_unrealized,
                self._acct_margin,
                self._acct_pos_margin,
                self._acct_order_margin,
            ):
                card.set("—")
            return

        active_view = views.get(active_mode, {})
        execution_view = views.get(execution_environment, active_view)

        for mode, card in self._domain_cards.items():
            view = views.get(mode, {})
            status_level = str(view.get("status_level", "info")).lower()
            detail_lines = []
            if view.get("status_detail"):
                detail_lines.append(str(view.get("status_detail")))
            metrics = (
                f"Trades {int(view.get('total_trades', 0) or 0)} | "
                f"Open {int(view.get('open_positions', 0) or 0)} | "
                f"Return {float(view.get('total_return_pct', 0.0) or 0.0):+.2f}%"
            )
            detail_lines.append(metrics)
            card.set_title(str(view.get("title", mode.title())))
            card.set(
                value=_format_money(view.get("equity", 0.0)),
                badge="ACTIVE" if view.get("is_active") else status_level.upper(),
                badge_color=_badge_color(status_level, active=bool(view.get("is_active"))),
                subtitle=str(view.get("role_label", "")),
                details="\n".join(part for part in detail_lines if part),
            )

        status_level = str(active_view.get("status_level", "info")).lower()
        if status_level == "error":
            mode_bg, mode_border, mode_color = "#2d0d12", "#f85149", "#ff4444"
        elif status_level in {"warning", "degraded"}:
            mode_bg, mode_border, mode_color = "#1c1208", "#5a3e00", "#ff9800"
        elif active_mode == "live":
            mode_bg, mode_border, mode_color = "#081c0e", "#005a1a", "#00d4aa"
        elif active_mode == "testnet":
            mode_bg, mode_border, mode_color = "#1c1c08", "#5a5a00", "#ffcc00"
        else:
            mode_bg, mode_border, mode_color = "#0d1b2a", "#1f6feb", "#58a6ff"

        banner_parts = [
            f"Active domain: {active_view.get('title', active_mode.upper())}",
            f"Execution: {execution_environment.upper()}",
            str(active_view.get("status_detail", "No domain status available")),
        ]
        if active_view.get("primary_goal"):
            banner_parts.append(f"Goal: {active_view.get('primary_goal')}")
        if execution_view.get("account_label"):
            banner_parts.append(f"Execution ledger: {execution_view.get('account_label')}")
        banner_parts.append("Telemetry refreshes on the shared live-state cycle")
        self._acct_mode.setText("  |  ".join(banner_parts))
        self._acct_mode.setStyleSheet(
            f"background: {mode_bg}; border: 1px solid {mode_border}; border-radius: 6px; "
            f"padding: 8px 12px; font-size: 12px; color: {mode_color}; font-weight: bold;"
        )

        self._acct_wallet.set(_format_money(active_view.get("equity", d.get("equity", 0.0))))
        self._acct_available.set(_format_money(active_view.get("balance", d.get("balance", 0.0))))
        active_pnl = float(active_view.get("total_pnl", d.get("total_pnl", 0.0)) or 0.0)
        self._acct_unrealized.set(_format_money(active_pnl), f"{active_pnl:+,.2f}", active_pnl >= 0)
        self._acct_margin.set(str(int(active_view.get("asset_count", active_view.get("open_positions", 0)) or 0)))
        self._acct_pos_margin.set(_format_money(execution_view.get("balance", 0.0)))
        self._acct_order_margin.set(str(int(execution_view.get("open_order_count", 0) or 0)))

        paper_view = views.get("paper", {})
        testnet_view = views.get("testnet", {})
        live_view = views.get("live", {})

        self._paper_assets_title.setText(
            f"📝  {paper_view.get('account_label', 'Paper Trading Ledger')} — {paper_view.get('status_detail', 'No paper snapshot available')}"
        )
        self._testnet_assets_title.setText(
            f"🧪  {testnet_view.get('account_label', 'Testnet Exchange Ledger')} — {testnet_view.get('status_detail', 'No testnet snapshot available')}"
        )
        self._live_assets_title.setText(
            f"🌐  {live_view.get('account_label', 'Live Wealth Ledger')} — {live_view.get('status_detail', 'No live snapshot available')}"
        )

        self._fill_paper_table(self._paper_asset_table, paper_view.get("asset_rows", []))
        self._fill_balance_table(self._testnet_asset_table, testnet_view.get("asset_rows", []))
        self._fill_balance_table(self._live_asset_table, live_view.get("asset_rows", []))

    def _fill_paper_table(self, table, positions):
        table.setRowCount(len(positions))
        for i, pos in enumerate(positions):
            table.setItem(i, 0, QTableWidgetItem(str(pos.get("symbol", ""))))
            direction = str(pos.get("direction", ""))
            direction_color = "#00d4aa" if direction == "LONG" else "#ff4444" if direction == "SHORT" else "#8b949e"
            table.setItem(i, 1, colored_item(direction, direction_color))
            table.setItem(i, 2, QTableWidgetItem(f"{float(pos.get('quantity', 0.0) or 0.0):,.6f}".rstrip("0").rstrip(".")))
            table.setItem(i, 3, QTableWidgetItem(_format_money(pos.get("entry_price", 0.0))))
            table.setItem(i, 4, QTableWidgetItem(_format_money(pos.get("current_price", 0.0))))
            pnl = float(pos.get("pnl", 0.0) or 0.0)
            table.setItem(i, 5, colored_item(_format_money(pnl), "#00d4aa" if pnl >= 0 else "#ff4444"))

    def _fill_balance_table(self, table, balances):
        table.setRowCount(len(balances))
        for i, balance in enumerate(balances):
            free = balance.get("free", 0)
            locked = balance.get("locked", 0)
            total = balance.get("total", free + locked)
            estimated = balance.get("estimated_usdt", 0)

            table.setItem(i, 0, QTableWidgetItem(str(balance.get("asset", ""))))
            table.setItem(i, 1, QTableWidgetItem(f"{free:,.8f}".rstrip("0").rstrip(".")))
            table.setItem(i, 2, QTableWidgetItem(f"{locked:,.8f}".rstrip("0").rstrip(".")))
            table.setItem(i, 3, QTableWidgetItem(f"{total:,.8f}".rstrip("0").rstrip(".")))
            table.setItem(i, 4, QTableWidgetItem(f"${estimated:,.2f}"))

    def _update_provider_statuses(self, d: dict):
        statuses = d.get("provider_statuses", {}) or {}
        rate_stats = d.get("rate_limiter_stats", {}) or {}
        health_data = d.get("health_data", {}) or {}
        checks = health_data.get("checks", {}) if isinstance(health_data.get("checks"), dict) else {}

        overall = str(health_data.get("overall", "unknown")).lower() if health_data else "unknown"
        summary_parts = [f"Health: {overall.upper()}"]
        for name in ("binance_api", "cycle_freshness", "redis"):
            check = checks.get(name, {}) if isinstance(checks, dict) else {}
            if check:
                summary_parts.append(f"{name.replace('_', ' ').title()}: {str(check.get('status', 'unknown')).upper()}")
        summary_parts.append(f"Providers tracked: {len(statuses)}")
        if overall == "healthy":
            color = "#00d4aa"
        elif overall == "degraded":
            color = "#ff9800"
        elif overall == "critical":
            color = "#ff4444"
        else:
            color = "#8b949e"
        self._provider_health.setText("  |  ".join(summary_parts))
        self._provider_health.setStyleSheet(
            f"background: #161b22; border: 1px solid {color}; border-radius: 6px; "
            f"padding: 8px 12px; font-size: 12px; color: #c9d1d9;"
        )

        _clear_layout(self._provider_grid)
        provider_names = {name for name in statuses.keys()} | {name for name in rate_stats.keys() if name != "default"}
        if not provider_names:
            placeholder = QLabel("Provider telemetry will populate after feeds and reasoning backends run.")
            placeholder.setStyleSheet("color: #8b949e; padding: 8px;")
            self._provider_grid.addWidget(placeholder, 0, 0)
            return

        priority = [
            "coingecko",
            "alternative_me",
            "blockchain_com",
            "yahoo_finance",
            "newsapi",
            "newsdata_io",
            "cryptocompare",
            "coinapi",
            "bitquery",
            "freecryptoapi",
            "ollama",
            "nvidia_nim",
            "messari",
            "rss_feeds",
        ]
        rank = {name: idx for idx, name in enumerate(priority)}
        ordered_names = sorted(
            provider_names,
            key=lambda name: (rank.get(name, len(rank) + 1), str(statuses.get(name, {}).get("display_name", name)).lower()),
        )

        for index, name in enumerate(ordered_names):
            info = dict(statuses.get(name, {}))
            display_name = str(info.get("display_name", name.replace("_", " ").title()))
            status = str(info.get("status", "unknown")).lower()
            rate = rate_stats.get(name, {}) if isinstance(rate_stats.get(name, {}), dict) else {}
            subtitle = f"{str(info.get('category', 'data')).title()} · {'Optional' if info.get('optional', True) else 'Core'}"

            details = []
            if rate:
                daily_limit = rate.get("daily_limit")
                daily_limit_text = str(daily_limit) if daily_limit not in (None, 0) else "∞"
                details.append(
                    f"Tokens {float(rate.get('tokens_available', 0.0) or 0.0):.1f} · Daily {int(rate.get('daily_used', 0) or 0)}/{daily_limit_text}"
                )
            if info.get("last_success_iso"):
                details.append(f"Last success {info.get('last_success_iso')}")
            failures = int(info.get("consecutive_failures", 0) or 0)
            if failures:
                details.append(f"Failures {failures}")
            if status in {"error", "degraded"} and info.get("last_error"):
                details.append(str(info.get("last_error"))[:140])

            card = StatusCard(display_name)
            card.set(
                value=str(info.get("message", status.upper() or "UNKNOWN")),
                badge=status.upper(),
                badge_color=_badge_color(status),
                subtitle=subtitle,
                details="\n".join(details),
            )
            self._provider_grid.addWidget(card, index // 3, index % 3)

    def _update_risk_metrics(self, d: dict):
        """Compute and display risk metrics from closed trades."""
        trades = d.get("closed_trades", [])
        init_bal = d.get("initial_balance", 10_000)

        if not trades:
            self._max_drawdown.set("—")
            self._sharpe.set("—")
            self._profit_factor.set("—")
            self._avg_win.set("—")
            self._avg_loss.set("—")
            self._consec_losses.set("0")
            return

        pnls = [t.get("pnl", 0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        import statistics

        # Max drawdown
        peak = init_bal
        max_dd = 0.0
        equity = init_bal
        for p in pnls:
            equity += p
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        dd_color = "#00d4aa" if max_dd < 0.05 else "#ff9800" if max_dd < 0.15 else "#ff4444"
        self._max_drawdown.set(f"{max_dd:.1%}", positive=max_dd < 0.05)

        # Sharpe ratio (annualized, assuming ~252 trading days, ~24 trades/day)
        if len(pnls) >= 2:
            mean_r = statistics.mean(pnls)
            std_r = statistics.stdev(pnls)
            sharpe = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0.0
            self._sharpe.set(f"{sharpe:.2f}", positive=sharpe > 0)
        else:
            self._sharpe.set("—")

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
        self._profit_factor.set(f"{pf:.2f}" if pf < 100 else "∞", positive=pf > 1)

        # Avg win / loss
        avg_w = statistics.mean(wins) if wins else 0
        avg_l = statistics.mean(losses) if losses else 0
        self._avg_win.set(f"${avg_w:+,.2f}", positive=True)
        self._avg_loss.set(f"${avg_l:+,.2f}", positive=False)

        # Max consecutive losses
        max_streak = 0
        streak = 0
        for p in pnls:
            if p < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        self._consec_losses.set(str(max_streak), positive=max_streak < 3)

    def _update_sentiment(self, d: dict):
        """Update Fear & Greed gauge and sentiment display."""
        fg = d.get("fear_greed", {})
        value = fg.get("value", 0)
        classification = fg.get("classification", "Unknown")

        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 0

        self._fg_bar.setValue(value)
        self._fg_label.setText(f"Fear & Greed Index: {value}")

        # Color the progress bar based on value
        if value <= 25:
            bar_color = "#ff4444"  # Extreme Fear
            text_color = "#ff4444"
        elif value <= 45:
            bar_color = "#ff9800"  # Fear
            text_color = "#ff9800"
        elif value <= 55:
            bar_color = "#8b949e"  # Neutral
            text_color = "#c9d1d9"
        elif value <= 75:
            bar_color = "#00d4aa"  # Greed
            text_color = "#00d4aa"
        else:
            bar_color = "#00ff88"  # Extreme Greed
            text_color = "#00ff88"

        self._fg_bar.setStyleSheet(
            f"QProgressBar {{ background: #21262d; border: 1px solid #30363d; border-radius: 6px; text-align: center; color: #c9d1d9; font-weight: bold; }}"
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 5px; }}"
        )
        self._sent_class.setText(f"<span style='color:{text_color}'>{classification}</span>")

    def _update_decisions(self, d: dict):
        """Update council decisions table with per-agent signal breakdown."""
        decision_log = d.get("decision_log", [])
        latest: dict = {}
        for entry in decision_log:
            latest[entry.get("symbol", "")] = entry

        if not latest:
            for sym, dec in d.get("last_decisions", {}).items():
                latest[sym] = {
                    "symbol": sym,
                    "action": dec.get("action", "N/A"),
                    "weighted_score": dec.get("weighted_score", 0),
                    "confidence": dec.get("confidence", 0),
                    "reasoning": dec.get("reasoning", ""),
                    "agent_signals": {},
                }

        self._decisions_table.setRowCount(len(latest))
        agent_names = ["oracle", "prophet", "sentinel", "arbiter", "oracle_extended", "debater"]

        for row, (sym, entry) in enumerate(latest.items()):
            act = entry.get("action", "N/A")
            score = entry.get("weighted_score", 0)
            conf = entry.get("confidence", 0)
            signals = entry.get("agent_signals", {})

            act_color = "#00d4aa" if act == "LONG" else "#ff4444" if act == "SHORT" else "#8b949e"
            self._decisions_table.setItem(row, 0, QTableWidgetItem(sym))
            self._decisions_table.setItem(row, 1, colored_item(act, act_color))
            self._decisions_table.setItem(row, 2, QTableWidgetItem(f"{score:.1f}"))
            self._decisions_table.setItem(row, 3, QTableWidgetItem(f"{conf:.2f}"))

            for col, agent in enumerate(agent_names):
                sig = signals.get(agent, {})
                direction = sig.get("direction", "—")
                agent_conf = sig.get("confidence", 0)
                if direction in ("LONG", "BUY"):
                    color = "#00d4aa"
                    text = f"▲ {agent_conf:.0%}"
                elif direction in ("SHORT", "SELL"):
                    color = "#ff4444"
                    text = f"▼ {agent_conf:.0%}"
                else:
                    color = "#8b949e"
                    text = f"— {agent_conf:.0%}"
                self._decisions_table.setItem(row, 4 + col, colored_item(text, color))

        # Decision reasoning
        while self._reasoning_area.count():
            w = self._reasoning_area.takeAt(0).widget()
            if w:
                w.deleteLater()

        if latest:
            for sym, entry in latest.items():
                reasoning = entry.get("reasoning", "")
                if reasoning:
                    lbl = QLabel(f"<b>{sym}</b>: {reasoning[:300]}")
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet(
                        "background: #161b22; border: 1px solid #30363d; "
                        "border-radius: 6px; padding: 8px; font-size: 11px; color: #c9d1d9;"
                    )
                    self._reasoning_area.addWidget(lbl)

                signals = entry.get("agent_signals", {})
                for agent_name, sig in signals.items():
                    agent_reasoning = sig.get("reasoning", "")
                    if agent_reasoning:
                        direction = sig.get("direction", "?")
                        ac = sig.get("confidence", 0)
                        dc = "#00d4aa" if direction in ("LONG", "BUY") else "#ff4444" if direction in ("SHORT", "SELL") else "#6e7681"
                        agent_lbl = QLabel(
                            f"  <span style='color:#58a6ff'>{agent_name}</span>"
                            f" → <span style='color:{dc}'>{direction}</span>"
                            f" (conf={ac:.2f}): <span style='color:#8b949e'>{agent_reasoning[:200]}</span>"
                        )
                        agent_lbl.setWordWrap(True)
                        agent_lbl.setStyleSheet("font-size: 11px; padding: 2px 12px;")
                        self._reasoning_area.addWidget(agent_lbl)
        else:
            lbl = QLabel("  No council decisions yet — start the orchestrator from Settings")
            lbl.setStyleSheet("color: #8b949e; padding: 8px;")
            self._reasoning_area.addWidget(lbl)

    def _update_activity_log(self, d: dict):
        """Update the agent activity log from structured.jsonl."""
        activity = d.get("agent_activity", [])
        if not activity:
            self._activity_log.setHtml(
                "<span style='color:#8b949e'>No agent activity yet — "
                "start the orchestrator from Settings page</span>"
            )
            return

        lines = []
        for entry in reversed(activity):
            ts = entry.get("timestamp", "")
            level = entry.get("level", "INFO")
            module = entry.get("module", "")
            msg = entry.get("message", "")

            if level in ("ERROR", "CRITICAL"):
                lc = "#ff4444"
            elif level == "WARNING":
                lc = "#ff9800"
            elif "council" in module.lower() or "agent" in module.lower():
                lc = "#58a6ff"
            else:
                lc = "#8b949e"

            for name in ("Oracle", "Prophet", "Sentinel", "Arbiter", "Debater", "Warden", "Executor"):
                if name.lower() in msg.lower():
                    lc = "#58a6ff"
                    break

            ts_short = ts[11:19] if len(ts) >= 19 else ts
            lines.append(
                f"<span style='color:#484f58'>{ts_short}</span> "
                f"<span style='color:{lc}'>[{module}]</span> "
                f"<span style='color:#c9d1d9'>{msg}</span>"
            )
        self._activity_log.setHtml("<br>".join(lines[-40:]))

    def _update_trending(self, d: dict):
        """Update trending coins display."""
        while self._trending_area.count():
            w = self._trending_area.takeAt(0).widget()
            if w:
                w.deleteLater()

        trending = d.get("trending", [])
        if trending:
            for coin in trending[:8]:
                symbol = coin.get("symbol", "?")
                rank = coin.get("market_cap_rank", "—")
                lbl = QLabel(f"<b>{symbol}</b><br><span style='color:#8b949e'>#{rank}</span>")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet(
                    "background: #161b22; border: 1px solid #30363d; "
                    "border-radius: 8px; padding: 10px 16px; font-size: 12px; min-width: 70px;"
                )
                self._trending_area.addWidget(lbl)
        else:
            lbl = QLabel("  No trending data available")
            lbl.setStyleSheet("color: #8b949e; padding: 8px;")
            self._trending_area.addWidget(lbl)
