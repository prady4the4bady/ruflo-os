"""
PRADY TRADER — Capital preservation guardrails.
Evaluates recent trading outcomes and rehearsal readiness to decide
whether the runtime should stand down instead of opening new risk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config.settings import ROOT_DIR


@dataclass
class GuardEvaluation:
    allowed: bool
    status: str
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _trade_count_from_snapshot(snapshot: Dict[str, Any]) -> int:
    total = snapshot.get("total_trades")
    if total is not None:
        return int(total or 0)
    closed_trades = snapshot.get("closed_trades") or []
    return len(closed_trades)


def _load_state_snapshot(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def trailing_loss_streak(trades: Iterable[Dict[str, Any]]) -> int:
    streak = 0
    for trade in reversed(list(trades)):
        pnl = _coerce_float(trade.get("pnl"))
        if pnl < 0:
            streak += 1
            continue
        break
    return streak


def compute_profit_factor(trades: Iterable[Dict[str, Any]]) -> Optional[float]:
    gross_profit = 0.0
    gross_loss = 0.0
    seen = False

    for trade in trades:
        seen = True
        pnl = _coerce_float(trade.get("pnl"))
        if pnl > 0:
            gross_profit += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)

    if not seen:
        return None
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def load_rehearsal_summary(root_dir: Path = ROOT_DIR, journal=None) -> Dict[str, Any]:
    """Load the strongest rehearsal history from paper/testnet state or journal."""
    candidates: List[Dict[str, Any]] = []
    journal_error = ""

    for mode, rel_path in (
        ("paper", Path("data/state_paper.json")),
        ("testnet", Path("data/state_testnet.json")),
    ):
        snapshot = _load_state_snapshot(root_dir / rel_path)
        if not snapshot or snapshot.get("_test"):
            continue

        closed_trades = list(snapshot.get("closed_trades") or [])
        candidates.append(
            {
                "mode": mode,
                "source": f"{mode} state file",
                "trades": _trade_count_from_snapshot(snapshot),
                "win_rate": _coerce_float(snapshot.get("win_rate")),
                "pnl": _coerce_float(snapshot.get("total_pnl", snapshot.get("daily_pnl"))),
                "profit_factor": compute_profit_factor(closed_trades),
                "consecutive_losses": trailing_loss_streak(closed_trades),
            }
        )

    if journal is not None:
        try:
            recent = list(journal.get_recent_trades(n=500, paper=True))
            stats = journal.get_stats(paper=True)
            candidates.append(
                {
                    "mode": "paper",
                    "source": "paper trade journal",
                    "trades": int(stats.get("total_trades", 0) or 0),
                    "win_rate": _coerce_float(stats.get("win_rate")),
                    "pnl": _coerce_float(stats.get("total_pnl")),
                    "profit_factor": compute_profit_factor(recent),
                    "consecutive_losses": trailing_loss_streak(recent),
                }
            )
        except Exception as exc:
            journal_error = str(exc)

    if not candidates:
        return {
            "available": False,
            "mode": "",
            "source": "",
            "trades": 0,
            "win_rate": 0.0,
            "pnl": 0.0,
            "profit_factor": None,
            "consecutive_losses": 0,
            "journal_error": journal_error,
        }

    best = max(
        candidates,
        key=lambda candidate: (
            int(candidate.get("trades", 0) or 0),
            _coerce_float(candidate.get("pnl")),
            _coerce_float(candidate.get("win_rate")),
        ),
    )
    best["available"] = int(best.get("trades", 0) or 0) > 0
    if journal_error:
        best["journal_error"] = journal_error
    return best


def evaluate_runtime_guard(
    settings,
    *,
    current_equity: float,
    baseline_equity: float,
    recent_closed_trades: Iterable[Dict[str, Any]],
    rehearsal_summary: Optional[Dict[str, Any]] = None,
) -> GuardEvaluation:
    """Return whether the runtime should keep opening new risk."""
    reasons: List[str] = []
    trades = list(recent_closed_trades)
    max_loss_pct = _coerce_float(getattr(settings, "max_daily_loss", 0.0))
    max_consecutive_losses = int(getattr(settings, "max_consecutive_losses", 3) or 3)

    baseline_loss_pct = 0.0
    if baseline_equity > 0 and current_equity > 0 and current_equity < baseline_equity:
        baseline_loss_pct = (baseline_equity - current_equity) / baseline_equity
        if baseline_loss_pct >= max_loss_pct:
            reasons.append(
                f"Equity drawdown {baseline_loss_pct:.2%} reached the configured loss limit {max_loss_pct:.2%}"
            )

    consecutive_losses = trailing_loss_streak(trades)
    if consecutive_losses >= max_consecutive_losses:
        reasons.append(
            f"Consecutive loss streak {consecutive_losses} reached the limit {max_consecutive_losses}"
        )

    metrics: Dict[str, Any] = {
        "current_equity": current_equity,
        "baseline_equity": baseline_equity,
        "baseline_loss_pct": baseline_loss_pct,
        "loss_limit_pct": max_loss_pct,
        "recent_closed_trades": len(trades),
        "consecutive_losses": consecutive_losses,
        "max_consecutive_losses": max_consecutive_losses,
    }

    if getattr(settings, "is_live", False):
        rehearsal = dict(rehearsal_summary or {})
        metrics["rehearsal"] = rehearsal

        min_trades = int(getattr(settings, "live_min_rehearsal_trades", 20) or 20)
        min_win_rate = _coerce_float(getattr(settings, "live_min_rehearsal_win_rate", 0.55))
        require_positive_pnl = bool(getattr(settings, "live_require_positive_rehearsal_pnl", True))

        if not rehearsal.get("available"):
            reasons.append("Live mode blocked: no validated paper/testnet rehearsal history is available")
        else:
            trades_count = int(rehearsal.get("trades", 0) or 0)
            win_rate = _coerce_float(rehearsal.get("win_rate"))
            pnl = _coerce_float(rehearsal.get("pnl"))

            if trades_count < min_trades:
                reasons.append(
                    f"Live mode blocked: rehearsal trades {trades_count} < required {min_trades}"
                )
            if win_rate < min_win_rate:
                reasons.append(
                    f"Live mode blocked: rehearsal win rate {win_rate:.0%} < required {min_win_rate:.0%}"
                )
            if require_positive_pnl and pnl <= 0:
                reasons.append(
                    f"Live mode blocked: rehearsal PnL ${pnl:,.2f} must be positive"
                )

    allowed = not reasons
    return GuardEvaluation(
        allowed=allowed,
        status="ok" if allowed else "paused",
        reasons=reasons,
        metrics=metrics,
    )