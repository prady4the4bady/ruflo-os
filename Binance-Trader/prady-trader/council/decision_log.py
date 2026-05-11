"""
PRADY TRADER — Council decision logger.
Stores every council decision for audit, backtesting, and weight tuning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import ROOT_DIR
from council.voting import CouncilDecision
from utils.json_safe import SafeJSONEncoder
from utils.time_utils import utc_date_str, utc_now

logger = logging.getLogger("prady.council.decision_log")

LOG_DIR = ROOT_DIR / "logs" / "decisions"


class DecisionLogger:
    """Append-only decision log with JSON-lines format."""

    def __init__(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._filepath = LOG_DIR / f"decisions_{utc_date_str()}.jsonl"
        self._decisions: List[Dict] = []

    def log_decision(self, symbol: str, decision: CouncilDecision):
        """Log a council decision to file and memory."""
        record = {
            "timestamp": utc_now().isoformat(),
            "symbol": symbol,
            "action": decision.action,
            "weighted_score": decision.weighted_score,
            "confidence": decision.confidence,
            "veto": decision.veto,
            "veto_reason": decision.veto_reason,
            "reasoning": decision.reasoning,
            "agent_signals": {
                name: {
                    "direction": sig.direction,
                    "confidence": sig.confidence,
                    "score": sig.score,
                    "reasoning": sig.reasoning,
                    "metadata": dict(sig.metadata or {}),
                }
                for name, sig in decision.agent_signals.items()
            },
        }

        self._decisions.append(record)

        try:
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, cls=SafeJSONEncoder) + "\n")
        except Exception as exc:
            logger.warning("Failed to write decision log: %s", exc)

    def get_recent(self, n: int = 20) -> List[Dict]:
        """Return the last N decisions from memory."""
        return self._decisions[-n:]

    def get_decisions_for_symbol(self, symbol: str, n: int = 50) -> List[Dict]:
        """Return recent decisions for a specific symbol."""
        return [d for d in self._decisions if d["symbol"] == symbol][-n:]

    def load_from_file(self, date_str: Optional[str] = None) -> List[Dict]:
        """Load decisions from a specific date file."""
        if date_str is None:
            date_str = utc_date_str()
        filepath = LOG_DIR / f"decisions_{date_str}.jsonl"
        if not filepath.exists():
            return []
        results = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return results
