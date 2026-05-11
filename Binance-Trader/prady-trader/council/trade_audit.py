from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from council.calibration import parse_decision_timestamp
from council.symbol_selection import rank_symbols_for_runtime

TradePathResolver = Callable[[str, datetime, int], Optional[Dict[str, Any]]]


def _new_performance_bucket() -> Dict[str, Any]:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl_pct": 0.0,
        "gross_profit_pct": 0.0,
        "gross_loss_pct": 0.0,
        "exit_reasons": {},
        "actions": {},
        "symbol_counts": {},
        "confidence_sum": 0.0,
        "abs_score_sum": 0.0,
    }


def _update_performance_bucket(
    bucket: Dict[str, Any],
    trade_record: Dict[str, Any],
    *,
    confidence: Optional[float] = None,
    score: Optional[float] = None,
) -> None:
    pnl_pct = float(trade_record.get("pnl_pct", 0.0) or 0.0)
    exit_reason = str(trade_record.get("exit_reason") or "time_exit")
    action = str(trade_record.get("action") or "UNKNOWN")
    symbol = str(trade_record.get("symbol") or "")

    bucket["trades"] += 1
    bucket["total_pnl_pct"] += pnl_pct
    bucket["exit_reasons"][exit_reason] = int(bucket["exit_reasons"].get(exit_reason, 0)) + 1
    bucket["actions"][action] = int(bucket["actions"].get(action, 0)) + 1
    if symbol:
        bucket["symbol_counts"][symbol] = int(bucket["symbol_counts"].get(symbol, 0)) + 1
    if confidence is not None:
        bucket["confidence_sum"] += float(confidence)
    if score is not None:
        bucket["abs_score_sum"] += abs(float(score))

    if pnl_pct > 0.0:
        bucket["wins"] += 1
        bucket["gross_profit_pct"] += pnl_pct
    elif pnl_pct < 0.0:
        bucket["losses"] += 1
        bucket["gross_loss_pct"] += abs(pnl_pct)


def _finalize_performance_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    trades = int(bucket.get("trades", 0) or 0)
    wins = int(bucket.get("wins", 0) or 0)
    gross_profit_pct = float(bucket.get("gross_profit_pct", 0.0) or 0.0)
    gross_loss_pct = float(bucket.get("gross_loss_pct", 0.0) or 0.0)
    total_pnl_pct = float(bucket.get("total_pnl_pct", 0.0) or 0.0)

    return {
        "trades": trades,
        "wins": wins,
        "losses": int(bucket.get("losses", 0) or 0),
        "total_pnl_pct": total_pnl_pct,
        "gross_profit_pct": gross_profit_pct,
        "gross_loss_pct": gross_loss_pct,
        "exit_reasons": dict(bucket.get("exit_reasons") or {}),
        "actions": dict(bucket.get("actions") or {}),
        "symbols": sorted(
            (bucket.get("symbol_counts") or {}).keys(),
            key=lambda symbol: (
                int((bucket.get("symbol_counts") or {}).get(symbol, 0)),
                symbol,
            ),
            reverse=True,
        ),
        "win_rate": (wins / trades) if trades > 0 else 0.0,
        "expectancy_pct": (total_pnl_pct / trades) if trades > 0 else 0.0,
        "profit_factor": (gross_profit_pct / gross_loss_pct) if gross_loss_pct > 0 else (float("inf") if gross_profit_pct > 0 else 0.0),
        "avg_confidence": (float(bucket.get("confidence_sum", 0.0) or 0.0) / trades) if trades > 0 else 0.0,
        "avg_abs_score": (float(bucket.get("abs_score_sum", 0.0) or 0.0) / trades) if trades > 0 else 0.0,
    }


def _sort_bucket_map(bucket_map: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    sorted_items = sorted(
        bucket_map.items(),
        key=lambda item: (
            float(item[1].get("expectancy_pct", 0.0) or 0.0),
            -int(item[1].get("trades", 0) or 0),
            item[0],
        ),
    )
    return {name: stats for name, stats in sorted_items}


def _recommend_penalty_multiplier(expectancy_pct: float, profit_factor: float) -> float:
    multiplier = 0.75
    if expectancy_pct <= -0.25:
        multiplier = 0.35
    elif expectancy_pct <= -0.15:
        multiplier = 0.5
    elif expectancy_pct <= -0.08:
        multiplier = 0.65

    if profit_factor < 0.5:
        multiplier = min(multiplier, 0.5)
    if profit_factor < 0.25:
        multiplier = min(multiplier, 0.35)
    return round(max(0.25, multiplier), 3)


def recommend_path_controls(
    supporting_agent_stats: Dict[str, Dict[str, Any]],
    coalition_attribution: Iterable[Dict[str, Any]],
    *,
    disable_agent_min_trades: int = 6,
    disable_agent_max_expectancy_pct: float = -0.20,
    disable_agent_max_profit_factor: float = 0.35,
    penalize_agent_min_trades: int = 4,
    penalize_agent_max_expectancy_pct: float = -0.05,
    penalize_agent_max_profit_factor: float = 0.80,
    block_coalition_min_trades: int = 2,
    block_coalition_max_expectancy_pct: float = -0.25,
    block_coalition_max_profit_factor: float = 0.60,
) -> Dict[str, Any]:
    disabled_agents: List[str] = []
    penalized_agents: List[Dict[str, Any]] = []
    blocked_coalitions: List[Dict[str, Any]] = []

    for agent_name, stats in supporting_agent_stats.items():
        trades = int(stats.get("trades", 0) or 0)
        expectancy_pct = float(stats.get("expectancy_pct", 0.0) or 0.0)
        profit_factor = float(stats.get("profit_factor", 0.0) or 0.0)

        if (
            trades >= disable_agent_min_trades
            and expectancy_pct <= disable_agent_max_expectancy_pct
            and profit_factor <= disable_agent_max_profit_factor
        ):
            disabled_agents.append(agent_name)
            continue

        if (
            trades >= penalize_agent_min_trades
            and expectancy_pct <= penalize_agent_max_expectancy_pct
            and profit_factor <= penalize_agent_max_profit_factor
        ):
            penalized_agents.append(
                {
                    "agent": agent_name,
                    "multiplier": _recommend_penalty_multiplier(expectancy_pct, profit_factor),
                    "trades": trades,
                    "expectancy_pct": round(expectancy_pct, 6),
                    "profit_factor": round(profit_factor, 6),
                    "reason": "negative_support_expectancy",
                }
            )

    disabled_set = set(disabled_agents)
    for entry in coalition_attribution:
        trades = int(entry.get("trades", 0) or 0)
        expectancy_pct = float(entry.get("expectancy_pct", 0.0) or 0.0)
        profit_factor = float(entry.get("profit_factor", 0.0) or 0.0)
        supporting_agents = [
            str(agent).strip()
            for agent in (entry.get("supporting_agents") or [])
            if str(agent).strip()
        ]
        if not supporting_agents:
            continue
        if all(agent in disabled_set for agent in supporting_agents):
            continue
        if (
            trades >= block_coalition_min_trades
            and expectancy_pct <= block_coalition_max_expectancy_pct
            and profit_factor <= block_coalition_max_profit_factor
        ):
            blocked_coalitions.append(
                {
                    "supporting_agents": supporting_agents,
                    "trades": trades,
                    "expectancy_pct": round(expectancy_pct, 6),
                    "profit_factor": round(profit_factor, 6),
                    "win_rate": round(float(entry.get("win_rate", 0.0) or 0.0), 6),
                    "reason": "negative_coalition_expectancy",
                }
            )

    disabled_agents.sort()
    penalized_agents.sort(key=lambda item: (item["multiplier"], item["agent"]))
    blocked_coalitions.sort(key=lambda item: (item["expectancy_pct"], -item["trades"], "+".join(item["supporting_agents"])))
    return {
        "disabled_agents": disabled_agents,
        "penalized_agents": penalized_agents,
        "blocked_coalitions": blocked_coalitions,
        "summary": {
            "disable_agent_min_trades": disable_agent_min_trades,
            "disable_agent_max_expectancy_pct": disable_agent_max_expectancy_pct,
            "disable_agent_max_profit_factor": disable_agent_max_profit_factor,
            "penalize_agent_min_trades": penalize_agent_min_trades,
            "penalize_agent_max_expectancy_pct": penalize_agent_max_expectancy_pct,
            "penalize_agent_max_profit_factor": penalize_agent_max_profit_factor,
            "block_coalition_min_trades": block_coalition_min_trades,
            "block_coalition_max_expectancy_pct": block_coalition_max_expectancy_pct,
            "block_coalition_max_profit_factor": block_coalition_max_profit_factor,
        },
    }


def simulate_trade_path(
    path: Dict[str, Any],
    action: str,
    *,
    stop_loss_pct: float = 0.02,
    take_profit_pct: float = 0.03,
) -> Dict[str, Any]:
    direction = str(action or "").upper().strip()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError(f"Unsupported trade direction: {action}")

    entry_price = float(path.get("entry_price", 0.0) or 0.0)
    future_price = float(path.get("future_price", entry_price) or entry_price)
    bars = list(path.get("bars") or [])
    if entry_price <= 0:
        raise ValueError("Trade path is missing a valid entry_price")

    if direction == "LONG":
        stop_price = entry_price * (1.0 - stop_loss_pct)
        take_profit_price = entry_price * (1.0 + take_profit_pct)
    else:
        stop_price = entry_price * (1.0 + stop_loss_pct)
        take_profit_price = entry_price * (1.0 - take_profit_pct)

    exit_price = future_price
    exit_reason = "time_exit"

    for bar in bars:
        high = float(bar.get("high", entry_price) or entry_price)
        low = float(bar.get("low", entry_price) or entry_price)
        if direction == "LONG":
            stop_hit = low <= stop_price
            target_hit = high >= take_profit_price
        else:
            stop_hit = high >= stop_price
            target_hit = low <= take_profit_price

        if stop_hit and target_hit:
            exit_price = stop_price
            exit_reason = "stop_loss_intrabar_collision"
            break
        if stop_hit:
            exit_price = stop_price
            exit_reason = "stop_loss"
            break
        if target_hit:
            exit_price = take_profit_price
            exit_reason = "take_profit"
            break

    if direction == "LONG":
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
    else:
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0

    return {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "exit_reason": exit_reason,
        "pnl_pct": pnl_pct,
        "profitable": pnl_pct > 0.0,
    }


def evaluate_council_trades(
    records: Iterable[Dict[str, Any]],
    path_resolver: TradePathResolver,
    *,
    lookahead_minutes: int = 60,
    stop_loss_pct: float = 0.02,
    take_profit_pct: float = 0.03,
    min_confidence: float = 0.60,
    configured_symbols: Optional[Iterable[str]] = None,
    selection_min_trades: int = 6,
    selection_min_profit_factor: float = 1.0,
    selection_min_expectancy_pct: float = 0.0,
) -> Dict[str, Any]:
    trades: List[Dict[str, Any]] = []
    symbol_buckets: Dict[str, Dict[str, Any]] = {}
    supporting_agent_buckets: Dict[str, Dict[str, Any]] = {}
    opposing_agent_buckets: Dict[str, Dict[str, Any]] = {}
    coalition_buckets: Dict[str, Dict[str, Any]] = {}

    total_records = 0
    directional_records = 0
    simulated_trades = 0
    skipped_no_path = 0
    skipped_low_confidence = 0

    configured = [str(symbol).upper().strip() for symbol in (configured_symbols or []) if str(symbol).strip()]
    configured_set = set(configured)

    for record in records:
        total_records += 1
        symbol = str(record.get("symbol") or "").upper().strip()
        action = str(record.get("action") or "").upper().strip()
        confidence = float(record.get("confidence", 0.0) or 0.0)
        timestamp_raw = record.get("timestamp")

        if configured_set and symbol not in configured_set:
            continue
        if action not in {"LONG", "SHORT"}:
            continue
        directional_records += 1
        if confidence < min_confidence:
            skipped_low_confidence += 1
            continue
        if not timestamp_raw or not symbol:
            continue

        timestamp = parse_decision_timestamp(str(timestamp_raw))
        path = path_resolver(symbol, timestamp, lookahead_minutes)
        if not path:
            skipped_no_path += 1
            continue

        simulated = simulate_trade_path(
            path,
            action,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        simulated_trades += 1

        raw_signals = record.get("agent_signals") or {}
        supporting_agents: List[str] = []
        opposing_agents: List[str] = []
        supporting_signal_snapshot: Dict[str, Dict[str, float]] = {}
        opposing_signal_snapshot: Dict[str, Dict[str, float]] = {}
        for agent_name, signal in raw_signals.items():
            if not isinstance(signal, dict):
                continue
            signal_direction = str(signal.get("direction") or "").upper().strip()
            if signal_direction not in {"LONG", "SHORT"}:
                continue
            signal_snapshot = {
                "confidence": float(signal.get("confidence", 0.0) or 0.0),
                "score": float(signal.get("score", 0.0) or 0.0),
            }
            if signal_direction == action:
                supporting_agents.append(agent_name)
                supporting_signal_snapshot[agent_name] = signal_snapshot
            else:
                opposing_agents.append(agent_name)
                opposing_signal_snapshot[agent_name] = signal_snapshot

        supporting_agents.sort()
        opposing_agents.sort()
        coalition_key = "+".join(supporting_agents)

        trade_record = {
            "symbol": symbol,
            "timestamp": timestamp.isoformat(),
            "action": action,
            "confidence": confidence,
            "weighted_score": float(record.get("weighted_score", 0.0) or 0.0),
            "supporting_agents": supporting_agents,
            "opposing_agents": opposing_agents,
            "supporting_signals": supporting_signal_snapshot,
            "opposing_signals": opposing_signal_snapshot,
            "coalition_key": coalition_key,
            **simulated,
        }
        trades.append(trade_record)

        symbol_bucket = symbol_buckets.setdefault(symbol, _new_performance_bucket())
        _update_performance_bucket(symbol_bucket, trade_record)

        for agent_name in supporting_agents:
            support_bucket = supporting_agent_buckets.setdefault(agent_name, _new_performance_bucket())
            signal_snapshot = supporting_signal_snapshot.get(agent_name, {})
            _update_performance_bucket(
                support_bucket,
                trade_record,
                confidence=float(signal_snapshot.get("confidence", 0.0) or 0.0),
                score=float(signal_snapshot.get("score", 0.0) or 0.0),
            )

        for agent_name in opposing_agents:
            opposing_bucket = opposing_agent_buckets.setdefault(agent_name, _new_performance_bucket())
            signal_snapshot = opposing_signal_snapshot.get(agent_name, {})
            _update_performance_bucket(
                opposing_bucket,
                trade_record,
                confidence=float(signal_snapshot.get("confidence", 0.0) or 0.0),
                score=float(signal_snapshot.get("score", 0.0) or 0.0),
            )

        coalition_bucket = coalition_buckets.setdefault(coalition_key, _new_performance_bucket())
        _update_performance_bucket(
            coalition_bucket,
            trade_record,
            confidence=confidence,
            score=float(record.get("weighted_score", 0.0) or 0.0),
        )

    symbol_stats = {
        symbol: _finalize_performance_bucket(bucket)
        for symbol, bucket in symbol_buckets.items()
    }
    supporting_agent_stats = _sort_bucket_map(
        {
            agent_name: _finalize_performance_bucket(bucket)
            for agent_name, bucket in supporting_agent_buckets.items()
        }
    )
    opposing_agent_stats = _sort_bucket_map(
        {
            agent_name: _finalize_performance_bucket(bucket)
            for agent_name, bucket in opposing_agent_buckets.items()
        }
    )

    coalition_attribution: List[Dict[str, Any]] = []
    for coalition_key, bucket in coalition_buckets.items():
        coalition_attribution.append(
            {
                "coalition_key": coalition_key,
                "supporting_agents": [agent for agent in coalition_key.split("+") if agent],
                **_finalize_performance_bucket(bucket),
            }
        )
    coalition_attribution.sort(
        key=lambda item: (
            float(item.get("expectancy_pct", 0.0) or 0.0),
            -int(item.get("trades", 0) or 0),
            item.get("coalition_key", ""),
        )
    )

    overall = {
        "trades": len(trades),
        "wins": sum(1 for trade in trades if float(trade.get("pnl_pct", 0.0) or 0.0) > 0),
        "losses": sum(1 for trade in trades if float(trade.get("pnl_pct", 0.0) or 0.0) < 0),
        "total_pnl_pct": sum(float(trade.get("pnl_pct", 0.0) or 0.0) for trade in trades),
    }
    overall["win_rate"] = (overall["wins"] / overall["trades"]) if overall["trades"] > 0 else 0.0
    gross_profit_pct = sum(float(trade.get("pnl_pct", 0.0) or 0.0) for trade in trades if float(trade.get("pnl_pct", 0.0) or 0.0) > 0)
    gross_loss_pct = abs(sum(float(trade.get("pnl_pct", 0.0) or 0.0) for trade in trades if float(trade.get("pnl_pct", 0.0) or 0.0) < 0))
    overall["profit_factor"] = (gross_profit_pct / gross_loss_pct) if gross_loss_pct > 0 else (float("inf") if gross_profit_pct > 0 else 0.0)
    overall["expectancy_pct"] = (overall["total_pnl_pct"] / overall["trades"]) if overall["trades"] > 0 else 0.0

    selection = rank_symbols_for_runtime(
        symbol_stats,
        configured_symbols=configured or symbol_stats.keys(),
        min_trades=selection_min_trades,
        min_profit_factor=selection_min_profit_factor,
        min_expectancy_pct=selection_min_expectancy_pct,
    )
    path_controls = recommend_path_controls(supporting_agent_stats, coalition_attribution)

    return {
        "summary": {
            "total_records": total_records,
            "directional_records": directional_records,
            "simulated_trades": simulated_trades,
            "skipped_low_confidence": skipped_low_confidence,
            "skipped_no_path": skipped_no_path,
            "lookahead_minutes": lookahead_minutes,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "min_confidence": min_confidence,
            "selection_min_trades": selection_min_trades,
            "selection_min_profit_factor": selection_min_profit_factor,
            "selection_min_expectancy_pct": selection_min_expectancy_pct,
            "overall": overall,
        },
        "symbol_stats": symbol_stats,
        "agent_attribution": {
            "supporting": supporting_agent_stats,
            "opposing": opposing_agent_stats,
        },
        "coalition_attribution": coalition_attribution,
        "recommended_path_controls": path_controls,
        "eligible_symbols": selection["eligible_symbols"],
        "ranked_symbols": selection["ranked_symbols"],
        "trades": trades,
    }


def write_trade_audit_report(output_path: Path, payload: Dict[str, Any]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path