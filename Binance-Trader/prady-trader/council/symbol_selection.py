from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config.settings import ROOT_DIR
from ml.model_store import get_latest_model_path

DEFAULT_SYMBOL_AUDIT_FILE = ROOT_DIR / "logs" / "council_trade_audit.json"


def has_trained_model_coverage(symbol: str) -> bool:
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return False
    return any(
        get_latest_model_path(model_type, symbol) is not None
        for model_type in ("lstm", "xgboost", "tft")
    )


def rank_symbols_for_runtime(
    symbol_stats: Dict[str, Dict[str, Any]],
    *,
    configured_symbols: Optional[Iterable[str]] = None,
    require_trained_models: bool = True,
    min_trades: int = 6,
    min_profit_factor: float = 1.0,
    min_expectancy_pct: float = 0.0,
) -> Dict[str, Any]:
    configured = [str(symbol).upper().strip() for symbol in (configured_symbols or symbol_stats.keys()) if str(symbol).strip()]
    ranked: List[Dict[str, Any]] = []

    for symbol in configured:
        stats = dict(symbol_stats.get(symbol, {}) or {})
        trades = int(stats.get("trades", 0) or 0)
        profit_factor = float(stats.get("profit_factor", 0.0) or 0.0)
        expectancy_pct = float(stats.get("expectancy_pct", 0.0) or 0.0)
        win_rate = float(stats.get("win_rate", 0.0) or 0.0)
        models_available = has_trained_model_coverage(symbol)

        reasons: List[str] = []
        eligible = True
        if trades < min_trades:
            eligible = False
            reasons.append(f"needs>={min_trades}_trades")
        if profit_factor < min_profit_factor:
            eligible = False
            reasons.append("profit_factor_below_1")
        if expectancy_pct < min_expectancy_pct:
            eligible = False
            reasons.append("negative_expectancy")
        if require_trained_models and not models_available:
            eligible = False
            reasons.append("models_missing")

        sample_factor = min(trades / float(max(min_trades, 1)), 2.0)
        score = expectancy_pct * max(profit_factor, 0.0) * sample_factor
        ranked.append(
            {
                "symbol": symbol,
                "eligible": eligible,
                "score": round(score, 6),
                "trades": trades,
                "win_rate": round(win_rate, 6),
                "profit_factor": round(profit_factor, 6),
                "expectancy_pct": round(expectancy_pct, 6),
                "total_pnl_pct": round(float(stats.get("total_pnl_pct", 0.0) or 0.0), 6),
                "models_available": models_available,
                "reasons": reasons,
            }
        )

    ranked.sort(
        key=lambda item: (
            1 if item["eligible"] else 0,
            item["score"],
            item["expectancy_pct"],
            item["profit_factor"],
            item["trades"],
        ),
        reverse=True,
    )

    eligible_symbols = [item["symbol"] for item in ranked if item["eligible"]]
    return {
        "eligible_symbols": eligible_symbols,
        "ranked_symbols": ranked,
        "summary": {
            "configured_symbols": configured,
            "eligible_count": len(eligible_symbols),
            "require_trained_models": require_trained_models,
            "min_trades": min_trades,
            "min_profit_factor": min_profit_factor,
            "min_expectancy_pct": min_expectancy_pct,
        },
    }


class SymbolSelectionManager:
    def __init__(self, audit_file: Optional[str | Path] = None):
        self._audit_file = Path(audit_file) if audit_file else DEFAULT_SYMBOL_AUDIT_FILE

    def load_audit(self) -> Dict[str, Any]:
        if not self._audit_file.exists():
            return {}
        try:
            payload = json.loads(self._audit_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def active_symbols(self, configured_symbols: Iterable[str]) -> List[str]:
        configured = [str(symbol).upper().strip() for symbol in configured_symbols if str(symbol).strip()]
        payload = self.load_audit()
        if not payload:
            return configured
        eligible = [
            str(symbol).upper().strip()
            for symbol in payload.get("eligible_symbols", [])
            if str(symbol).strip()
        ]
        allowed = set(eligible)
        return [symbol for symbol in configured if symbol in allowed]