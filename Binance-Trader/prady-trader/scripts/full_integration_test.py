#!/usr/bin/env python3
"""PRADY TRADER — Full integration test. Run all modules, detect issues."""
import sys, os, traceback

if "pytest" in sys.modules and __name__ != "__main__":
    import pytest

    pytest.skip("full_integration_test is a standalone smoke script", allow_module_level=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

errors = []
warnings = []
_APP = None


def ensure_app():
    global _APP
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"))
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication(sys.argv)
    return _APP

def test(name, fn):
    try:
        fn()
    except Exception as e:
        errors.append((name, str(e)))
        print(f"  [FAIL] {name}: {e}")

def warn(name, msg):
    warnings.append((name, msg))
    print(f"  [WARN] {name}: {msg}")

print("=" * 60)
print("  PRADY TRADER — Full Integration Test")
print("=" * 60)

# 1. Config
def t_config():
    from config.settings import get_settings
    s = get_settings()
    assert s.trading_mode in ("paper", "testnet", "live"), f"Bad mode: {s.trading_mode}"
    assert len(s.trading_pairs) > 0, "No trading pairs"
    print(f"  [OK] Config: mode={s.trading_mode}, pairs={len(s.trading_pairs)}")
test("Config", t_config)

# 2. Constants
def t_constants():
    from config.constants import AGENT_WEIGHTS
    assert len(AGENT_WEIGHTS) >= 6, f"Only {len(AGENT_WEIGHTS)} weights"
    print(f"  [OK] Constants: {len(AGENT_WEIGHTS)} agent weights")
test("Constants", t_constants)

# 3. Dashboard state
def t_dashboard():
    from dashboard.state import get_dashboard_state
    state = get_dashboard_state()
    assert state.balance > 0
    print(f"  [OK] Dashboard state: balance={state.balance}")
test("Dashboard", t_dashboard)

# 4. All agents import
def t_agents():
    from agents.oracle_agent import OracleAgent
    from agents.prophet_agent import ProphetAgent
    from agents.sentinel_agent import SentinelAgent
    from agents.arbiter_agent import ArbiterAgent
    from agents.debater_agent import DebaterAgent
    from agents.oracle_extended_agent import OracleExtendedAgent
    print("  [OK] All 6 agents import")
test("Agents", t_agents)

# 5. ML
def t_ml():
    from ml.ensemble import EnsemblePredictor
    print("  [OK] ML ensemble import")
test("ML", t_ml)

# 6. Indicators
def t_indicators():
    from indicators.composite import compute_composite_score
    from indicators.trend import compute_all_trend
    from indicators.momentum import compute_all_momentum
    print("  [OK] Indicators import (composite, trend, momentum)")
test("Indicators", t_indicators)

# 7. Orchestrator
def t_orchestrator():
    from council.orchestrator import TradingOrchestrator, CouncilOrchestrator
    print("  [OK] Orchestrator import")
test("Orchestrator", t_orchestrator)

# 8. Executor
def t_executor():
    from execution.paper_engine import PaperTradingEngine
    from execution.risk_manager import RiskManager
    from execution.position_tracker import PositionTracker
    print("  [OK] Executor imports (paper_engine, risk_manager, position_tracker)")
test("Executor", t_executor)

# 9. Desktop modules (headless)
def t_desktop():
    ensure_app()
    from desktop.widgets import MetricCard
    from desktop.theme import DARK_THEME
    from desktop.worker import DataWorker, OrchestratorWorker
    print("  [OK] Desktop core imports")
test("Desktop Core", t_desktop)

# 10. All pages
def t_pages():
    ensure_app()
    from desktop.pages.home import HomePage
    from desktop.pages.markets import MarketsPage
    from desktop.pages.trading import TradingPage
    from desktop.pages.agents import AgentsPage
    from desktop.pages.ledger import LedgerPage
    from desktop.pages.performance import PerformancePage
    from desktop.pages.health import HealthPage
    from desktop.pages.strategy import StrategyBuilderPage
    from desktop.pages.control import ControlRoomPage
    from desktop.pages.settings import SettingsPage
    # Instantiate each page
    pages = [
        HomePage(),
        MarketsPage(),
        TradingPage(),
        AgentsPage(),
        LedgerPage(),
        PerformancePage(),
        HealthPage(),
        StrategyBuilderPage(),
        ControlRoomPage(),
        SettingsPage(),
    ]
    print(f"  [OK] All 10 pages instantiated")
test("Pages", t_pages)

# 11. Page update_data with sample data
def t_page_update():
    ensure_app()
    from desktop.pages.home import HomePage
    from desktop.pages.markets import MarketsPage
    from desktop.pages.trading import TradingPage
    from desktop.pages.agents import AgentsPage
    from desktop.pages.ledger import LedgerPage
    from desktop.pages.performance import PerformancePage
    from desktop.pages.health import HealthPage
    from desktop.pages.strategy import StrategyBuilderPage
    from desktop.pages.control import ControlRoomPage
    from desktop.pages.settings import SettingsPage
    
    sample = {
        "system_running": False,
        "balance": 10000.0,
        "equity": 10000.0,
        "daily_pnl": 0.0,
        "total_pnl": 0.0,
        "total_trades": 0,
        "win_rate": 0.0,
        "best_trade": 0.0,
        "worst_trade": 0.0,
        "open_positions": [],
        "closed_trades": [],
        "last_decisions": {},
        "agent_signals": {},
        "agent_weights": {},
        "prices": {"BTCUSDT": 74000.0, "ETHUSDT": 2300.0},
        "cycle_count": 0,
        "initial_balance": 10000.0,
        "total_return_pct": 0.0,
        "uptime_seconds": 0,
        "uptime_str": "0h 0m 0s",
        "market_overview": {},
        "fear_greed": {},
        "news": [],
        "trending": [],
        "kill_switch": False,
        "model_info": {},
        "ensemble_predictions": {},
        "mode_snapshots": {},
        "mode_policies": {},
        "active_mode_policy": {},
        "mode_summaries": {},
        "mode_account_views": {},
        "provider_statuses": {},
        "rate_limiter_stats": {},
        "journal_stats": {},
        "health_data": {},
        "process_data": {},
        "decision_log": [],
        "agent_activity": [],
        "binance_account": {},
        "binance_accounts": {},
    }
    for PageCls in [
        HomePage,
        MarketsPage,
        TradingPage,
        AgentsPage,
        LedgerPage,
        PerformancePage,
        HealthPage,
        StrategyBuilderPage,
        ControlRoomPage,
        SettingsPage,
    ]:
        page = PageCls()
        page.update_data(sample)
    print("  [OK] All pages update_data() with sample data")
test("Page Updates", t_page_update)

# 12. MainWindow construction
def t_mainwindow():
    ensure_app()
    from desktop.app import MainWindow
    win = MainWindow()
    print("  [OK] MainWindow constructed")
    win.close()
    win.deleteLater()
test("MainWindow", t_mainwindow)

# 13. Orchestrator creates in thread context
def t_orch_create():
    from council.orchestrator import TradingOrchestrator
    orch = TradingOrchestrator()
    assert orch is not None
    print("  [OK] TradingOrchestrator created")
test("Orch Create", t_orch_create)

# 14. Async orchestrator run (1 cycle with kill)
def t_orch_run():
    import asyncio
    from council.orchestrator import TradingOrchestrator
    orch = TradingOrchestrator()
    
    async def run_one():
        async def auto_kill():
            await asyncio.sleep(20)
            orch._kill_switch = True
        asyncio.create_task(auto_kill())
        await orch.run()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_one())
        print("  [OK] Orchestrator ran 1 cycle and stopped")
    finally:
        loop.close()
test("Orch Run", t_orch_run)

# 15. Training coverage audit
def t_training_coverage():
    from config.settings import get_settings
    from ml.model_store import get_latest_model_path

    missing = {}
    for symbol in get_settings().trading_pairs:
        gaps = [name for name in ("lstm", "xgboost", "tft") if get_latest_model_path(name, symbol) is None]
        if gaps:
            missing[symbol] = gaps

    if missing:
        warn("Training Coverage", "; ".join(f"{symbol}: {', '.join(gaps)}" for symbol, gaps in missing.items()))
    else:
        print("  [OK] Training coverage: all configured pairs have lstm/xgboost/tft artifacts")
test("Training Coverage", t_training_coverage)

# 16. Docker services check
def t_docker():
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        warn("Docker", f"docker ps unavailable within 20s: {exc}")
        return

    containers = result.stdout.strip().split("\n") if result.stdout.strip() else []
    expected = {"prady-postgres", "prady-redis", "prady-ollama"}
    running = set(containers)
    missing = expected - running
    if missing:
        warn("Docker", f"Missing containers: {sorted(missing)}")
    else:
        print(f"  [OK] Docker: all 3 containers running")
test("Docker", t_docker)

# Summary
print("\n" + "=" * 60)
if errors:
    print(f"  FAILED: {len(errors)} error(s)")
    for name, msg in errors:
        print(f"    ✗ {name}: {msg}")
else:
    print("  ALL TESTS PASSED")

if warnings:
    print(f"  WARNINGS: {len(warnings)}")
    for name, msg in warnings:
        print(f"    ⚠ {name}: {msg}")

print("=" * 60)
sys.exit(1 if errors else 0)
