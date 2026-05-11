"""UTC helpers used across runtime, persistence, and tests."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    """Return a naive datetime that still represents UTC time."""
    return utc_now().replace(tzinfo=None)


def utc_date_str(fmt: str = "%Y%m%d") -> str:
    """Format the current UTC time using the provided pattern."""
    return utc_now().strftime(fmt)


def parse_utc_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp and normalize it to a UTC-aware datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
