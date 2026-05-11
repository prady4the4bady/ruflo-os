"""PRADY TRADER — Performance page (enhanced with risk analytics)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QProgressBar,
)

from desktop.widgets import MetricCard, colored_item, make_table, page_title, section_label, Separator

try:
    import pyqtgraph as pg
    HAS_PG = True
except ImportError:
    HAS_PG = False


class PerformancePage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        c = QWidget()
        self.setWidget(c)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 8, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(page_title("Performance"))

        # Stats row
        mrow = QHBoxLayout()
        mrow.setSpacing(10)
        self._total = MetricCard("Total Trades")
        self._wr = MetricCard("Win Rate")
        self._tpnl = MetricCard("Total PnL")
        self._dpnl = MetricCard("Daily PnL")
        self._best = MetricCard("Best Trade")
        self._worst = MetricCard("Worst Trade")
        for w in (self._total, self._wr, self._tpnl, self._dpnl, self._best, self._worst):
            mrow.addWidget(w)
        lay.addLayout(mrow)

        # Equity curve
        lay.addWidget(section_label("Equity Curve"))
        if HAS_PG:
            self._chart = pg.PlotWidget()
            self._chart.setBackground("#0e1117")
            self._chart.setMinimumHeight(280)
            self._chart.showGrid(x=True, y=True, alpha=0.15)
            self._chart.setLabel("left", "Equity ($)")
            self._chart.setLabel("bottom", "Trade #")
            self._line = self._chart.plot(pen=pg.mkPen("#00d4aa", width=2))
            lay.addWidget(self._chart)
        else:
            self._chart = None

        # PnL histogram
        lay.addWidget(section_label("PnL Distribution"))
        if HAS_PG:
            self._hist_chart = pg.PlotWidget()
            self._hist_chart.setBackground("#0e1117")
            self._hist_chart.setMinimumHeight(200)
            self._hist_chart.setMaximumHeight(250)
            self._hist_chart.showGrid(y=True, alpha=0.15)
            self._hist_chart.setLabel("left", "Count")
            self._hist_chart.setLabel("bottom", "PnL ($)")
            lay.addWidget(self._hist_chart)
        else:
            self._hist_chart = None

        # Trade log
        lay.addWidget(section_label("Recent Trades"))
        self._trade_table = make_table(
            ["Symbol", "Direction", "Entry", "Exit", "PnL", "Duration"],
            max_h=350,
        )
        lay.addWidget(self._trade_table)

        lay.addWidget(Separator())

        # ── Risk Analytics ───────────────────────────────────
        lay.addWidget(section_label("⚠️  Risk Analytics"))
        rrow = QHBoxLayout()
        rrow.setSpacing(10)
        self._max_drawdown = MetricCard("Max Drawdown")
        self._sharpe = MetricCard("Sharpe Ratio")
        self._sortino = MetricCard("Sortino Ratio")
        self._profit_factor = MetricCard("Profit Factor")
        self._avg_rr = MetricCard("Avg Risk:Reward")
        self._expectancy = MetricCard("Expectancy")
        for w in (self._max_drawdown, self._sharpe, self._sortino,
                  self._profit_factor, self._avg_rr, self._expectancy):
            rrow.addWidget(w)
        lay.addLayout(rrow)

        # ── Win/Loss Streaks ─────────────────────────────────
        lay.addWidget(section_label("📊  Win/Loss Distribution"))
        streak_row = QHBoxLayout()
        streak_row.setSpacing(10)
        self._win_streak = MetricCard("Best Win Streak")
        self._loss_streak = MetricCard("Worst Loss Streak")
        self._avg_hold_w = MetricCard("Avg Hold (Win)")
        self._avg_hold_l = MetricCard("Avg Hold (Loss)")
        self._long_wr = MetricCard("Long Win Rate")
        self._short_wr = MetricCard("Short Win Rate")
        for w in (self._win_streak, self._loss_streak, self._avg_hold_w,
                  self._avg_hold_l, self._long_wr, self._short_wr):
            streak_row.addWidget(w)
        lay.addLayout(streak_row)

        lay.addStretch()

    def update_data(self, d: dict):
        self._total.set(str(d.get("total_trades", 0)))
        wr = d.get("win_rate", 0)
        self._wr.set(f"{wr:.1%}")
        tp = d.get("total_pnl", 0)
        self._tpnl.set(f"${tp:+,.2f}", positive=tp >= 0)
        dp = d.get("daily_pnl", 0)
        self._dpnl.set(f"${dp:+,.2f}", positive=dp >= 0)
        bt = d.get("best_trade", 0)
        self._best.set(f"${bt:+,.2f}", positive=bt >= 0)
        wt = d.get("worst_trade", 0)
        self._worst.set(f"${wt:+,.2f}", positive=wt >= 0)

        trades = d.get("closed_trades", [])

        # Equity
        if self._chart and trades:
            init = d.get("initial_balance", 10_000)
            vals = [init]
            for t in trades:
                vals.append(vals[-1] + t.get("pnl", 0))
            self._line.setData(list(range(len(vals))), vals)

        # PnL histogram
        if self._hist_chart:
            self._hist_chart.clear()
            if trades:
                import numpy as np
                pnls = [t.get("pnl", 0) for t in trades]
                if pnls:
                    y, x = np.histogram(pnls, bins=min(20, max(5, len(pnls) // 3)))
                    colors = ["#00d4aa" if (x[i] + x[i + 1]) / 2 >= 0 else "#ff4444"
                              for i in range(len(y))]
                    for i in range(len(y)):
                        bar = pg.BarGraphItem(
                            x=[x[i]], height=[y[i]], width=(x[1] - x[0]) * 0.9,
                            brush=pg.mkBrush(colors[i]),
                        )
                        self._hist_chart.addItem(bar)

        # Trade log (last 50)
        recent = trades[-50:]
        self._trade_table.setRowCount(len(recent))
        for i, t in enumerate(reversed(recent)):
            self._trade_table.setItem(i, 0, QTableWidgetItem(str(t.get("symbol", ""))))
            dr = t.get("direction", "")
            self._trade_table.setItem(i, 1, colored_item(dr, "#00d4aa" if dr == "LONG" else "#ff4444"))
            self._trade_table.setItem(i, 2, QTableWidgetItem(f"${t.get('entry_price', 0):,.2f}"))
            self._trade_table.setItem(i, 3, QTableWidgetItem(f"${t.get('exit_price', 0):,.2f}"))
            pnl = t.get("pnl", 0)
            self._trade_table.setItem(i, 4, colored_item(f"${pnl:+,.2f}", "#00d4aa" if pnl >= 0 else "#ff4444"))
            mins = t.get("holding_minutes", 0)
            self._trade_table.setItem(i, 5, QTableWidgetItem(f"{mins:.0f} min" if mins else "—"))

        # ── Risk analytics ───────────────────────────────────
        self._update_risk_analytics(trades, d.get("initial_balance", 10_000))

    def _update_risk_analytics(self, trades: list, init_bal: float):
        if not trades:
            for w in (self._max_drawdown, self._sharpe, self._sortino,
                      self._profit_factor, self._avg_rr, self._expectancy,
                      self._win_streak, self._loss_streak, self._avg_hold_w,
                      self._avg_hold_l, self._long_wr, self._short_wr):
                w.set("—")
            return

        import statistics

        pnls = [t.get("pnl", 0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

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
        self._max_drawdown.set(f"{max_dd:.1%}", positive=max_dd < 0.05)

        # Sharpe ratio
        if len(pnls) >= 2:
            mean_r = statistics.mean(pnls)
            std_r = statistics.stdev(pnls)
            sharpe = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0.0
            self._sharpe.set(f"{sharpe:.2f}", positive=sharpe > 0)
        else:
            self._sharpe.set("—")

        # Sortino ratio (only penalizes downside deviation)
        if len(pnls) >= 2:
            mean_r = statistics.mean(pnls)
            downside = [min(0, p) ** 2 for p in pnls]
            down_dev = (sum(downside) / len(downside)) ** 0.5
            sortino = (mean_r / down_dev) * (252 ** 0.5) if down_dev > 0 else 0.0
            self._sortino.set(f"{sortino:.2f}", positive=sortino > 0)
        else:
            self._sortino.set("—")

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
        self._profit_factor.set(f"{pf:.2f}" if pf < 100 else "∞", positive=pf > 1)

        # Average Risk:Reward
        avg_w = statistics.mean(wins) if wins else 0
        avg_l = abs(statistics.mean(losses)) if losses else 0
        rr = avg_w / avg_l if avg_l > 0 else 0
        self._avg_rr.set(f"1:{rr:.1f}" if rr else "—", positive=rr > 1)

        # Expectancy per trade
        wr = len(wins) / len(pnls) if pnls else 0
        lr = len(losses) / len(pnls) if pnls else 0
        exp = (wr * avg_w) - (lr * avg_l) if pnls else 0
        self._expectancy.set(f"${exp:+,.2f}", positive=exp > 0)

        # Win/loss streaks
        max_w_streak = max_l_streak = 0
        w_streak = l_streak = 0
        for p in pnls:
            if p > 0:
                w_streak += 1
                l_streak = 0
                max_w_streak = max(max_w_streak, w_streak)
            elif p < 0:
                l_streak += 1
                w_streak = 0
                max_l_streak = max(max_l_streak, l_streak)
            else:
                w_streak = l_streak = 0
        self._win_streak.set(str(max_w_streak), positive=True)
        self._loss_streak.set(str(max_l_streak), positive=max_l_streak < 3)

        # Average hold time by outcome
        win_holds = [t.get("holding_minutes", 0) for t in trades if t.get("pnl", 0) > 0]
        loss_holds = [t.get("holding_minutes", 0) for t in trades if t.get("pnl", 0) < 0]
        self._avg_hold_w.set(f"{statistics.mean(win_holds):.0f} min" if win_holds else "—")
        self._avg_hold_l.set(f"{statistics.mean(loss_holds):.0f} min" if loss_holds else "—")

        # Win rate by direction
        longs = [t for t in trades if t.get("direction") == "LONG"]
        shorts = [t for t in trades if t.get("direction") == "SHORT"]
        long_wins = sum(1 for t in longs if t.get("pnl", 0) > 0)
        short_wins = sum(1 for t in shorts if t.get("pnl", 0) > 0)
        self._long_wr.set(f"{long_wins / len(longs):.0%}" if longs else "—")
        self._short_wr.set(f"{short_wins / len(shorts):.0%}" if shorts else "—")
