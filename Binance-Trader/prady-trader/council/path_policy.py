from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config.settings import ROOT_DIR
from council.voting import CouncilDecision
from council.weight_manager import bounded_normalize_weights

DEFAULT_COUNCIL_AUDIT_FILE = ROOT_DIR / "logs" / "council_trade_audit.json"


def _normalize_agent_list(items: Iterable[Any]) -> List[str]:
    normalized = [str(item).strip() for item in items if str(item).strip()]
    normalized.sort()
    return normalized


class CouncilPathPolicyManager:
    def __init__(self, audit_file: Optional[str | Path] = None):
        self._audit_file = Path(audit_file) if audit_file else DEFAULT_COUNCIL_AUDIT_FILE

    def load_policy(self) -> Dict[str, Any]:
        if not self._audit_file.exists():
            return {}
        try:
            payload = json.loads(self._audit_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        controls = payload.get("recommended_path_controls")
        return controls if isinstance(controls, dict) else {}

    def adjust_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        policy = self.load_policy()
        if not policy:
            return dict(weights)

        disabled_agents = {
            str(agent).strip()
            for agent in policy.get("disabled_agents", [])
            if str(agent).strip()
        }
        penalty_lookup = {
            str(item.get("agent") or "").strip(): float(item.get("multiplier", 1.0) or 1.0)
            for item in policy.get("penalized_agents", [])
            if isinstance(item, dict) and str(item.get("agent") or "").strip()
        }

        adjusted: Dict[str, float] = {}
        changed = False
        for agent_name, weight in weights.items():
            updated = float(weight)
            if agent_name in disabled_agents:
                updated = 0.0
            elif agent_name in penalty_lookup:
                updated = max(0.0, updated * max(0.0, penalty_lookup[agent_name]))
            adjusted[agent_name] = updated
            changed = changed or abs(updated - float(weight)) > 1e-9

        if not changed:
            return dict(weights)
        return bounded_normalize_weights(adjusted, min_weight=0.0)

    def enforce_decision(self, decision: CouncilDecision) -> CouncilDecision:
        if decision.action not in {"LONG", "SHORT"}:
            return decision

        policy = self.load_policy()
        blocked = policy.get("blocked_coalitions")
        if not isinstance(blocked, list) or not blocked:
            return decision

        supporting_agents = _normalize_agent_list(
            agent_name
            for agent_name, signal in decision.agent_signals.items()
            if getattr(signal, "direction", "") == decision.action
        )
        if not supporting_agents:
            return decision

        for entry in blocked:
            if not isinstance(entry, dict):
                continue
            blocked_agents = _normalize_agent_list(entry.get("supporting_agents") or [])
            if blocked_agents != supporting_agents:
                continue
            reason = str(entry.get("reason") or "negative_coalition_expectancy")
            return replace(
                decision,
                action="HOLD",
                reasoning=(
                    f"{decision.reasoning} | Audit policy blocked coalition "
                    f"[{', '.join(supporting_agents)}] ({reason})"
                ),
            )

        return decision