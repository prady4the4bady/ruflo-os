"""
PRADY TRADER — Replay calibration helpers for council weights.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from config.constants import AGENT_WEIGHTS
from council.weight_manager import bounded_normalize_weights


PriceResolver = Callable[[str, datetime, int], Optional[Tuple[float, float]]]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_decision_timestamp(value: str) -> datetime:
    normalized = str(value).strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    timestamp = datetime.fromisoformat(normalized)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def classify_forward_move(
    entry_price: float,
    future_price: float,
    move_threshold_pct: float = 0.002,
) -> str:
    if entry_price <= 0 or future_price <= 0:
        return "NEUTRAL"

    move_pct = (future_price - entry_price) / entry_price
    if move_pct >= move_threshold_pct:
        return "LONG"
    if move_pct <= -move_threshold_pct:
        return "SHORT"
    return "NEUTRAL"


def load_decision_records(log_dir: Path, max_files: Optional[int] = None) -> List[Dict[str, Any]]:
    files = sorted(log_dir.glob("decisions_*.jsonl"))
    if max_files is not None and max_files > 0:
        files = files[-max_files:]

    records: List[Dict[str, Any]] = []
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
    return records


def evaluate_agent_decisions(
    records: Iterable[Dict[str, Any]],
    price_resolver: PriceResolver,
    *,
    lookahead_minutes: int = 60,
    move_threshold_pct: float = 0.002,
) -> Dict[str, Any]:
    agent_stats: Dict[str, Dict[str, float]] = {
        name: {
            "samples": 0.0,
            "weighted_samples": 0.0,
            "correct_weight": 0.0,
            "total_confidence": 0.0,
            "total_abs_score": 0.0,
        }
        for name in AGENT_WEIGHTS
    }
    decision_outcomes: List[Dict[str, Any]] = []
    total_records = 0
    scored_records = 0
    skipped_no_price = 0
    skipped_neutral_move = 0

    for record in records:
        total_records += 1
        symbol = str(record.get("symbol") or "").upper().strip()
        timestamp_raw = record.get("timestamp")
        if not symbol or not timestamp_raw:
            continue

        timestamp = parse_decision_timestamp(str(timestamp_raw))
        resolved_prices = price_resolver(symbol, timestamp, lookahead_minutes)
        if not resolved_prices:
            skipped_no_price += 1
            continue

        entry_price, future_price = resolved_prices
        outcome_direction = classify_forward_move(
            entry_price,
            future_price,
            move_threshold_pct=move_threshold_pct,
        )
        if outcome_direction == "NEUTRAL":
            skipped_neutral_move += 1
            continue

        scored_records += 1
        decision_outcomes.append(
            {
                "symbol": symbol,
                "timestamp": timestamp.isoformat(),
                "weighted_score": float(record.get("weighted_score", 0.0) or 0.0),
                "confidence": float(record.get("confidence", 0.0) or 0.0),
                "entry_price": entry_price,
                "future_price": future_price,
                "outcome_direction": outcome_direction,
            }
        )

        for agent_name, signal in (record.get("agent_signals") or {}).items():
            if agent_name not in agent_stats or not isinstance(signal, dict):
                continue

            direction = str(signal.get("direction") or "").upper().strip()
            if direction not in {"LONG", "SHORT"}:
                continue

            confidence = _clamp(float(signal.get("confidence", 0.0) or 0.0), 0.0, 1.0)
            abs_score = abs(float(signal.get("score", 0.0) or 0.0))
            sample_weight = (0.25 + (0.75 * confidence)) * (0.35 + (0.65 * _clamp(abs_score / 100.0, 0.0, 1.0)))

            stats = agent_stats[agent_name]
            stats["samples"] += 1.0
            stats["weighted_samples"] += sample_weight
            stats["correct_weight"] += sample_weight if direction == outcome_direction else 0.0
            stats["total_confidence"] += confidence
            stats["total_abs_score"] += abs_score

    for stats in agent_stats.values():
        weighted_samples = stats["weighted_samples"]
        samples = stats["samples"]
        stats["accuracy"] = (stats["correct_weight"] / weighted_samples) if weighted_samples > 0 else 0.5
        stats["avg_confidence"] = (stats["total_confidence"] / samples) if samples > 0 else 0.5
        stats["avg_abs_score"] = (stats["total_abs_score"] / samples) if samples > 0 else 50.0

    return {
        "summary": {
            "total_records": total_records,
            "scored_records": scored_records,
            "skipped_no_price": skipped_no_price,
            "skipped_neutral_move": skipped_neutral_move,
            "lookahead_minutes": lookahead_minutes,
            "move_threshold_pct": move_threshold_pct,
        },
        "agent_stats": agent_stats,
        "decision_outcomes": decision_outcomes,
    }


def recommend_agent_weights(
    agent_stats: Dict[str, Dict[str, float]],
    *,
    base_weights: Optional[Dict[str, float]] = None,
    min_samples: int = 8,
) -> Dict[str, Any]:
    base = dict(base_weights or AGENT_WEIGHTS)
    raw_weights: Dict[str, float] = {}
    diagnostics: Dict[str, Dict[str, float]] = {}

    for name, base_weight in base.items():
        stats = agent_stats.get(name, {})
        samples_value = stats.get("samples", 0.0)
        accuracy_value = stats.get("accuracy", 0.5)
        avg_confidence_value = stats.get("avg_confidence", 0.5)
        avg_abs_score_value = stats.get("avg_abs_score", 50.0)

        samples = int(0 if samples_value is None else samples_value)
        accuracy = float(0.5 if accuracy_value is None else accuracy_value)
        avg_confidence = float(0.5 if avg_confidence_value is None else avg_confidence_value)
        avg_abs_score = float(50.0 if avg_abs_score_value is None else avg_abs_score_value)

        sample_factor = _clamp(samples / float(max(min_samples * 2, 1)), 0.0, 1.0)
        blended_accuracy = ((1.0 - sample_factor) * 0.5) + (sample_factor * accuracy)
        confidence_multiplier = _clamp(1.0 + ((avg_confidence - 0.5) * 0.25), 0.9, 1.1)
        score_multiplier = _clamp(1.0 + (((avg_abs_score / 100.0) - 0.5) * 0.2), 0.9, 1.1)

        raw_weight = base_weight * blended_accuracy * 2.0 * confidence_multiplier * score_multiplier
        raw_weights[name] = raw_weight
        diagnostics[name] = {
            "base_weight": base_weight,
            "samples": float(samples),
            "accuracy": accuracy,
            "blended_accuracy": blended_accuracy,
            "avg_confidence": avg_confidence,
            "avg_abs_score": avg_abs_score,
            "raw_weight": raw_weight,
        }

    return {
        "recommended_weights": bounded_normalize_weights(raw_weights, min_weight=0.0),
        "diagnostics": diagnostics,
    }


def recommend_score_thresholds(
    decision_outcomes: Iterable[Dict[str, Any]],
    *,
    min_threshold: int = 8,
    max_threshold: int = 30,
    soft_cap_threshold: int = 10,
    soft_cap_min_samples: int = 32,
) -> Dict[str, Any]:
    outcomes = list(decision_outcomes)
    best_threshold = min_threshold
    best_metric = -1.0

    for threshold in range(min_threshold, max_threshold + 1):
        directional = 0
        correct = 0
        total = 0

        for outcome in outcomes:
            total += 1
            score = float(outcome.get("weighted_score", 0.0) or 0.0)
            expected = str(outcome.get("outcome_direction") or "NEUTRAL").upper()
            predicted = "HOLD"
            if score >= threshold:
                predicted = "LONG"
            elif score <= -threshold:
                predicted = "SHORT"

            if predicted in {"LONG", "SHORT"}:
                directional += 1
                if predicted == expected:
                    correct += 1

        if total <= 0 or directional <= 0:
            continue

        precision = correct / directional
        coverage = directional / total
        metric = precision * (0.5 + (0.5 * coverage))
        if metric > best_metric:
            best_metric = metric
            best_threshold = threshold

    effective_threshold = best_threshold
    if len(outcomes) < soft_cap_min_samples:
        effective_threshold = min(best_threshold, soft_cap_threshold)

    return {
        "long": effective_threshold,
        "short": -effective_threshold,
        "raw_long": best_threshold,
        "sample_size": len(outcomes),
        "metric": round(best_metric, 4) if best_metric >= 0 else 0.0,
    }


def write_calibration_report(
    output_path: Path,
    *,
    summary: Dict[str, Any],
    agent_stats: Dict[str, Dict[str, float]],
    recommended_weights: Dict[str, float],
    threshold_recommendation: Dict[str, Any],
) -> Path:
    payload = {
        "summary": summary,
        "agent_stats": agent_stats,
        "recommended_weights": recommended_weights,
        "recommended_thresholds": threshold_recommendation,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path