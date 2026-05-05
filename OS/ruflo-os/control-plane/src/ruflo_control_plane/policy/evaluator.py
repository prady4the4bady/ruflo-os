"""Policy evaluation engine — deny-by-default action gating."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

from ruflo_control_plane.policy.rules import DEFAULT_RULES, PolicyRule

logger = structlog.get_logger(__name__)


class PolicyVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyResult:
    verdict: PolicyVerdict
    reason: str
    matched_rule: str | None = None


class PolicyEvaluator:
    """Evaluates actions against security policies.

    Default policy is DENY. Rules explicitly allow or require approval.
    """

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self.rules = rules or DEFAULT_RULES

    def evaluate(
        self,
        action: str,
        agent_type: str = "general",
        context: dict[str, Any] | None = None,
    ) -> PolicyResult:
        """Evaluate an action against policy rules.

        Returns the verdict: allow, deny, or require_approval.
        """
        ctx = context or {}

        for rule in self.rules:
            if rule.matches(action, agent_type, ctx):
                logger.info("policy.matched", action=action, rule=rule.name, verdict=rule.verdict)
                return PolicyResult(
                    verdict=PolicyVerdict(rule.verdict),
                    reason=rule.reason,
                    matched_rule=rule.name,
                )

        # Default: deny
        logger.warning("policy.default_deny", action=action, agent=agent_type)
        return PolicyResult(
            verdict=PolicyVerdict.DENY,
            reason="No matching policy rule — default deny",
        )
