"""PRADY TRADER — Background data worker (runs in QThread)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from PyQt6.QtCore import QThread, pyqtSignal

from utils.time_utils import utc_date_str

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("prady.desktop.worker")


class DataWorker(QThread):
    """Fetches dashboard data off the main thread every *interval* seconds."""

    data_ready = pyqtSignal(dict)

    def __init__(self, interval: int = 5):
        super().__init__()
        self._interval = interval
        self._running = True

    # ── lifecycle ────────────────────────────────────────────
    def stop(self):
        self._running = False
        self.wait(3000)

    def run(self):
        while self._running:
            try:
                d = self._fetch()
                self.data_ready.emit(d)
            except Exception:
                logger.exception("Data worker refresh failed")
            # sleep in small chunks so stop() is responsive
            for _ in range(self._interval * 10):
                if not self._running:
                    return
                self.msleep(100)

    # ── data collection ──────────────────────────────────────
    _binance_cache: dict = {}
    _binance_cache_ts: float = 0.0
    _binance_cache_signature: tuple[str, str] | None = None

    def _fetch(self) -> Dict[str, Any]:
        import sys
        sys.path.insert(0, str(ROOT))

        from dashboard.state import get_dashboard_state, refresh_live_data

        state = get_dashboard_state()
        refresh_live_data(state)

        # Read health / process files
        health_data: dict = {}
        hf = ROOT / "data" / "health_status.json"
        if hf.exists():
            try:
                health_data = json.loads(hf.read_text(encoding="utf-8"))
            except Exception:
                pass

        process_data: dict = {}
        pf = ROOT / "data" / "process_state.json"
        if pf.exists():
            try:
                process_data = json.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Read recent decision logs (last 30 decisions)
        decision_log: list = []
        try:
            log_dir = ROOT / "logs" / "decisions"
            today = utc_date_str()
            log_file = log_dir / f"decisions_{today}.jsonl"
            if log_file.exists():
                lines = log_file.read_text(encoding="utf-8").strip().split("\n")
                for line in lines[-30:]:
                    if line.strip():
                        try:
                            decision_log.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass

        # Read recent structured log entries (last 50 for agent activity)
        agent_activity: list = []
        try:
            sf = ROOT / "logs" / "structured.jsonl"
            if sf.exists():
                with open(sf, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines[-50:]:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            record = entry.get("record", {})
                            msg = record.get("message", "")
                            level = record.get("level", {}).get("name", "INFO")
                            ts = record.get("time", {}).get("repr", "")
                            module = record.get("module", "")
                            agent_activity.append({
                                "timestamp": ts[:19] if ts else "",
                                "level": level,
                                "module": module,
                                "message": msg,
                            })
                        except Exception:
                            pass
        except Exception:
            pass

        # Fetch Binance account info (cached for 30s to avoid rate limits)
        account_signature = (str(state.trading_mode), str(state.execution_environment))
        binance_accounts: dict = dict(state.binance_accounts) if state.binance_accounts else {}
        snapshot_signature = None
        if binance_accounts:
            snapshot_signature = (
                str(binance_accounts.get("runtime_mode", state.trading_mode)),
                str(binance_accounts.get("execution_environment", state.execution_environment)),
            )

        if not binance_accounts or snapshot_signature != account_signature:
            try:
                now = time.time()
                if (
                    now - DataWorker._binance_cache_ts > 30
                    or not DataWorker._binance_cache
                    or DataWorker._binance_cache_signature != account_signature
                ):
                    from data.binance_client import get_binance_client

                    bc = get_binance_client()
                    DataWorker._binance_cache = bc.get_full_account_info()
                    DataWorker._binance_cache_ts = now
                    DataWorker._binance_cache_signature = account_signature
                binance_accounts = DataWorker._binance_cache
            except Exception as exc:
                if DataWorker._binance_cache and DataWorker._binance_cache_signature == account_signature:
                    binance_accounts = DataWorker._binance_cache
                else:
                    binance_accounts = {
                        "error": str(exc),
                        "runtime_mode": account_signature[0],
                        "execution_environment": account_signature[1],
                    }
        else:
            DataWorker._binance_cache = binance_accounts
            DataWorker._binance_cache_ts = time.time()
            DataWorker._binance_cache_signature = account_signature

        return {
            "system_running": state.system_running,
            "trading_mode": state.trading_mode,
            "execution_environment": state.execution_environment,
            "balance": state.balance,
            "equity": state.equity,
            "daily_pnl": state.daily_pnl,
            "total_pnl": state.total_pnl,
            "total_trades": state.total_trades,
            "win_rate": state.win_rate,
            "best_trade": state.best_trade,
            "worst_trade": state.worst_trade,
            "open_positions": list(state.open_positions),
            "closed_trades": list(state.closed_trades),
            "last_decisions": dict(state.last_decisions),
            "agent_signals": dict(state.agent_signals),
            "agent_weights": dict(state.agent_weights),
            "prices": dict(state.prices),
            "cycle_count": state.cycle_count,
            "initial_balance": state.initial_balance,
            "total_return_pct": state.total_return_pct,
            "uptime_seconds": state.uptime_seconds,
            "uptime_str": state.uptime_str,
            "market_overview": dict(state.market_overview),
            "fear_greed": dict(state.fear_greed),
            "news": list(state.news),
            "trending": list(state.trending),
            "kill_switch": state.kill_switch,
            "model_info": dict(state.model_info),
            "ensemble_predictions": dict(state.ensemble_predictions),
            "mode_snapshots": dict(state.mode_snapshots),
            "active_mode_policy": dict(state.active_mode_policy),
            "mode_account_views": dict(state.mode_account_views),
            "provider_statuses": dict(state.provider_statuses),
            "rate_limiter_stats": dict(state.rate_limiter_stats),
            "health_data": health_data,
            "process_data": process_data,
            "decision_log": decision_log,
            "agent_activity": agent_activity,
            "binance_accounts": binance_accounts,
            "binance_account": binance_accounts,
        }


class OrchestratorWorker(QThread):
    """Runs the TradingOrchestrator in its own thread + event loop."""

    status = pyqtSignal(str)  # "running" | "stopped" | "error: ..."

    def __init__(self, mode: str = "paper"):
        super().__init__()
        self._mode = mode
        self._orch = None
        self._loop = None

    def run(self):
        import asyncio, sys, traceback
        sys.path.insert(0, str(ROOT))
        try:
            from config.settings import apply_runtime_mode

            apply_runtime_mode(self._mode, persist=False)

            from council.orchestrator import TradingOrchestrator

            logger.info("Creating TradingOrchestrator for mode=%s", self._mode)
            self._orch = TradingOrchestrator()
            logger.info("TradingOrchestrator created successfully")
            self.status.emit("running")

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            logger.info("Starting orchestrator event loop")
            self._loop.run_until_complete(self._orch.run())
            logger.info("Orchestrator event loop finished normally")
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Orchestrator worker failed: %s\n%s", exc, tb)
            self.status.emit(f"error: {exc}")
        finally:
            if self._loop and not self._loop.is_closed():
                self._loop.close()
                logger.info("Closed orchestrator event loop")
            self.status.emit("stopped")

    def request_stop(self):
        if self._orch:
            logger.info("Stop requested for orchestrator worker")
            self._orch._kill_switch = True
