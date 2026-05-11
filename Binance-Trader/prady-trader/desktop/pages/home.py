"""PRADY TRADER — Desktop home surface."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QTextEdit, QTableWidgetItem, QVBoxLayout, QWidget

from desktop.widgets import MetricCard, StatusCard, colored_item, make_table, page_title, section_label


def _format_money(value: float | int | None) -> str:
    return f"${float(value or 0.0):,.2f}"


def _action_color(action: str) -> str:
    return "#00d4aa" if action == "LONG" else "#ff4444" if action == "SHORT" else "#8b949e"


def _badge_color(level: str) -> str:
    return {
        "healthy": "#00d4aa",
        "ok": "#00d4aa",
        "active": "#58a6ff",
        "warning": "#ffcc00",
        "degraded": "#ff9800",
        "critical": "#ff4444",
        "error": "#ff4444",
        "unknown": "#8b949e",
    }.get(str(level or "unknown").lower(), "#8b949e")


class HomePage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(page_title("Home"))

        self._briefing = QLabel("Waiting for runtime state…")
        self._briefing.setWordWrap(True)
        self._briefing.setStyleSheet(
            "background: #121b25; border: 1px solid #223142; border-radius: 12px; "
            "padding: 10px 12px; color: #d6e3ef; font-size: 12px;"
        )
        layout.addWidget(self._briefing)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self._runtime = MetricCard("Runtime")
        self._execution = MetricCard("Execution")
        self._balance = MetricCard("Balance")
        self._return = MetricCard("Total Return")
        self._cycle = MetricCard("Cycle")
        self._providers = MetricCard("Providers")
        for card in (
            self._runtime,
            self._execution,
            self._balance,
            self._return,
            self._cycle,
            self._providers,
        ):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        layout.addWidget(section_label("Desk Snapshot"))
        snapshot = QHBoxLayout()
        snapshot.setSpacing(10)
        self._market_card = StatusCard("Market Readiness")
        self._council_card = StatusCard("Council Pressure")
        self._ops_card = StatusCard("Ops Posture")
        for card in (self._market_card, self._council_card, self._ops_card):
            snapshot.addWidget(card)
        layout.addLayout(snapshot)

        layout.addWidget(section_label("Recent Decisions"))
        self._decision_table = make_table(["Time", "Symbol", "Action", "Score", "Conf"], max_h=260)
        layout.addWidget(self._decision_table)

        layout.addWidget(section_label("Desk Feeds"))
        feed_row = QHBoxLayout()
        feed_row.setSpacing(10)
        self._news_feed = QTextEdit()
        self._news_feed.setReadOnly(True)
        self._news_feed.setMinimumHeight(240)
        self._activity_feed = QTextEdit()
        self._activity_feed.setReadOnly(True)
        self._activity_feed.setMinimumHeight(240)
        feed_row.addWidget(self._news_feed, 1)
        feed_row.addWidget(self._activity_feed, 1)
        layout.addLayout(feed_row)
        layout.addStretch()

    def update_data(self, data: dict):
        runtime = str(data.get("trading_mode", "paper")).upper()
        execution = str(data.get("execution_environment", "paper")).upper()
        balance = float(data.get("balance", 0.0) or 0.0)
        total_return = float(data.get("total_return_pct", 0.0) or 0.0)
        provider_count = len(data.get("provider_statuses", {}) or {})

        self._runtime.set(runtime)
        self._execution.set(execution)
        self._balance.set(_format_money(balance))
        self._return.set(f"{total_return:+.2f}%", positive=total_return >= 0)
        self._cycle.set(f"#{int(data.get('cycle_count', 0) or 0)}")
        self._providers.set(str(provider_count))

        policy = data.get("active_mode_policy", {}) or {}
        health = data.get("health_data", {}) or {}
        overall = str(health.get("overall", "unknown")).upper()
        summary = [
            f"Runtime {runtime}",
            f"Execution {execution}",
            f"Health {overall}",
            f"Uptime {data.get('uptime_str', '0h 0m 0s')}",
        ]
        if policy.get("title"):
            summary.append(f"Policy {policy.get('title')}")
        if policy.get("guardrail"):
            summary.append(f"Guardrail {policy.get('guardrail')}")
        self._briefing.setText("  |  ".join(summary))

        market = data.get("market_overview", {}) or {}
        fng = data.get("fear_greed", {}) or {}
        sentiment_value = int(fng.get("value", 0) or 0)
        sentiment_label = str(fng.get("classification", "Unknown") or "Unknown")
        market_badge = "RISK" if sentiment_value <= 35 else "LIVE"
        market_color = "#ff9800" if sentiment_value <= 35 else "#00d4aa"
        btc_price = data.get("prices", {}).get("BTCUSDT") or market.get("btc_price")
        self._market_card.set(
            value=sentiment_label,
            badge=market_badge,
            badge_color=market_color,
            subtitle=f"BTC {_format_money(btc_price) if btc_price else 'n/a'}",
            details=(
                f"BTC dominance {float(market.get('btc_dominance', 0.0) or 0.0):.1f}%\n"
                f"Market cap {_format_money((float(market.get('total_market_cap', 0.0) or 0.0)) / 1_000_000_000_000)}T"
                if market.get("total_market_cap")
                else "Macro feed waiting for market overview"
            ),
        )

        decisions = list(data.get("decision_log", []) or [])
        latest_entry = decisions[-1] if decisions else None
        if latest_entry is None:
            last_decisions = data.get("last_decisions", {}) or {}
            if last_decisions:
                symbol, decision = next(iter(last_decisions.items()))
                latest_entry = {
                    "symbol": symbol,
                    "action": decision.get("action", "HOLD"),
                    "weighted_score": decision.get("weighted_score", 0),
                    "confidence": decision.get("confidence", 0),
                    "reasoning": decision.get("reasoning", "No decision reasoning recorded yet."),
                }

        if latest_entry is not None:
            action = str(latest_entry.get("action", "HOLD") or "HOLD")
            symbol = str(latest_entry.get("symbol", "Desk") or "Desk")
            confidence = float(latest_entry.get("confidence", 0.0) or 0.0)
            self._council_card.set(
                value=f"{symbol} {action}",
                badge=action,
                badge_color=_action_color(action),
                subtitle=f"Confidence {confidence:.0%}",
                details=str(latest_entry.get("reasoning", "No reasoning available."))[:180],
            )
        else:
            self._council_card.set(
                value="No live vote",
                badge="IDLE",
                badge_color="#8b949e",
                subtitle="Council has not published a decision yet",
                details="Start the engine from Control Room to populate the council feed.",
            )

        process_data = data.get("process_data", {}) or {}
        processes = process_data.get("processes", {}) if isinstance(process_data.get("processes"), dict) else {}
        alive = sum(1 for process in processes.values() if process.get("alive"))
        ops_level = str(health.get("overall", "unknown") or "unknown").lower()
        self._ops_card.set(
            value=ops_level.upper(),
            badge="OPS",
            badge_color=_badge_color(ops_level),
            subtitle=f"{alive} managed process(es) online",
            details=(
                f"Kill switch {'ACTIVE' if data.get('kill_switch') else 'clear'}\n"
                f"{provider_count} provider(s) tracked"
            ),
        )

        table_rows = decisions[-10:]
        if not table_rows:
            table_rows = [
                {
                    "timestamp": "—",
                    "symbol": symbol,
                    "action": latest_entry.get("action", "HOLD") if latest_entry else "HOLD",
                    "weighted_score": latest_entry.get("weighted_score", 0) if latest_entry else 0,
                    "confidence": latest_entry.get("confidence", 0) if latest_entry else 0,
                }
                for symbol, latest_entry in (data.get("last_decisions", {}) or {}).items()
            ]

        self._decision_table.setRowCount(len(table_rows))
        for row, entry in enumerate(reversed(table_rows)):
            timestamp = str(entry.get("timestamp") or entry.get("time") or entry.get("created_at") or "—")
            action = str(entry.get("action", "HOLD") or "HOLD")
            self._decision_table.setItem(row, 0, QTableWidgetItem(timestamp[-8:] if len(timestamp) >= 8 else timestamp))
            self._decision_table.setItem(row, 1, QTableWidgetItem(str(entry.get("symbol", "—"))))
            self._decision_table.setItem(row, 2, colored_item(action, _action_color(action)))
            self._decision_table.setItem(row, 3, QTableWidgetItem(f"{float(entry.get('weighted_score', 0.0) or 0.0):.1f}"))
            self._decision_table.setItem(row, 4, QTableWidgetItem(f"{float(entry.get('confidence', 0.0) or 0.0):.2f}"))

        news_lines = []
        for article in (data.get("news", []) or [])[:8]:
            title = str(article.get("title", "Untitled") or "Untitled")
            source = str(article.get("source") or article.get("_provider") or "feed")
            sentiment = str(article.get("sentiment", "neutral") or "neutral").lower()
            marker = "▲" if sentiment in {"positive", "bullish"} else "▼" if sentiment in {"negative", "bearish"} else "•"
            news_lines.append(
                f"<span style='color:#7cf2d0'>{marker}</span> "
                f"<span style='color:#f4f8fc'>{title}</span><br>"
                f"<span style='color:#8ea2b6'>{source}</span>"
            )
        self._news_feed.setHtml("<br><br>".join(news_lines) or "<span style='color:#8b949e'>No live news feed yet.</span>")

        activity_lines = []
        for entry in reversed((data.get("agent_activity", []) or [])[-12:]):
            ts = str(entry.get("timestamp", "") or "")
            level = str(entry.get("level", "INFO") or "INFO")
            module = str(entry.get("module", "runtime") or "runtime")
            message = str(entry.get("message", "") or "")
            level_color = "#ff4444" if level in {"ERROR", "CRITICAL"} else "#ff9800" if level == "WARNING" else "#58a6ff"
            activity_lines.append(
                f"<span style='color:#6e7681'>{ts[-8:] if len(ts) >= 8 else ts}</span> "
                f"<span style='color:{level_color}'>[{module}]</span> "
                f"<span style='color:#d6e3ef'>{message}</span>"
            )
        self._activity_feed.setHtml("<br>".join(activity_lines) or "<span style='color:#8b949e'>No agent activity yet.</span>")