from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from execution.capital_guard import (
    compute_profit_factor,
    evaluate_runtime_guard,
    load_rehearsal_summary,
    trailing_loss_streak,
)


def _settings(**overrides):
    values = {
        "max_daily_loss": Decimal("0.05"),
        "max_consecutive_losses": 3,
        "is_live": False,
        "live_min_rehearsal_trades": 20,
        "live_min_rehearsal_win_rate": Decimal("0.55"),
        "live_require_positive_rehearsal_pnl": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_trailing_loss_streak_counts_only_suffix_losses():
    trades = [
        {"pnl": 12.0},
        {"pnl": -2.0},
        {"pnl": -1.0},
        {"pnl": -4.0},
    ]

    assert trailing_loss_streak(trades) == 3


def test_compute_profit_factor_handles_wins_and_losses():
    trades = [{"pnl": 10.0}, {"pnl": -5.0}, {"pnl": 15.0}, {"pnl": -5.0}]

    assert compute_profit_factor(trades) == 2.5


def test_evaluate_runtime_guard_blocks_loss_limit_and_streak():
    evaluation = evaluate_runtime_guard(
        _settings(),
        current_equity=930.0,
        baseline_equity=1000.0,
        recent_closed_trades=[
            {"pnl": -10.0},
            {"pnl": -8.0},
            {"pnl": -7.0},
        ],
    )

    assert evaluation.allowed is False
    assert evaluation.status == "paused"
    assert any("Equity drawdown" in reason for reason in evaluation.reasons)
    assert any("Consecutive loss streak" in reason for reason in evaluation.reasons)


def test_evaluate_runtime_guard_blocks_live_when_rehearsal_is_weak():
    evaluation = evaluate_runtime_guard(
        _settings(is_live=True),
        current_equity=1000.0,
        baseline_equity=1000.0,
        recent_closed_trades=[],
        rehearsal_summary={
            "available": True,
            "source": "testnet state file",
            "mode": "testnet",
            "trades": 12,
            "win_rate": 0.42,
            "pnl": -25.0,
        },
    )

    assert evaluation.allowed is False
    joined = " ".join(evaluation.reasons)
    assert "rehearsal trades" in joined
    assert "rehearsal win rate" in joined
    assert "rehearsal PnL" in joined


def test_load_rehearsal_summary_prefers_best_candidate():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "state_paper.json").write_text(
            '{"total_trades": 8, "win_rate": 0.5, "total_pnl": 12.0, "closed_trades": [{"pnl": 5.0}, {"pnl": -1.0}]}',
            encoding="utf-8",
        )
        (data_dir / "state_testnet.json").write_text(
            '{"total_trades": 18, "win_rate": 0.61, "total_pnl": 84.0, "closed_trades": [{"pnl": 10.0}, {"pnl": 9.0}, {"pnl": -4.0}]}',
            encoding="utf-8",
        )

        summary = load_rehearsal_summary(root_dir=root, journal=None)

    assert summary["available"] is True
    assert summary["mode"] == "testnet"
    assert summary["trades"] == 18
    assert summary["source"] == "testnet state file"