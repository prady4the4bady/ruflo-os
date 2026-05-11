"""PRADY TRADER — Reusable desktop widgets."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)


class MetricCard(QFrame):
    """Compact metric display: label, big value, optional delta."""

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setMinimumWidth(100)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self._lbl = QLabel(label)
        self._lbl.setObjectName("metricLabel")
        self._val = QLabel("—")
        self._val.setObjectName("metricValue")
        self._dlt = QLabel("")
        self._dlt.setObjectName("metricDelta")
        lay.addWidget(self._lbl)
        lay.addWidget(self._val)
        lay.addWidget(self._dlt)

    def set(self, value: str, delta: str = "", positive: bool | None = None):
        self._val.setText(value)
        if delta:
            self._dlt.setText(delta)
            if positive is not None:
                c = "#00d4aa" if positive else "#ff4444"
                self._dlt.setStyleSheet(f"color: {c}; font-size: 12px;")
        else:
            self._dlt.setText("")


class StatusCard(QFrame):
    """Compact status card for live domains and provider telemetry."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setMinimumWidth(180)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._title = QLabel(title)
        self._title.setObjectName("metricLabel")
        self._badge = QLabel("IDLE")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet(
            "background: #30363d; color: #c9d1d9; border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: bold;"
        )
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._badge)

        self._value = QLabel("—")
        self._value.setObjectName("metricValue")
        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._subtitle.setWordWrap(True)
        self._details = QLabel("")
        self._details.setStyleSheet("color: #c9d1d9; font-size: 11px;")
        self._details.setWordWrap(True)

        lay.addLayout(header)
        lay.addWidget(self._value)
        lay.addWidget(self._subtitle)
        lay.addWidget(self._details)

    def set_title(self, title: str):
        self._title.setText(title)

    def set(
        self,
        *,
        value: str,
        badge: str,
        badge_color: str,
        subtitle: str = "",
        details: str = "",
    ):
        self._value.setText(value)
        self._badge.setText(badge)
        self._badge.setStyleSheet(
            f"background: {badge_color}; color: #0d1117; border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: bold;"
        )
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
        self._details.setText(details)
        self._details.setVisible(bool(details))


class Separator(QFrame):
    """Horizontal line divider."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("separator")
        self.setFixedHeight(1)


def make_table(columns: list[str], max_h: int = 220) -> QTableWidget:
    """Create a styled QTableWidget."""
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setMaximumHeight(max_h)
    t.setAlternatingRowColors(False)
    return t


def colored_item(text: str, color: str) -> QTableWidgetItem:
    """QTableWidgetItem with custom text color."""
    item = QTableWidgetItem(text)
    item.setForeground(QColor(color))
    return item


def section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("sectionHeader")
    return lbl


def page_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("pageTitle")
    return lbl


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
