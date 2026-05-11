"""
PRADY TRADER — Council orchestrator.
Runs all agents in parallel, collects signals, runs the vote,
handles veto checks, and triggers execution.
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Dict, Optional

from agents.base_agent import AgentSignal
from agents.oracle_agent import OracleAgent
from agents.sentinel_agent import SentinelAgent
from agents.prophet_agent import ProphetAgent
from agents.arbiter_agent import ArbiterAgent
from agents.debater_agent import DebaterAgent
from agents.warden_agent import WardenAgent
from agents.executor_agent import ExecutorAgent
from agents.oracle_extended_agent import OracleExtendedAgent
from agents.strategy_fusion_agent import StrategyFusionAgent
from config.settings import get_settings
from council.path_policy import CouncilPathPolicyManager
from council.voting import vote, CouncilDecision
from council.weight_manager import WeightManager
from council.decision_log import DecisionLogger
from council.symbol_selection import SymbolSelectionManager
from execution.capital_guard import evaluate_runtime_guard, load_rehearsal_summary

logger = logging.getLogger("prady.council.orchestrator")


class CouncilOrchestrator:
    """
    Main loop that:
    1. Runs Oracle, Sentinel, Prophet, Arbiter in parallel
    2. Feeds their signals to Debater
    3. Runs Warden veto check
    4. Conducts council vote
    5. Triggers Executor if vote passes
    """

    def __init__(self):
        self.oracle = OracleAgent()
        self.sentinel = SentinelAgent()
        self.prophet = ProphetAgent()
        self.arbiter = ArbiterAgent()
        self.oracle_extended = OracleExtendedAgent()
        self.strategy_fusion = StrategyFusionAgent()
        self.debater = DebaterAgent()
        self.warden = WardenAgent()
        self.executor = ExecutorAgent()

        self.weight_manager = WeightManager()
        self.decision_logger = DecisionLogger()
        self.path_policy = CouncilPathPolicyManager()
        self.symbol_selector = SymbolSelectionManager()

        self._running = False
        self._last_decisions: Dict[str, CouncilDecision] = {}

    @property
    def last_decisions(self) -> Dict[str, CouncilDecision]:
        return self._last_decisions

    def _build_entry_context(self, symbol: str, decision: CouncilDecision) -> Dict[str, Any]:
        weights = self.weight_manager.weights
        agent_snapshot: Dict[str, Dict[str, Any]] = {}
        supporting_agents = []
        opposing_agents = []

        for name, signal in decision.agent_signals.items():
            agent_snapshot[name] = {
                "direction": signal.direction,
                "confidence": signal.confidence,
                "score": signal.score,
                "weight": weights.get(name, 0.0),
            }
            if signal.direction == decision.action:
                supporting_agents.append(name)
            elif signal.direction in {"LONG", "SHORT"}:
                opposing_agents.append(name)

        return {
            "symbol": symbol,
            "decision_action": decision.action,
            "decision_confidence": decision.confidence,
            "decision_weighted_score": decision.weighted_score,
            "supporting_agents": supporting_agents,
            "opposing_agents": opposing_agents,
            "agent_snapshot": agent_snapshot,
            "decision_timestamp": decision.timestamp,
        }

    def record_trade_outcome(self, closed_trade: Optional[Dict[str, Any]]) -> None:
        if not closed_trade:
            return

        pnl = float(closed_trade.get("pnl", 0.0) or 0.0)
        if pnl == 0.0:
            return

        metadata = closed_trade.get("metadata") or {}
        if not isinstance(metadata, dict):
            return

        agent_snapshot = metadata.get("agent_snapshot") or {}
        entry_direction = str(metadata.get("decision_action") or closed_trade.get("direction") or "").upper()
        if entry_direction not in {"LONG", "SHORT"} or not isinstance(agent_snapshot, dict):
            return

        trade_won = pnl > 0.0
        updates = 0
        for name, snapshot in agent_snapshot.items():
            if not isinstance(snapshot, dict):
                continue
            signal_direction = str(snapshot.get("direction") or "").upper()
            if signal_direction not in {"LONG", "SHORT"}:
                continue
            predicted_entry_direction = signal_direction == entry_direction
            correct = predicted_entry_direction == trade_won
            self.weight_manager.record_outcome(name, correct)
            updates += 1

        if updates:
            self.weight_manager.update_weights()
            logger.info("Recorded trade outcome for %s agents (pnl=%.2f)", updates, pnl)

    async def run_cycle(self, symbol: str) -> CouncilDecision:
        """Run a single council cycle for one symbol."""
        start = time.time()
        logger.info("=" * 50)
        logger.info("Council cycle for %s", symbol)
        logger.info("=" * 50)

        # Phase 1: Run core agents in parallel
        oracle_task = asyncio.create_task(self.oracle.run(symbol))
        sentinel_task = asyncio.create_task(self.sentinel.run(symbol))
        prophet_task = asyncio.create_task(self.prophet.run(symbol))
        arbiter_task = asyncio.create_task(self.arbiter.run(symbol))
        oracle_ext_task = asyncio.create_task(self.oracle_extended.run(symbol))
        strategy_fusion_task = asyncio.create_task(self.strategy_fusion.run(symbol))

        oracle_sig, sentinel_sig, prophet_sig, arbiter_sig, oracle_ext_sig, strategy_fusion_sig = await asyncio.gather(
            oracle_task, sentinel_task, prophet_task, arbiter_task, oracle_ext_task, strategy_fusion_task
        )

        # Phase 2: Feed signals to Debater
        other_signals = {
            "oracle": {
                "direction": oracle_sig.direction,
                "confidence": oracle_sig.confidence,
                "reasoning": oracle_sig.reasoning,
            },
            "sentinel": {
                "direction": sentinel_sig.direction,
                "confidence": sentinel_sig.confidence,
                "reasoning": sentinel_sig.reasoning,
            },
            "prophet": {
                "direction": prophet_sig.direction,
                "confidence": prophet_sig.confidence,
                "reasoning": prophet_sig.reasoning,
            },
            "arbiter": {
                "direction": arbiter_sig.direction,
                "confidence": arbiter_sig.confidence,
                "reasoning": arbiter_sig.reasoning,
            },
            "oracle_extended": {
                "direction": oracle_ext_sig.direction,
                "confidence": oracle_ext_sig.confidence,
                "reasoning": oracle_ext_sig.reasoning,
            },
            "strategy_fusion": {
                "direction": strategy_fusion_sig.direction,
                "confidence": strategy_fusion_sig.confidence,
                "reasoning": strategy_fusion_sig.reasoning,
            },
        }
        self.debater.set_other_signals(other_signals)
        debater_sig = await self.debater.run(symbol)

        # Phase 3: Warden veto check
        veto, veto_reason = await self.warden.check_veto(symbol)

        # Phase 4: Council vote
        signals: Dict[str, AgentSignal] = {
            "oracle": oracle_sig,
            "sentinel": sentinel_sig,
            "prophet": prophet_sig,
            "arbiter": arbiter_sig,
            "oracle_extended": oracle_ext_sig,
            "strategy_fusion": strategy_fusion_sig,
            "debater": debater_sig,
        }

        decision = vote(
            signals=signals,
            weight_manager=self.weight_manager,
            veto=veto,
            veto_reason=veto_reason,
            weight_overrides=self.path_policy.adjust_weights(self.weight_manager.weights),
        )
        decision = self.path_policy.enforce_decision(decision)

        self.decision_logger.log_decision(symbol, decision)
        self._last_decisions[symbol] = decision

        # Phase 5: Execute if decision says trade
        settings = get_settings()
        min_confidence = float(min(settings.min_confidence, settings.effective_min_confidence))
        if decision.should_trade and decision.confidence >= min_confidence:
            logger.info("Executing %s for %s (conf=%.2f)", decision.action, symbol, decision.confidence)
            entry_result = await self.executor.execute_entry(
                symbol=symbol,
                direction=decision.action,
                confidence=decision.confidence,
                decision_context=self._build_entry_context(symbol, decision),
            )
            execution_status = entry_result.get("status")
            execution_reason = entry_result.get("reason")
            self.record_trade_outcome(entry_result.get("closed_trade"))
            if execution_reason:
                logger.info(
                    "Execution result for %s: %s (%s)",
                    symbol,
                    execution_status,
                    execution_reason,
                )
                decision.reasoning += f" | Execution: {execution_status} ({execution_reason})"
            else:
                decision.reasoning += f" | Execution: {execution_status}"
        elif decision.should_trade:
            logger.info(
                "Skipping %s — confidence %.2f below min %.2f",
                symbol, decision.confidence, min_confidence,
            )
        else:
            logger.info("HOLD for %s — no trade", symbol)

        elapsed = time.time() - start
        logger.info("Council cycle for %s completed in %.2fs", symbol, elapsed)
        return decision

    async def run_all_symbols(self):
        """Run council cycle for all configured symbols."""
        settings = get_settings()
        active_symbols = self.symbol_selector.active_symbols(settings.trading_pairs)
        if not active_symbols:
            logger.warning("No active symbols qualified for council run")
            return
        tasks = [self.run_cycle(symbol) for symbol in active_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, result in zip(active_symbols, results):
            if isinstance(result, Exception):
                logger.exception("Council cycle failed for %s: %s", symbol, result)
            else:
                logger.info(
                    "Result for %s: %s (score=%.1f)",
                    symbol, result.action, result.weighted_score,
                )

    async def start(self):
        """Start the continuous council loop."""
        from config.constants import COUNCIL_CYCLE_SEC

        self._running = True
        logger.info("Council orchestrator started (cycle=%ds)", COUNCIL_CYCLE_SEC)

        while self._running:
            try:
                await self.run_all_symbols()
            except Exception as exc:
                logger.exception("Council loop error: %s", exc)
            await asyncio.sleep(COUNCIL_CYCLE_SEC)

    def stop(self):
        """Stop the council loop."""
        self._running = False
        logger.info("Council orchestrator stopped")


# ═══════════════════════════════════════════════════════════════
# TradingOrchestrator — full paper-trading wrapper
# ═══════════════════════════════════════════════════════════════

class TradingOrchestrator:
    """
    Production-grade wrapper around CouncilOrchestrator.
    • Owns the PaperTradingEngine
    • Writes live state to JSON every cycle (dashboard reads it)
    • Checks pending paper orders every cycle
    • Monitors positions for max-hold and daily-loss limits
    • Graceful shutdown on SIGINT / SIGTERM
    • Kill-switch support (dashboard can set it)
    """

    def __init__(self):
        from decimal import Decimal
        from execution.paper_engine import PaperTradingEngine
        from execution.position_tracker import PositionTracker
        from execution.trade_journal import TradeJournal
        from data.state_writer import StateWriter
        from data.binance_client import get_binance_client

        self.settings = get_settings()
        self.paper_engine = PaperTradingEngine(Decimal("10000"))
        self.position_tracker = PositionTracker()
        self.state_writer = StateWriter()
        self.binance = get_binance_client()
        self.journal = TradeJournal()

        # Build the council with our paper engine injected into executor
        self.council = CouncilOrchestrator()
        self.council.executor = ExecutorAgent(
            paper_engine=self.paper_engine,
            position_tracker=self.position_tracker,
            journal=self.journal,
        )
        self.symbol_selector = self.council.symbol_selector

        self._kill_switch = False
        self._cycle_count = 0
        self._start_time = time.time()
        self._prices: Dict[str, float] = {}
        self._agent_signals: Dict[str, Dict] = {}
        self._last_trade_count = 0  # track journaled trades
        self._execution_initial_balance: Optional[float] = None
        self._runtime_guard: Dict[str, object] = {
            "allowed": True,
            "status": "ok",
            "reasons": [],
            "metrics": {},
        }
        self._hydrate_execution_initial_balance()

    def _hydrate_execution_initial_balance(self):
        """Reload the persisted execution baseline so restarts preserve drawdown history."""
        if not self.settings.uses_binance_execution:
            return
        try:
            persisted = self.state_writer.read_state(self.settings.trading_mode)
        except Exception as exc:
            logger.debug("Execution baseline load failed: %s", exc)
            return
        if not isinstance(persisted, dict):
            return

        baseline = float(persisted.get("execution_baseline_balance") or 0.0)
        if baseline <= 0:
            initial_balance = float(persisted.get("initial_balance") or 0.0)
            equity = float(persisted.get("equity") or 0.0)
            cycle_count = int(persisted.get("cycle_count") or 0)
            total_return_pct = float(persisted.get("total_return_pct") or 0.0)
            has_persisted_history = (
                cycle_count > 0
                or abs(total_return_pct) > 1e-9
                or (initial_balance > 0 and equity > 0 and abs(initial_balance - equity) > 1e-6)
            )
            if has_persisted_history:
                baseline = initial_balance

        if baseline > 0:
            self._execution_initial_balance = baseline
            logger.info("Hydrated execution baseline: $%.2f", baseline)

    async def run(self):
        """Main loop — runs until killed."""
        import signal
        from config.constants import COUNCIL_CYCLE_SEC

        # Graceful shutdown on SIGINT (Ctrl+C) — only works from main thread
        def _shutdown(sig, frame):
            logger.info("Received signal %s — shutting down gracefully", sig)
            self._kill_switch = True

        try:
            signal.signal(signal.SIGINT, _shutdown)
        except ValueError:
            pass  # not main thread (e.g. QThread) — skip signal handler

        logger.info("=" * 60)
        logger.info(
            "PRADY TRADER - %s mode (%s spot execution)",
            self.settings.mode_label,
            self.settings.execution_environment.upper(),
        )
        logger.info("Pairs: %s", self.settings.trading_pairs)
        logger.info("Active pairs: %s", self._active_symbols())
        logger.info("Cycle interval: %ds", COUNCIL_CYCLE_SEC)
        if self.settings.is_paper:
            logger.info("Initial balance: $%s", self.paper_engine.balance)
        logger.info("=" * 60)

        while not self._kill_switch:
            self._cycle_count += 1
            cycle_start = time.time()
            logger.info("─── Cycle %d ───", self._cycle_count)

            try:
                # 1. Refresh prices for all symbols
                await self._refresh_prices()

                # 1.5 Reconcile exchange-held inventory into the in-memory tracker
                self._sync_execution_positions()

                # 2. Check pending paper orders against current prices
                self._check_pending_orders()

                # 3. Check position limits (max hold, daily loss)
                await self._check_position_limits()

                # 4. Evaluate runtime capital guard before opening any new risk
                trading_allowed = self._evaluate_runtime_guard()

                # 5. Run council for all symbols if capital guard allows it
                if trading_allowed:
                    for symbol in self._active_symbols():
                        if self._kill_switch:
                            break
                        try:
                            decision = await self.council.run_cycle(symbol)
                            # Collect agent signals from last decision for dashboard
                            if hasattr(decision, "agent_signals"):
                                self._agent_signals[symbol] = decision.agent_signals
                        except Exception as exc:
                            logger.exception("Council cycle failed for %s: %s", symbol, exc)
                else:
                    logger.warning(
                        "Capital guard paused new trades: %s",
                        "; ".join(str(reason) for reason in self._runtime_guard.get("reasons", [])),
                    )

                # 6. Write state for dashboard
                self._write_state()

                # 6.5 Persist new closed trades to PostgreSQL journal
                self._persist_new_trades()

                # 7. Log cycle summary
                if self.settings.is_paper:
                    stats = self.paper_engine.get_stats()
                    open_count = len(self.paper_engine.positions)
                    equity = float(self.paper_engine.get_equity(self._prices))
                else:
                    stats = self.position_tracker.get_stats()
                    open_count = self.position_tracker.position_count
                    try:
                        exec_info = self.binance.get_execution_account_info()
                        balance = float(exec_info.get("account_summary", {}).get("free_usdt", 0.0))
                        equity = float(exec_info.get("account_summary", {}).get("estimated_total_usdt", 0.0))
                    except Exception:
                        balance = 0.0
                        equity = 0.0
                elapsed = time.time() - cycle_start
                logger.info(
                    "Cycle %d done in %.1fs | Balance: $%.2f | Equity: $%.2f | "
                    "Open: %d | Trades: %d | Win: %.0f%%",
                    self._cycle_count, elapsed,
                    stats["balance"] if self.settings.is_paper else balance,
                    equity,
                    open_count,
                    stats["total_trades"],
                    stats.get("win_rate", 0) * 100,
                )

            except Exception as exc:
                logger.exception("Critical error in cycle %d: %s", self._cycle_count, exc)

            # Check kill switch file
            self._check_kill_switch_file()

            if not self._kill_switch:
                await asyncio.sleep(COUNCIL_CYCLE_SEC)

        # Shutdown
        logger.info("=" * 60)
        logger.info("SHUTDOWN — Writing final state")
        self._write_state()
        stats = self.paper_engine.get_stats() if self.settings.is_paper else self.position_tracker.get_stats()
        if self.settings.is_paper:
            final_balance = float(stats.get("balance", 0.0))
        else:
            try:
                exec_info = self.binance.get_execution_account_info()
                exec_summary = exec_info.get("account_summary", {})
                final_balance = float(exec_summary.get("free_usdt", 0.0))
            except Exception:
                final_balance = 0.0
        logger.info("Final balance: $%.2f", final_balance)
        logger.info("Total trades: %d", stats["total_trades"])
        logger.info("Win rate: %.0f%%", stats.get("win_rate", 0) * 100)
        logger.info("Total PnL: $%.2f", stats.get("total_pnl", 0))
        logger.info("=" * 60)

    def stop(self):
        """Request a graceful stop at the next safe point in the loop."""
        self._kill_switch = True

    async def _refresh_prices(self):
        """Fetch current prices for all trading pairs."""
        for symbol in self.settings.trading_pairs:
            try:
                ticker = self.binance.get_ticker_price(symbol)
                if isinstance(ticker, dict):
                    price = float(ticker.get("lastPrice", ticker.get("price", 0)))
                else:
                    price = float(ticker)
                if price > 0:
                    self._prices[symbol] = price
            except Exception as exc:
                logger.warning("Price fetch failed for %s: %s", symbol, exc)

    def _active_symbols(self) -> list[str]:
        return self.symbol_selector.active_symbols(self.settings.trading_pairs)

    def _check_pending_orders(self):
        """Check if any paper stop/limit orders should trigger."""
        if not self.settings.is_paper:
            return
        for symbol, price in self._prices.items():
            self.paper_engine.check_pending_orders(symbol, price)

    def _sync_execution_positions(self):
        """Keep the live/testnet tracker aligned with exchange-held spot inventory."""
        if not self.settings.uses_binance_execution:
            return
        try:
            sync_stats = self.council.executor.sync_exchange_positions()
        except Exception as exc:
            logger.warning("Execution inventory sync failed: %s", exc)
            return
        if sync_stats.get("adopted") or sync_stats.get("updated"):
            logger.info(
                "Execution inventory sync: adopted=%d updated=%d",
                sync_stats.get("adopted", 0),
                sync_stats.get("updated", 0),
            )

    def _evaluate_runtime_guard(self) -> bool:
        """Pause new trades when capital-preservation guardrails are breached."""
        rehearsal_summary = None
        if self.settings.is_paper:
            stats = self.paper_engine.get_stats()
            current_equity = float(self.paper_engine.get_equity(self._prices))
            baseline_equity = float(stats.get("initial_balance", current_equity) or current_equity)
            recent_closed_trades = self.paper_engine.get_trade_history(200)
        else:
            exec_info = self.binance.get_execution_account_info()
            summary = exec_info.get("account_summary", {}) if isinstance(exec_info, dict) else {}
            current_equity = float(summary.get("estimated_total_usdt") or summary.get("free_usdt") or 0.0)
            if self._execution_initial_balance is None and current_equity > 0:
                self._execution_initial_balance = current_equity
            baseline_equity = float(self._execution_initial_balance or current_equity or 0.0)
            recent_closed_trades = self.position_tracker.get_closed_trades(200)
            if self.settings.is_live:
                rehearsal_summary = load_rehearsal_summary(journal=self.journal)

        evaluation = evaluate_runtime_guard(
            self.settings,
            current_equity=current_equity,
            baseline_equity=baseline_equity,
            recent_closed_trades=recent_closed_trades,
            rehearsal_summary=rehearsal_summary,
        )
        self._runtime_guard = evaluation.to_dict()
        return evaluation.allowed

    async def _check_position_limits(self):
        """Close positions that exceed max hold time or daily loss limit."""
        max_hold = self.settings.max_hold_minutes
        if self.settings.is_paper:
            for symbol, pos in list(self.paper_engine.positions.items()):
                hold_minutes = (time.time() - pos.entry_time) / 60.0
                if hold_minutes > max_hold:
                    logger.warning(
                        "Position %s exceeded max hold (%d min > %d min) — closing",
                        symbol, int(hold_minutes), max_hold,
                    )
                    result = await self.council.executor.close_position(symbol, reason="time_exit")
                    self.council.record_trade_outcome(result.get("closed_trade"))

            stats = self.paper_engine.get_stats()
            initial = stats["initial_balance"]
            current = stats["balance"]
            if initial > 0:
                daily_loss_pct = (initial - current) / initial
                max_daily = float(self.settings.max_daily_loss)
                if daily_loss_pct >= max_daily:
                    logger.critical(
                        "DAILY LOSS LIMIT HIT: %.1f%% >= %.1f%% — activating kill switch",
                        daily_loss_pct * 100, max_daily * 100,
                    )
                    self._kill_switch = True
            return

        for symbol, pos in list(self.position_tracker.open_positions.items()):
            price = self._prices.get(symbol)
            if not price:
                continue
            hold_minutes = pos.holding_time_minutes()
            current_price = Decimal(str(price))
            if hold_minutes > max_hold:
                logger.warning(
                    "Live position %s exceeded max hold (%d min > %d min) — closing",
                    symbol, int(hold_minutes), max_hold,
                )
                result = await self.council.executor.close_position(symbol, reason="time_exit")
                self.council.record_trade_outcome(result.get("closed_trade"))
            elif pos.should_stop_loss(current_price):
                logger.warning("Live stop-loss hit for %s — closing", symbol)
                result = await self.council.executor.close_position(symbol, reason="stop_loss")
                self.council.record_trade_outcome(result.get("closed_trade"))
            elif pos.should_take_profit(current_price):
                logger.info("Live take-profit hit for %s — closing", symbol)
                result = await self.council.executor.close_position(symbol, reason="take_profit")
                self.council.record_trade_outcome(result.get("closed_trade"))

    def _write_state(self):
        """Build and write state JSON for dashboard."""
        state = self.state_writer.build_state(
            paper_engine=self.paper_engine,
            last_decisions=self.council.last_decisions,
            prices=self._prices,
            cycle_count=self._cycle_count,
            start_time=self._start_time,
            kill_switch=self._kill_switch,
            agent_signals=self._agent_signals,
        )
        state["trading_mode"] = self.settings.trading_mode
        state["execution_environment"] = self.settings.execution_environment
        state["runtime_guard"] = dict(self._runtime_guard)
        state["active_symbols"] = self._active_symbols()
        state["configured_symbols"] = list(self.settings.trading_pairs)

        if self.settings.uses_binance_execution:
            tracker_positions = []
            for symbol, pos in self.position_tracker.open_positions.items():
                current_price = Decimal(str(self._prices.get(symbol, float(pos.entry_price))))
                tracker_positions.append({
                    "symbol": symbol,
                    "direction": pos.direction,
                    "entry_price": float(pos.entry_price),
                    "current_price": float(current_price),
                    "quantity": float(pos.quantity),
                    "leverage": pos.leverage,
                    "pnl": float(pos.unrealised_pnl(current_price)),
                    "holding_minutes": pos.holding_time_minutes(),
                    "source": getattr(pos, "source", "internal"),
                })

            tracker_stats = self.position_tracker.get_stats()
            exec_info = self.binance.get_execution_account_info()
            execution_positions = exec_info.get("positions", []) if isinstance(exec_info, dict) else []
            exec_summary = exec_info.get("account_summary", {})
            balance = float(exec_summary.get("free_usdt", 0.0))
            equity = float(exec_summary.get("estimated_total_usdt", balance))
            if self._execution_initial_balance is None and equity > 0:
                self._execution_initial_balance = equity
            initial_balance = self._execution_initial_balance or equity or balance
            total_pnl = (equity - initial_balance) if initial_balance > 0 else 0.0
            total_return_pct = (
                ((equity - initial_balance) / initial_balance) * 100
                if initial_balance > 0
                else 0.0
            )
            if not tracker_positions:
                for raw in execution_positions:
                    symbol = str(raw.get("symbol") or "").strip().upper()
                    if not symbol:
                        continue
                    current_price = float(raw.get("markPrice") or self._prices.get(symbol, 0.0) or 0.0)
                    quantity = float(raw.get("positionAmt", 0.0) or 0.0)
                    if quantity <= 0:
                        continue
                    tracker_positions.append({
                        "symbol": symbol,
                        "direction": "LONG",
                        "entry_price": float(raw.get("entryPrice") or current_price),
                        "current_price": current_price,
                        "quantity": quantity,
                        "leverage": 1,
                        "pnl": 0.0,
                        "holding_minutes": 0.0,
                        "source": "execution_account",
                    })
            state.update({
                "balance": balance,
                "equity": equity,
                "initial_balance": initial_balance,
                "execution_baseline_balance": initial_balance,
                "total_return_pct": total_return_pct,
                "total_pnl": total_pnl,
                "daily_pnl": total_pnl,
                "realised_pnl": float(tracker_stats.get("total_pnl", 0.0)),
                "total_trades": tracker_stats.get("total_trades", 0),
                "win_rate": tracker_stats.get("win_rate", 0.0),
                "best_trade": tracker_stats.get("best_trade", 0.0),
                "worst_trade": tracker_stats.get("worst_trade", 0.0),
                "open_positions": tracker_positions,
                "closed_trades": self.position_tracker.get_closed_trades(100),
            })
        # Extract ensemble predictions from prophet agent metadata
        ensemble_preds = {}
        for sym, signals in self._agent_signals.items():
            prophet_sig = signals.get("prophet")
            if prophet_sig:
                meta = prophet_sig.metadata if hasattr(prophet_sig, "metadata") else (prophet_sig.get("metadata") if isinstance(prophet_sig, dict) else {})
                if meta and isinstance(meta, dict) and "probability" in meta:
                    ensemble_preds[sym] = {
                        "direction": meta.get("prediction", "—"),
                        "probability": meta.get("probability", 0.5),
                        "model_agreement": meta.get("model_agreement", 0),
                        "individual": meta.get("individual", {}),
                    }
        if ensemble_preds:
            state["ensemble_predictions"] = ensemble_preds
        # Add persistent journal stats if available
        try:
            journal_stats = self.journal.get_stats()
            if journal_stats.get("total_trades", 0) > 0:
                state["journal_stats"] = journal_stats
        except Exception:
            pass
        self.state_writer.write(state)

    def _persist_new_trades(self):
        """Record any new closed trades to the persistent PostgreSQL journal."""
        if not self.settings.is_paper:
            return
        history = self.paper_engine.get_trade_history(10_000)
        new_trades = history[self._last_trade_count:]
        for trade in new_trades:
            try:
                entry_price = trade.get("entry_price", 0.0)
                exit_price = trade.get("exit_price", 0.0)
                pnl = trade.get("pnl", 0.0)
                pnl_pct = (pnl / (entry_price * trade.get("quantity", 1.0)) * 100) if entry_price else 0.0

                trade_id = self.journal.record_entry(
                    symbol=trade["symbol"],
                    direction=trade["direction"],
                    entry_price=entry_price,
                    quantity=trade.get("quantity", 0.0),
                    paper=True,
                )
                self.journal.record_exit(
                    trade_id=trade_id,
                    exit_price=exit_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    exit_reason="paper_close",
                )
            except Exception as exc:
                logger.warning("Failed to journal trade: %s", exc)
        self._last_trade_count = len(history)

    def _check_kill_switch_file(self):
        """Check for a kill switch file written by dashboard or external process."""
        from config.settings import ROOT_DIR
        kill_file = ROOT_DIR / "data" / "kill_switch"
        if kill_file.exists():
            logger.warning("Kill switch file detected — shutting down")
            self._kill_switch = True
            kill_file.unlink(missing_ok=True)
