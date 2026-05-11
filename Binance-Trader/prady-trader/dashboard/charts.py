"""
PRADY TRADER — Plotly chart builders for the dashboard.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COMMAND_COLORS = {
    "graphite": "#2c2e30",
    "muted": "#6f746f",
    "teal": "#4d7c7a",
    "teal_soft": "rgba(77, 124, 122, 0.16)",
    "amber": "#d98736",
    "amber_soft": "rgba(217, 135, 54, 0.18)",
    "danger": "#b95d43",
    "danger_soft": "rgba(185, 93, 67, 0.15)",
    "grid": "rgba(110, 96, 76, 0.18)",
    "panel": "rgba(250, 247, 239, 0.62)",
}


def _apply_command_theme(fig: go.Figure, height: int, title: Optional[str] = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        title=title,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COMMAND_COLORS["panel"],
        font=dict(
            family="Aptos, Bahnschrift, Segoe UI, sans-serif",
            color=COMMAND_COLORS["graphite"],
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=COMMAND_COLORS["grid"],
        zeroline=False,
        linecolor=COMMAND_COLORS["grid"],
        tickfont=dict(color=COMMAND_COLORS["muted"]),
        title_font=dict(color=COMMAND_COLORS["muted"]),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=COMMAND_COLORS["grid"],
        zeroline=False,
        linecolor=COMMAND_COLORS["grid"],
        tickfont=dict(color=COMMAND_COLORS["muted"]),
        title_font=dict(color=COMMAND_COLORS["muted"]),
    )
    return fig


def build_candlestick_chart(
    df: pd.DataFrame,
    symbol: str,
    indicators: Optional[Dict[str, pd.Series]] = None,
    trades: Optional[List[Dict]] = None,
) -> go.Figure:
    """Build a candlestick chart with optional indicator overlays and trade markers."""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=[f"{symbol} Price", "Volume"],
    )

    # Candlesticks
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="OHLC",
            increasing_line_color=COMMAND_COLORS["teal"],
            decreasing_line_color=COMMAND_COLORS["danger"],
        ),
        row=1, col=1,
    )

    # Volume bars
    colors = [COMMAND_COLORS["teal"] if c >= o else COMMAND_COLORS["danger"]
              for c, o in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(x=df.index, y=df["volume"], marker_color=colors, name="Volume", opacity=0.5),
        row=2, col=1,
    )

    # Indicator overlays
    if indicators:
        palette = [
            COMMAND_COLORS["amber"],
            COMMAND_COLORS["teal"],
            COMMAND_COLORS["graphite"],
            "#7a8f5d",
            COMMAND_COLORS["danger"],
            "#8b7355",
        ]
        for i, (name, series) in enumerate(indicators.items()):
            fig.add_trace(
                go.Scatter(
                    x=series.index, y=series, name=name,
                    line=dict(color=palette[i % len(palette)], width=1),
                ),
                row=1, col=1,
            )

    # Trade markers
    if trades:
        for trade in trades:
            color = COMMAND_COLORS["teal"] if trade.get("direction") == "LONG" else COMMAND_COLORS["danger"]
            symbol_marker = "triangle-up" if trade.get("direction") == "LONG" else "triangle-down"
            fig.add_trace(
                go.Scatter(
                    x=[trade.get("entry_time")],
                    y=[trade.get("entry_price")],
                    mode="markers",
                    marker=dict(color=color, size=12, symbol=symbol_marker),
                    name=f"{trade.get('direction', '')} entry",
                    showlegend=False,
                ),
                row=1, col=1,
            )

    fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=50, r=50, t=40, b=30))
    return _apply_command_theme(fig, 600, f"{symbol} Market Structure")


def build_equity_curve(trades: List[Dict], initial_balance: float = 10000.0) -> go.Figure:
    """Build equity curve from trade history."""
    if not trades:
        fig = go.Figure()
        fig.add_annotation(
            text="No trades yet",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=COMMAND_COLORS["muted"]),
        )
        return _apply_command_theme(fig, 320, "Equity Curve")

    equity = [initial_balance]
    timestamps = [trades[0].get("timestamp", 0)]

    for trade in trades:
        pnl = trade.get("pnl", 0)
        equity.append(equity[-1] + pnl)
        timestamps.append(trade.get("timestamp", 0))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(equity))),
        y=equity,
        mode="lines",
        fill="tozeroy",
        line=dict(color=COMMAND_COLORS["teal"], width=2.5),
        fillcolor=COMMAND_COLORS["teal_soft"],
        name="Equity",
    ))

    fig.update_layout(yaxis_title="USDT", margin=dict(l=50, r=50, t=40, b=30))
    return _apply_command_theme(fig, 320, "Equity Curve")


def build_agent_radar(signals: Dict[str, Dict]) -> go.Figure:
    """Build radar chart showing agent signal strengths."""
    if not signals:
        fig = go.Figure()
        fig.add_annotation(
            text="No signals",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=COMMAND_COLORS["muted"]),
        )
        _apply_command_theme(fig, 340, "Council Radar")
        return fig

    categories = list(signals.keys())
    confidences = [s.get("confidence", 0) for s in signals.values()]
    scores = [abs(s.get("score", 0)) / 100 for s in signals.values()]

    # Close the radar
    categories_closed = categories + [categories[0]]
    confidences_closed = confidences + [confidences[0]]
    scores_closed = scores + [scores[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=confidences_closed, theta=categories_closed, fill="toself",
        name="Confidence",
        line=dict(color=COMMAND_COLORS["teal"], width=2),
        fillcolor=COMMAND_COLORS["teal_soft"],
    ))
    fig.add_trace(go.Scatterpolar(
        r=scores_closed, theta=categories_closed, fill="toself",
        name="Score Magnitude",
        line=dict(color=COMMAND_COLORS["amber"], width=2),
        fillcolor=COMMAND_COLORS["amber_soft"],
    ))

    fig.update_layout(
        template="plotly_white",
        height=350,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Aptos, Bahnschrift, Segoe UI, sans-serif", color=COMMAND_COLORS["graphite"]),
        polar=dict(
            bgcolor=COMMAND_COLORS["panel"],
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                gridcolor=COMMAND_COLORS["grid"],
                linecolor=COMMAND_COLORS["grid"],
                tickfont=dict(color=COMMAND_COLORS["muted"]),
            ),
            angularaxis=dict(linecolor=COMMAND_COLORS["grid"], tickfont=dict(color=COMMAND_COLORS["muted"])),
        ),
        margin=dict(l=50, r=50, t=30, b=30),
    )
    return fig


def build_pnl_histogram(trades: List[Dict]) -> go.Figure:
    """Build PnL distribution histogram."""
    if not trades:
        fig = go.Figure()
        return _apply_command_theme(fig, 260, "PnL Distribution")

    pnls = [t.get("pnl", 0) for t in trades if t.get("pnl") is not None]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=pnls, nbinsx=30,
        marker_color=COMMAND_COLORS["amber"],
        name="PnL Distribution",
        opacity=0.85,
    ))

    fig.update_layout(xaxis_title="PnL (USDT)", margin=dict(l=50, r=50, t=40, b=30))
    return _apply_command_theme(fig, 260, "PnL Distribution")


def build_composite_gauge(score: float, label: str = "Composite Score") -> go.Figure:
    """Build a gauge chart for composite score (0-100)."""
    color = COMMAND_COLORS["teal"] if score >= 60 else COMMAND_COLORS["amber"] if score >= 40 else COMMAND_COLORS["danger"]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": label},
        gauge=dict(
            axis=dict(range=[0, 100]),
            bar=dict(color=color),
            steps=[
                dict(range=[0, 35], color=COMMAND_COLORS["danger_soft"]),
                dict(range=[35, 65], color=COMMAND_COLORS["amber_soft"]),
                dict(range=[65, 100], color=COMMAND_COLORS["teal_soft"]),
            ],
        ),
    ))

    fig.update_layout(
        template="plotly_white",
        height=250,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Aptos, Bahnschrift, Segoe UI, sans-serif", color=COMMAND_COLORS["graphite"]),
        margin=dict(l=30, r=30, t=30, b=10),
    )
    return fig


def build_weight_bar_chart(weights: Dict[str, float], accuracies: Dict[str, float]) -> go.Figure:
    """Build grouped bar chart for agent weights and accuracies."""
    agents = list(weights.keys())
    w_vals = [weights[a] for a in agents]
    a_vals = [accuracies.get(a, 0.5) for a in agents]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=agents, y=w_vals, name="Weight", marker_color=COMMAND_COLORS["teal"]))
    fig.add_trace(go.Bar(x=agents, y=a_vals, name="Accuracy", marker_color=COMMAND_COLORS["amber"]))

    fig.update_layout(barmode="group", yaxis_range=[0, 1], margin=dict(l=50, r=50, t=40, b=30))
    return _apply_command_theme(fig, 320, "Agent Weights & Accuracy")
