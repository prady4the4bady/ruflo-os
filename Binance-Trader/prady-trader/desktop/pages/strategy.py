"""PRADY TRADER — Strategy Builder page."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QHBoxLayout, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from desktop.widgets import MetricCard, colored_item, make_table, page_title, section_label


class StrategyBuilderPage(QScrollArea):
    EXPECTED_MODELS = ("lstm", "xgboost", "tft")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(page_title("Strategy Builder"))

        self._policy_summary = QLabel("Waiting for policy metadata…")
        self._policy_summary.setWordWrap(True)
        self._policy_summary.setStyleSheet(
            "background: #121b25; border: 1px solid #223142; border-radius: 12px; "
            "padding: 10px 12px; color: #d6e3ef; font-size: 12px;"
        )
        layout.addWidget(self._policy_summary)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self._model_count = MetricCard("Model Files")
        self._pairs_covered = MetricCard("Pairs Covered")
        self._missing_pairs = MetricCard("Coverage Gaps")
        self._prediction_count = MetricCard("Predictions")
        self._decision_count = MetricCard("Decisions")
        self._agent_count = MetricCard("Agents Weighted")
        for card in (
            self._model_count,
            self._pairs_covered,
            self._missing_pairs,
            self._prediction_count,
            self._decision_count,
            self._agent_count,
        ):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        layout.addWidget(section_label("Agent Weights"))
        self._weights_table = make_table(["Agent", "Weight", "Status"], max_h=220)
        layout.addWidget(self._weights_table)

        layout.addWidget(section_label("Prediction Surface"))
        self._prediction_table = make_table(["Symbol", "Direction", "Probability", "Agreement", "Coverage"], max_h=240)
        layout.addWidget(self._prediction_table)

        layout.addWidget(section_label("Signal Candidates"))
        self._candidate_table = make_table(["Symbol", "Action", "Score", "Conf", "Reasoning"], max_h=260)
        layout.addWidget(self._candidate_table)

        layout.addWidget(section_label("Model Registry"))
        self._registry = QTextEdit()
        self._registry.setReadOnly(True)
        self._registry.setMinimumHeight(220)
        layout.addWidget(self._registry)

        layout.addWidget(section_label("Training Gaps"))
        self._gaps = QTextEdit()
        self._gaps.setReadOnly(True)
        self._gaps.setMinimumHeight(140)
        layout.addWidget(self._gaps)
        layout.addStretch()

    def update_data(self, data: dict):
        coverage = self._model_coverage_snapshot()
        total_files = sum(sum(1 for path in models.values() if path) for models in coverage.values())
        fully_covered = sum(1 for models in coverage.values() if models and all(models.values()))
        missing = {symbol: [name for name, path in models.items() if not path] for symbol, models in coverage.items()}
        missing = {symbol: gaps for symbol, gaps in missing.items() if gaps}

        weights = data.get("agent_weights", {}) or {}
        predictions = data.get("ensemble_predictions", {}) or {}
        decisions = list(data.get("decision_log", []) or [])
        policy = data.get("active_mode_policy", {}) or {}

        summary_parts = [
            str(policy.get("title", "Strategy surface waiting for runtime policy")),
            f"Goal {policy.get('primary_goal', 'n/a')}",
            f"Guardrail {policy.get('guardrail', 'n/a')}",
        ]
        self._policy_summary.setText("  |  ".join(summary_parts))

        self._model_count.set(str(total_files))
        self._pairs_covered.set(f"{fully_covered}/{len(coverage)}", positive=fully_covered == len(coverage) if coverage else None)
        self._missing_pairs.set(str(len(missing)), positive=len(missing) == 0)
        self._prediction_count.set(str(len(predictions)))
        self._decision_count.set(str(len(decisions) or len(data.get("last_decisions", {}) or {})))
        self._agent_count.set(str(len(weights)))

        self._weights_table.setRowCount(len(weights))
        for row, (agent, weight) in enumerate(weights.items()):
            self._weights_table.setCellWidget(row, 0, QLabel(agent.title().replace("_", " ")))
            self._weights_table.setCellWidget(row, 1, QLabel(f"{float(weight or 0.0):.2f}"))
            badge = "HEAVY" if float(weight or 0.0) >= 0.15 else "BALANCED" if float(weight or 0.0) >= 0.1 else "LIGHT"
            color = "#00d4aa" if badge == "HEAVY" else "#58a6ff" if badge == "BALANCED" else "#8b949e"
            self._weights_table.setItem(row, 2, colored_item(badge, color))

        self._prediction_table.setRowCount(len(predictions))
        for row, (symbol, prediction) in enumerate(predictions.items()):
            direction = str(prediction.get("direction", "NEUTRAL") or "NEUTRAL")
            probability = float(prediction.get("probability", 0.0) or 0.0)
            agreement = float(prediction.get("model_agreement", 0.0) or 0.0)
            coverage_label = self._coverage_label(coverage.get(symbol, {}))
            color = "#00d4aa" if direction == "UP" else "#ff4444" if direction == "DOWN" else "#8b949e"
            self._prediction_table.setCellWidget(row, 0, QLabel(symbol))
            self._prediction_table.setItem(row, 1, colored_item(direction, color))
            self._prediction_table.setCellWidget(row, 2, QLabel(f"{probability:.1%}"))
            self._prediction_table.setCellWidget(row, 3, QLabel(f"{agreement:.1%}"))
            self._prediction_table.setItem(row, 4, colored_item(coverage_label, "#00d4aa" if coverage_label == "FULL" else "#ff9800" if coverage_label == "PARTIAL" else "#ff4444"))

        candidate_rows = decisions[-10:]
        if not candidate_rows:
            candidate_rows = [
                {
                    "symbol": symbol,
                    "action": payload.get("action", "HOLD"),
                    "weighted_score": payload.get("weighted_score", 0),
                    "confidence": payload.get("confidence", 0),
                    "reasoning": payload.get("reasoning", ""),
                }
                for symbol, payload in (data.get("last_decisions", {}) or {}).items()
            ]

        self._candidate_table.setRowCount(len(candidate_rows))
        for row, candidate in enumerate(reversed(candidate_rows)):
            symbol = str(candidate.get("symbol", "—") or "—")
            action = str(candidate.get("action", "HOLD") or "HOLD")
            score = float(candidate.get("weighted_score", 0.0) or 0.0)
            confidence = float(candidate.get("confidence", 0.0) or 0.0)
            reasoning = str(candidate.get("reasoning", "") or "")[:120]
            action_color = "#00d4aa" if action == "LONG" else "#ff4444" if action == "SHORT" else "#8b949e"
            self._candidate_table.setCellWidget(row, 0, QLabel(symbol))
            self._candidate_table.setItem(row, 1, colored_item(action, action_color))
            self._candidate_table.setCellWidget(row, 2, QLabel(f"{score:.1f}"))
            self._candidate_table.setCellWidget(row, 3, QLabel(f"{confidence:.2f}"))
            self._candidate_table.setCellWidget(row, 4, QLabel(reasoning or "No reasoning yet"))

        registry_lines = []
        for symbol, models in coverage.items():
            status_parts = []
            for model_name in self.EXPECTED_MODELS:
                path = models.get(model_name)
                if path:
                    status_parts.append(f"<span style='color:#00d4aa'>{model_name}</span> {path}")
                else:
                    status_parts.append(f"<span style='color:#ff4444'>{model_name}</span> missing")
            registry_lines.append(f"<b>{symbol}</b><br>{'<br>'.join(status_parts)}")
        self._registry.setHtml("<br><br>".join(registry_lines) or "<span style='color:#8b949e'>No model registry entries found.</span>")

        if missing:
            gap_lines = [
                f"<span style='color:#ff9800'><b>{symbol}</b></span>: {', '.join(gaps)}"
                for symbol, gaps in missing.items()
            ]
            self._gaps.setHtml(
                "<span style='color:#d6e3ef'>These pairs are not fully trained yet.</span><br><br>"
                + "<br>".join(gap_lines)
            )
        else:
            self._gaps.setHtml("<span style='color:#00d4aa'>All configured pairs have latest model coverage.</span>")

    def _model_coverage_snapshot(self) -> dict[str, dict[str, str]]:
        from config.settings import get_settings
        from ml.model_store import get_latest_model_path

        snapshot: dict[str, dict[str, str]] = {}
        settings = get_settings()
        for symbol in settings.trading_pairs:
            snapshot[symbol] = {}
            for model_name in self.EXPECTED_MODELS:
                path = get_latest_model_path(model_name, symbol)
                snapshot[symbol][model_name] = path.name if path else ""
        return snapshot

    @staticmethod
    def _coverage_label(model_map: dict[str, str]) -> str:
        model_map = model_map or {}
        available = [path for path in model_map.values() if path]
        if model_map and len(available) == len(model_map):
            return "FULL"
        if available:
            return "PARTIAL"
        return "MISSING"