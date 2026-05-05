"""Network broker — allow-list enforcement for outbound connections."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class NetworkRule:
    host_pattern: str
    ports: list[int] = field(default_factory=lambda: [80, 443])
    protocol: str = "tcp"
    allow: bool = True


class NetworkBroker:
    """Enforces network allow-lists for sandboxed agents.

    Default policy: deny all outbound connections unless explicitly allowed.
    """

    # Always-blocked hosts (metadata services, internal networks)
    ALWAYS_DENY = ["169.254.169.254", "metadata.google.internal", "localhost"]

    def __init__(self, default_rules: list[NetworkRule] | None = None) -> None:
        self._rules = default_rules or []
        self._connection_log: list[dict] = []

    def add_rule(self, rule: NetworkRule) -> None:
        self._rules.append(rule)

    def check(self, host: str, port: int, protocol: str = "tcp") -> bool:
        """Check if a connection is allowed. Returns True if permitted."""
        # Always deny dangerous hosts
        for denied in self.ALWAYS_DENY:
            if host == denied or host.endswith(f".{denied}"):
                logger.warning("network_broker.always_denied", host=host, port=port)
                self._log(host, port, protocol, allowed=False)
                return False

        # Check explicit rules
        for rule in self._rules:
            if fnmatch.fnmatch(host, rule.host_pattern):
                if port in rule.ports or not rule.ports:
                    allowed = rule.allow
                    self._log(host, port, protocol, allowed=allowed)
                    if allowed:
                        logger.info("network_broker.allowed", host=host, port=port)
                    else:
                        logger.warning("network_broker.denied_by_rule", host=host, port=port)
                    return allowed

        # Default: deny
        logger.warning("network_broker.default_deny", host=host, port=port)
        self._log(host, port, protocol, allowed=False)
        return False

    def _log(self, host: str, port: int, protocol: str, allowed: bool) -> None:
        self._connection_log.append({
            "host": host, "port": port, "protocol": protocol, "allowed": allowed,
        })

    @property
    def connection_log(self) -> list[dict]:
        return list(self._connection_log)

    def clear_log(self) -> None:
        self._connection_log.clear()
