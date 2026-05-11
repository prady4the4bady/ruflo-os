"""
PRADY TRADER — State writer.
Writes live trading state to JSON file every cycle for the dashboard to read.
Also writes to Redis if available.
"""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.mode_policy import get_all_mode_policies, get_mode_policy
from config.settings import ROOT_DIR
from utils.json_safe import SafeJSONEncoder

logger = logging.getLogger("prady.data.state_writer")

STATE_FILE = ROOT_DIR / "data" / "live_state.json"
MODE_STATE_FILES = {
    "paper": ROOT_DIR / "data" / "state_paper.json",
    "testnet": ROOT_DIR / "data" / "state_testnet.json",
    "live": ROOT_DIR / "data" / "state_live.json",
}
class StateWriter:
    """Writes orchestrator state to shared JSON file for dashboard."""

    def __init__(self, path: Path = STATE_FILE):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._redis = None
        self._try_redis()

    def _try_redis(self):
        """Try to connect to Redis for pub/sub dashboard updates."""
        try:
            from config.settings import get_settings
            url = get_settings().redis_url
            if url:
                import redis
                self._redis = redis.from_url(url, decode_responses=True)
                self._redis.ping()
                logger.info("StateWriter connected to Redis")
        except Exception:
            self._redis = None

    def read_state(self, runtime_mode: Optional[str] = None) -> Dict[str, Any]:
        """Read the most recent persisted state for a runtime mode."""
        mode = str(runtime_mode or "").lower().strip()
        mode_path = MODE_STATE_FILES.get(mode)
        candidates = []
        if mode_path is not None:
            candidates.append(mode_path)
        candidates.append(self._path)

        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                logger.debug("Failed to read state file %s: %s", candidate, exc)
        return {}

    def write(self, state: Dict[str, Any]) -> None:
        """Write state dict to JSON file and optionally Redis."""
        state["_updated_at"] = time.time()
        state["_updated_iso"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        runtime_mode = str(state.get("trading_mode", "paper")).lower()
        mode_path = MODE_STATE_FILES.get(runtime_mode, STATE_FILE)

        try:
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, cls=SafeJSONEncoder, indent=2)
            tmp.replace(self._path)

            if mode_path != self._path:
                mode_tmp = mode_path.with_suffix(".tmp")
                with open(mode_tmp, "w", encoding="utf-8") as f:
                    json.dump(state, f, cls=SafeJSONEncoder, indent=2)
                mode_tmp.replace(mode_path)
        except Exception as exc:
            logger.error("Failed to write state file: %s", exc)

        if self._redis:
            try:
                payload = json.dumps(state, cls=SafeJSONEncoder)
                self._redis.set("prady:live_state", payload)
                self._redis.set("prady:state:current", payload)
                self._redis.set(f"prady:state:{runtime_mode}", payload)
                self._redis.publish("prady:state_update", "1")
            except Exception as exc:
                logger.warning("Redis state publish failed: %s", exc)

    def build_state(
        self,
        paper_engine,
        last_decisions: Dict,
        prices: Dict[str, float],
        cycle_count: int,
        start_time: float,
        kill_switch: bool,
        agent_signals: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Build the full state dict from components."""
        from config.settings import get_settings

        settings = get_settings()
        stats = paper_engine.get_stats()
        positions_list = []
        for sym, pos in paper_engine.positions.items():
            cur_price = Decimal(str(prices.get(sym, 0)))
            positions_list.append({
                "symbol": sym,
                "direction": "LONG" if pos.side == "BUY" else "SHORT",
                "entry_price": float(pos.entry_price),
                "current_price": float(cur_price),
                "quantity": float(pos.quantity),
                "leverage": pos.leverage,
                "pnl": float(pos.unrealised_pnl(cur_price)),
                "holding_minutes": (time.time() - pos.entry_time) / 60.0,
            })

        decisions_dict = {}
        for sym, dec in last_decisions.items():
            decisions_dict[sym] = {
                "action": dec.action,
                "weighted_score": dec.weighted_score,
                "confidence": dec.confidence,
                "veto": dec.veto,
                "veto_reason": dec.veto_reason or "",
                "reasoning": dec.reasoning,
            }

        signals_dict = {}
        if agent_signals:
            for sym, sym_signals in agent_signals.items():
                signals_dict[sym] = {}
                for agent_name, sig in sym_signals.items():
                    metadata = sig.metadata if hasattr(sig, "metadata") else sig.get("metadata", {})
                    if not isinstance(metadata, dict):
                        metadata = {}
                    signals_dict[sym][agent_name] = {
                        "direction": sig.direction if hasattr(sig, "direction") else str(sig.get("direction", "")),
                        "confidence": sig.confidence if hasattr(sig, "confidence") else float(sig.get("confidence", 0)),
                        "score": sig.score if hasattr(sig, "score") else float(sig.get("score", 0)),
                        "reasoning": sig.reasoning if hasattr(sig, "reasoning") else str(sig.get("reasoning", "")),
                        "metadata": metadata,
                    }

        equity = float(paper_engine.get_equity(prices))

        return {
            "system_running": not kill_switch,
            "trading_mode": settings.trading_mode,
            "runtime_mode": settings.runtime_mode,
            "mode_label": settings.mode_label,
            "mode_policy": get_mode_policy(settings.trading_mode),
            "mode_policies": get_all_mode_policies(),
            "execution_environment": settings.execution_environment,
            "cycle_count": cycle_count,
            "uptime_seconds": time.time() - start_time,
            "balance": stats["balance"],
            "equity": equity,
            "initial_balance": stats["initial_balance"],
            "total_return_pct": stats.get("total_return_pct", 0.0),
            "total_pnl": stats.get("total_pnl", 0.0),
            "daily_pnl": stats.get("total_pnl", 0.0),
            "total_trades": stats.get("total_trades", 0),
            "win_rate": stats.get("win_rate", 0.0),
            "best_trade": stats.get("best_trade", 0.0),
            "worst_trade": stats.get("worst_trade", 0.0),
            "open_positions": positions_list,
            "closed_trades": paper_engine.get_trade_history(100),
            "last_decisions": decisions_dict,
            "agent_signals": signals_dict,
            "prices": prices,
            "kill_switch": kill_switch,
            "runtime_guard": {
                "allowed": True,
                "status": "ok",
                "reasons": [],
                "metrics": {},
            },
        }
