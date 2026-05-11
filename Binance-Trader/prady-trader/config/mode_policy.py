from __future__ import annotations

from typing import Any, Dict

MODE_POLICIES: Dict[str, Dict[str, str]] = {
    "paper": {
        "title": "Paper Practice",
        "purpose": "Rehearse strategy logic with simulated capital and internal fills before touching any exchange account.",
        "capital_source": "Simulated ledger only",
        "execution_model": "Internal paper engine",
        "result_label": "Practice PnL",
        "primary_goal": "Improve timing, coin selection, and process quality without financial risk.",
        "guardrail": "Do not treat paper gains as proof of live readiness or as spendable capital.",
    },
    "testnet": {
        "title": "Testnet Rehearsal",
        "purpose": "Exercise real exchange workflows on Binance Spot Testnet with zero-risk balances and exchange-side order routing.",
        "capital_source": "Binance Spot Testnet balances",
        "execution_model": "Binance Spot Testnet",
        "result_label": "Dress-rehearsal PnL",
        "primary_goal": "Validate execution timing, order placement, and operational safety on real exchange plumbing.",
        "guardrail": "Do not use live-account wealth to justify testnet trades; testnet is rehearsal, not wealth generation.",
    },
    "live": {
        "title": "Live Capital",
        "purpose": "Trade the real Binance account where every order affects actual holdings and account growth.",
        "capital_source": "Real Binance spot balances",
        "execution_model": "Binance Spot Mainnet",
        "result_label": "Realized capital performance",
        "primary_goal": "Grow and protect real capital with disciplined timing, symbol selection, and risk control.",
        "guardrail": "Capital preservation outranks experimentation; only high-conviction, fully-audited trades belong here.",
    },
}


def get_mode_policy(mode: str | None = None) -> Dict[str, Any]:
    if mode is None:
        from config.settings import get_settings

        mode = get_settings().trading_mode

    normalized = str(mode or "paper").strip().lower()
    if normalized not in MODE_POLICIES:
        normalized = "paper"

    return {"mode": normalized, **MODE_POLICIES[normalized]}


def get_all_mode_policies() -> Dict[str, Dict[str, Any]]:
    return {mode: get_mode_policy(mode) for mode in MODE_POLICIES}


def format_mode_policy_prompt(mode: str | None = None) -> str:
    policy = get_mode_policy(mode)
    return (
        f"CURRENT RUNTIME MODE: {policy['mode'].upper()} ({policy['title']})\n"
        f"- Purpose: {policy['purpose']}\n"
        f"- Capital source: {policy['capital_source']}\n"
        f"- Execution model: {policy['execution_model']}\n"
        f"- Goal: {policy['primary_goal']}\n"
        f"- Guardrail: {policy['guardrail']}"
    )