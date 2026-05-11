"""PRADY TRADER — Agent Intelligence page (enhanced)."""

from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.widgets import MetricCard, Separator, colored_item, make_table, page_title, section_label

try:
    import pyqtgraph as pg
    HAS_PG = True
except ImportError:
    HAS_PG = False


class AgentsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        c = QWidget()
        self.setWidget(c)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 8, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(page_title("Agent Matrix"))

        # ── Agent accuracy metrics (top row) ─────────────────
        lay.addWidget(section_label("Agent Accuracy & Performance"))
        arow = QHBoxLayout()
        arow.setSpacing(10)
        self._accuracy_cards: dict[str, MetricCard] = {}
        for name in ("Oracle", "Prophet", "Sentinel", "Arbiter", "OracleExt", "Debater"):
            card = MetricCard(name)
            self._accuracy_cards[name] = card
            arow.addWidget(card)
        lay.addLayout(arow)

        # ── Agent weights chart ──────────────────────────────
        lay.addWidget(section_label("Agent Weights"))
        if HAS_PG:
            self._weight_chart = pg.PlotWidget()
            self._weight_chart.setBackground("#0e1117")
            self._weight_chart.setMinimumHeight(200)
            self._weight_chart.setMaximumHeight(250)
            self._bar_item = None
            lay.addWidget(self._weight_chart)
        else:
            self._weight_chart = None

        # Weights table
        self._weight_table = make_table(["Agent", "Weight", "Role"], max_h=260)
        lay.addWidget(self._weight_table)

        lay.addWidget(Separator())

        # ── Per-symbol signals ───────────────────────────────
        lay.addWidget(section_label("Per-Symbol Agent Signals"))
        self._signals_area = QVBoxLayout()
        self._signals_container = QWidget()
        self._signals_container.setLayout(self._signals_area)
        lay.addWidget(self._signals_container)

        lay.addWidget(Separator())

        # ── Agent Reasoning from Decision Logs ───────────────
        lay.addWidget(section_label("📋  Agent Reasoning (from Council Decisions)"))
        self._reasoning_log = QTextEdit()
        self._reasoning_log.setReadOnly(True)
        self._reasoning_log.setMaximumHeight(300)
        self._reasoning_log.setStyleSheet(
            "background: #0d1117; border: 1px solid #30363d; border-radius: 6px; "
            "color: #c9d1d9; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px; padding: 8px;"
        )
        lay.addWidget(self._reasoning_log)

        lay.addWidget(Separator())

        # ── Decision history table ───────────────────────────
        lay.addWidget(section_label("📊  Decision History"))
        self._history_table = make_table(
            ["Time", "Symbol", "Action", "Score", "Conf", "Veto", "Dominant Agent"],
            max_h=250,
        )
        lay.addWidget(self._history_table)

        lay.addWidget(Separator())

        # ── ML predictions ───────────────────────────────────
        lay.addWidget(section_label("ML Ensemble Predictions"))
        self._ml_area = QVBoxLayout()
        self._ml_container = QWidget()
        self._ml_container.setLayout(self._ml_area)
        lay.addWidget(self._ml_container)

        lay.addStretch()

    def update_data(self, d: dict):
        # ── weights ──────────────────────────────────────────
        try:
            from config.constants import AGENT_WEIGHTS
            weights = d.get("agent_weights") or AGENT_WEIGHTS
        except ImportError:
            weights = d.get("agent_weights", {})

        roles = {
            "oracle": "Multi-TF Technical",
            "prophet": "ML Ensemble",
            "arbiter": "Regime & Cross-pair",
            "sentinel": "Risk & Sentiment",
            "oracle_extended": "External APIs",
            "debater": "LLM Contrarian",
            "warden": "Veto Gate",
        }

        names = list(weights.keys())
        vals = [weights[n] for n in names]

        if self._weight_chart and names:
            self._weight_chart.clear()
            x = list(range(len(names)))
            bg = pg.BarGraphItem(x=x, height=vals, width=0.6,
                                 brush=pg.mkBrush("#00d4aa"))
            self._weight_chart.addItem(bg)
            ax = self._weight_chart.getAxis("bottom")
            ax.setTicks([list(zip(x, [n.title() for n in names]))])

        self._weight_table.setRowCount(len(names))
        for i, n in enumerate(names):
            self._weight_table.setItem(i, 0, QTableWidgetItem(n.title()))
            self._weight_table.setItem(i, 1, QTableWidgetItem(f"{weights[n]:.2f}"))
            self._weight_table.setItem(i, 2, QTableWidgetItem(roles.get(n, "")))

        # ── per-symbol signals ───────────────────────────────
        while self._signals_area.count():
            w = self._signals_area.takeAt(0).widget()
            if w:
                w.deleteLater()

        for sym, sigs in d.get("agent_signals", {}).items():
            header = QLabel(f"<b>🎯 {sym}</b>")
            header.setStyleSheet("font-size: 14px; padding: 6px 0 2px 0;")
            self._signals_area.addWidget(header)

            if isinstance(sigs, dict):
                row_lay = QHBoxLayout()
                for name, sig in sigs.items():
                    direction = sig.get("direction", "N/A") if isinstance(sig, dict) else "N/A"
                    conf = sig.get("confidence", 0) if isinstance(sig, dict) else 0
                    reasoning = sig.get("reasoning", "") if isinstance(sig, dict) else ""
                    c = "#00d4aa" if direction == "LONG" else "#ff4444" if direction == "SHORT" else "#8b949e"
                    reason_snip = f"<br><span style='color:#6e7681; font-size:10px;'>{reasoning[:80]}…</span>" if reasoning else ""
                    card = QLabel(
                        f"<b>{name.title()}</b><br>"
                        f"<span style='color:{c}; font-size:15px;'>{direction}</span><br>"
                        f"<span style='color:#8b949e; font-size:11px;'>Conf: {conf:.2f}</span>"
                        f"{reason_snip}"
                    )
                    card.setWordWrap(True)
                    card.setStyleSheet(
                        "background: #161b22; border: 1px solid #30363d; "
                        "border-radius: 6px; padding: 8px 12px; margin: 2px; min-width: 120px;"
                    )
                    row_lay.addWidget(card)
                row_w = QWidget()
                row_w.setLayout(row_lay)
                self._signals_area.addWidget(row_w)

        # ── Agent accuracy from decision logs ────────────────
        decision_log = d.get("decision_log", [])
        self._update_accuracy(decision_log)
        self._update_reasoning_log(decision_log)
        self._update_decision_history(decision_log)

        # ── ML predictions ───────────────────────────────────
        while self._ml_area.count():
            w = self._ml_area.takeAt(0).widget()
            if w:
                w.deleteLater()

        preds = d.get("ensemble_predictions", {})
        if preds:
            for sym, pred in preds.items():
                direction = pred.get("direction", "N/A")
                conf = pred.get("confidence", 0)
                c = "#00d4aa" if direction == "LONG" else "#ff4444" if direction == "SHORT" else "#8b949e"
                lbl = QLabel(
                    f"  <b>{sym}</b>: <span style='color:{c}'>{direction}</span>"
                    f"  (conf={conf:.2f})"
                )
                lbl.setStyleSheet("font-size: 13px; padding: 3px;")
                self._ml_area.addWidget(lbl)
        else:
            lbl = QLabel("  No ML predictions available — models not trained yet")
            lbl.setStyleSheet("color: #8b949e; padding: 8px;")
            self._ml_area.addWidget(lbl)

    def _update_accuracy(self, decision_log: list):
        """Compute per-agent accuracy from decision log — how aligned each agent is with final action."""
        agent_map = {
            "oracle": "Oracle",
            "prophet": "Prophet",
            "sentinel": "Sentinel",
            "arbiter": "Arbiter",
            "oracle_extended": "OracleExt",
            "debater": "Debater",
        }
        agree_cnt: Counter = Counter()
        total_cnt: Counter = Counter()
        conf_sum: dict[str, float] = {k: 0.0 for k in agent_map}

        for entry in decision_log:
            final_action = entry.get("action", "HOLD")
            signals = entry.get("agent_signals", {})
            for key, display in agent_map.items():
                sig = signals.get(key, {})
                if not sig:
                    continue
                total_cnt[display] += 1
                direction = sig.get("direction", "NEUTRAL")
                conf_sum[key] = conf_sum.get(key, 0) + sig.get("confidence", 0)
                # LONG aligns with LONG, SHORT with SHORT, NEUTRAL with HOLD
                if direction == final_action or (direction == "NEUTRAL" and final_action == "HOLD"):
                    agree_cnt[display] += 1

        for key, display in agent_map.items():
            total = total_cnt.get(display, 0)
            if total > 0:
                accuracy = agree_cnt.get(display, 0) / total
                avg_conf = conf_sum.get(key, 0) / total
                self._accuracy_cards[display].set(
                    f"{accuracy:.0%}",
                    f"align · {total} decisions · avg conf {avg_conf:.2f}",
                    accuracy >= 0.5,
                )
            else:
                self._accuracy_cards[display].set("—", "No decisions yet", None)

    def _update_reasoning_log(self, decision_log: list):
        """Show per-agent reasoning from most recent decisions."""
        if not decision_log:
            self._reasoning_log.setHtml(
                "<span style='color:#8b949e'>No decision data — start the orchestrator from Settings</span>"
            )
            return

        lines = []
        for entry in decision_log[-5:]:
            ts = entry.get("timestamp", "")[:19]
            sym = entry.get("symbol", "?")
            act = entry.get("action", "?")
            ac = "#00d4aa" if act == "LONG" else "#ff4444" if act == "SHORT" else "#8b949e"
            lines.append(
                f"<b><span style='color:#58a6ff'>━━ {sym}</span></b> "
                f"<span style='color:{ac}'>{act}</span> "
                f"<span style='color:#484f58'>{ts}</span>"
            )
            signals = entry.get("agent_signals", {})
            for agent, sig in signals.items():
                reasoning = sig.get("reasoning", "")
                direction = sig.get("direction", "?")
                conf = sig.get("confidence", 0)
                dc = "#00d4aa" if direction in ("LONG", "BUY") else "#ff4444" if direction in ("SHORT", "SELL") else "#6e7681"
                lines.append(
                    f"  <span style='color:#58a6ff'>{agent}</span>"
                    f" → <span style='color:{dc}'>{direction}</span>"
                    f" ({conf:.2f}): <span style='color:#8b949e'>{reasoning[:150]}</span>"
                )
            lines.append("")

        self._reasoning_log.setHtml("<br>".join(lines))

    def _update_decision_history(self, decision_log: list):
        """Fill decision history table."""
        entries = decision_log[-20:]
        self._history_table.setRowCount(len(entries))
        for row, entry in enumerate(reversed(entries)):
            ts = entry.get("timestamp", "")
            ts_short = ts[11:19] if len(ts) >= 19 else ts
            sym = entry.get("symbol", "?")
            act = entry.get("action", "?")
            score = entry.get("weighted_score", 0)
            conf = entry.get("confidence", 0)
            veto = entry.get("veto", False)

            # Find dominant agent (highest confidence that matches final action)
            signals = entry.get("agent_signals", {})
            dominant = "—"
            max_conf = 0
            for agent, sig in signals.items():
                ac = sig.get("confidence", 0)
                if ac > max_conf:
                    max_conf = ac
                    dominant = agent.title()

            ac_color = "#00d4aa" if act == "LONG" else "#ff4444" if act == "SHORT" else "#8b949e"
            self._history_table.setItem(row, 0, QTableWidgetItem(ts_short))
            self._history_table.setItem(row, 1, QTableWidgetItem(sym))
            self._history_table.setItem(row, 2, colored_item(act, ac_color))
            self._history_table.setItem(row, 3, QTableWidgetItem(f"{score:.1f}"))
            self._history_table.setItem(row, 4, QTableWidgetItem(f"{conf:.2f}"))
            self._history_table.setItem(row, 5, colored_item("YES" if veto else "NO", "#ff4444" if veto else "#00d4aa"))
            self._history_table.setItem(row, 6, QTableWidgetItem(dominant))
