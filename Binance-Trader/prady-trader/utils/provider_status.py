"""Provider telemetry helpers shared across data feeds and UI surfaces."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict

from config.settings import ROOT_DIR

STATUS_FILE = ROOT_DIR / "data" / "provider_status.json"

_LOCK = threading.Lock()
_STATE: Dict[str, Dict[str, Any]] = {}
_PROCESS_STARTED_AT = time.time()


def _provider_key(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name or "unknown").strip().lower())
    return normalized.strip("_") or "unknown"


def _now() -> tuple[float, str]:
    ts = time.time()
    return ts, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))


def _format_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)) if ts > 0 else ""


def _clear_suppression(record: Dict[str, Any]) -> None:
    record["suppressed_until_at"] = 0.0
    record["suppressed_until_iso"] = ""


def _load_from_disk() -> None:
    if _STATE:
        return
    if not STATUS_FILE.exists():
        return
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _STATE.update(data)
    except Exception:
        return


def _tmp_status_file() -> Path:
    suffix = f"{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    return STATUS_FILE.with_name(f"{STATUS_FILE.name}.{suffix}")


def _persist() -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_STATE, indent=2, sort_keys=True)
    tmp = _tmp_status_file()
    tmp.write_text(payload, encoding="utf-8")
    try:
        tmp.replace(STATUS_FILE)
    except PermissionError:
        # Windows can refuse atomic replacement when the target is being watched.
        STATUS_FILE.write_text(payload, encoding="utf-8")
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except PermissionError:
            pass
        except OSError:
            pass


def _base_record(
    provider: str,
    *,
    category: str,
    configured: bool,
    optional: bool,
) -> tuple[str, Dict[str, Any], float, str]:
    _load_from_disk()
    key = _provider_key(provider)
    record = _STATE.setdefault(
        key,
        {
            "provider": key,
            "display_name": provider,
            "category": category,
            "configured": configured,
            "optional": optional,
            "status": "unknown",
            "message": "",
            "consecutive_failures": 0,
            "last_checked_at": 0.0,
            "last_checked_iso": "",
            "last_success_at": 0.0,
            "last_success_iso": "",
            "last_failure_at": 0.0,
            "last_failure_iso": "",
            "last_error": "",
            "last_warning_at": 0.0,
            "suppressed_until_at": 0.0,
            "suppressed_until_iso": "",
            "details": {},
        },
    )
    ts, iso = _now()
    record["display_name"] = provider
    record["category"] = category
    record["configured"] = configured
    record["optional"] = optional
    record["last_checked_at"] = ts
    record["last_checked_iso"] = iso
    return key, record, ts, iso


def mark_provider_disabled(
    provider: str,
    message: str,
    *,
    category: str = "data",
    configured: bool = False,
    optional: bool = True,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    with _LOCK:
        _, record, _, _ = _base_record(
            provider,
            category=category,
            configured=configured,
            optional=optional,
        )
        record["status"] = "disabled"
        record["message"] = message
        record["details"] = details or {}
        record["consecutive_failures"] = 0
        record["last_error"] = ""
        _clear_suppression(record)
        _persist()
        return dict(record)


def mark_provider_success(
    provider: str,
    message: str = "",
    *,
    category: str = "data",
    configured: bool = True,
    optional: bool = True,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    with _LOCK:
        _, record, ts, iso = _base_record(
            provider,
            category=category,
            configured=configured,
            optional=optional,
        )
        record["status"] = "healthy"
        record["message"] = message
        record["details"] = details or {}
        record["consecutive_failures"] = 0
        record["last_error"] = ""
        record["last_success_at"] = ts
        record["last_success_iso"] = iso
        _clear_suppression(record)
        _persist()
        return dict(record)


def mark_provider_failure(
    provider: str,
    message: str,
    *,
    category: str = "data",
    configured: bool = True,
    optional: bool = True,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    with _LOCK:
        _, record, ts, iso = _base_record(
            provider,
            category=category,
            configured=configured,
            optional=optional,
        )
        failures = int(record.get("consecutive_failures", 0) or 0) + 1
        record["consecutive_failures"] = failures
        record["status"] = "error" if configured and failures >= 3 else "degraded"
        record["message"] = message
        record["details"] = details or {}
        record["last_error"] = message
        record["last_failure_at"] = ts
        record["last_failure_iso"] = iso
        _persist()
        return dict(record)


def suppress_provider(
    provider: str,
    message: str,
    *,
    cooldown_sec: int,
    category: str = "data",
    configured: bool = True,
    optional: bool = True,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    with _LOCK:
        _, record, ts, _ = _base_record(
            provider,
            category=category,
            configured=configured,
            optional=optional,
        )
        until = ts + max(0, int(cooldown_sec or 0))
        current_until = float(record.get("suppressed_until_at", 0.0) or 0.0)
        if until > current_until:
            record["suppressed_until_at"] = until
            record["suppressed_until_iso"] = _format_ts(until)
        record["message"] = message
        if details is not None:
            record["details"] = details
        _persist()
        return dict(record)


def is_provider_suppressed(provider: str) -> bool:
    with _LOCK:
        _load_from_disk()
        key = _provider_key(provider)
        record = _STATE.get(key) or {}
        suppressed_until = float(record.get("suppressed_until_at", 0.0) or 0.0)
        return suppressed_until > time.time()


def recommended_suppression_seconds(message: str, *, default_cooldown: int = 300) -> int:
    lowered = str(message or "").lower()
    if not lowered:
        return 0

    auth_markers = (
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "no access",
        "upgrade your subscription",
        "invalid api key",
        "api key",
        "permission denied",
    )
    deprecated_markers = ("404", "deprecated", "not found")
    connectivity_markers = (
        "cannot connect",
        "name or service not known",
        "temporary failure in name resolution",
        "timeout",
        "timed out",
        "connection reset",
        "server disconnected",
        "nodename nor servname",
        "socket",
    )

    if any(marker in lowered for marker in auth_markers):
        return max(int(default_cooldown or 0), 3600)
    if any(marker in lowered for marker in deprecated_markers):
        return max(int(default_cooldown or 0), 21600)
    if any(marker in lowered for marker in connectivity_markers):
        return max(int(default_cooldown or 0), 900)
    return 0


def startup_grace_active(grace_sec: int = 0) -> bool:
    grace = max(0, int(grace_sec or 0))
    if grace <= 0:
        return False
    return (time.time() - _PROCESS_STARTED_AT) < grace


def should_emit_runtime_warning(
    provider: str,
    *,
    cooldown_sec: int = 300,
    startup_grace_sec: int = 0,
    warn_after_failures: int = 1,
) -> bool:
    if startup_grace_active(startup_grace_sec):
        return False
    if is_provider_suppressed(provider):
        return False
    with _LOCK:
        _load_from_disk()
        key = _provider_key(provider)
        record = _STATE.get(key) or {}
        failures = int(record.get("consecutive_failures", 0) or 0)
    threshold = max(1, int(warn_after_failures or 1))
    if failures < threshold:
        return False
    return should_emit_warning(provider, cooldown_sec=cooldown_sec)


def should_emit_warning(provider: str, cooldown_sec: int = 300) -> bool:
    with _LOCK:
        _load_from_disk()
        key = _provider_key(provider)
        record = _STATE.setdefault(key, {"provider": key, "display_name": provider, "last_warning_at": 0.0})
        now = time.time()
        last_warning = float(record.get("last_warning_at", 0.0) or 0.0)
        failures = int(record.get("consecutive_failures", 0) or 0)
        emit = failures <= 1 or (now - last_warning) >= max(0, cooldown_sec)
        if emit:
            record["last_warning_at"] = now
            _persist()
        return emit


def load_provider_statuses() -> Dict[str, Dict[str, Any]]:
    with _LOCK:
        _load_from_disk()
        return {key: dict(value) for key, value in _STATE.items()}
