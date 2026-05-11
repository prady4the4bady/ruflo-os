from __future__ import annotations

import json

import numpy as np

from config.mode_policy import format_mode_policy_prompt, get_mode_policy
from utils.json_safe import SafeJSONEncoder


def test_get_mode_policy_for_live_mode():
    policy = get_mode_policy("live")

    assert policy["mode"] == "live"
    assert policy["capital_source"] == "Real Binance spot balances"
    assert "capital preservation" in policy["guardrail"].lower()


def test_format_mode_policy_prompt_includes_runtime_context():
    prompt = format_mode_policy_prompt("testnet")

    assert "CURRENT RUNTIME MODE: TESTNET" in prompt
    assert "Binance Spot Testnet" in prompt
    assert "Guardrail:" in prompt


def test_safe_json_encoder_handles_numpy_scalars():
    payload = {"flag": np.bool_(True), "score": np.float32(1.25)}
    rendered = json.dumps(payload, cls=SafeJSONEncoder)

    assert '"flag": true' in rendered
    assert '"score": 1.25' in rendered