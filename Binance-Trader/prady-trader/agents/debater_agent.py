"""
PRADY TRADER — Debater Agent (weight: 0.10).
Uses local Ollama first and falls back to NVIDIA NIM for contrarian
trade-thesis analysis before dropping to a rule-based debater.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict

from agents.base_agent import BaseAgent, AgentSignal
from config.constants import AGENT_WEIGHTS
from config.mode_policy import format_mode_policy_prompt
from config.settings import get_settings
from utils.provider_status import (
    is_provider_suppressed,
    load_provider_statuses,
    mark_provider_disabled,
    mark_provider_failure,
    mark_provider_success,
    recommended_suppression_seconds,
    should_emit_runtime_warning,
    suppress_provider,
)

logger = logging.getLogger("prady.agents.debater")

DEBATER_MAX_TIMEOUT_SEC = 8


def _reasoning_timeout_sec() -> int:
    """Cap LLM wait time so one unavailable provider cannot stall a full trading cycle."""
    configured = int(getattr(get_settings(), "ollama_timeout_sec", DEBATER_MAX_TIMEOUT_SEC) or 0)
    return max(3, min(configured, DEBATER_MAX_TIMEOUT_SEC))


def _reasoning_warning(provider: str, message: str, exc: Exception | None = None) -> None:
    settings = get_settings()
    cooldown = int(getattr(settings, "provider_warning_cooldown_sec", 300) or 300)
    startup_grace = int(getattr(settings, "provider_startup_grace_sec", 180) or 180)
    if should_emit_runtime_warning(
        provider,
        cooldown_sec=cooldown,
        startup_grace_sec=startup_grace,
        warn_after_failures=2,
    ):
        if exc is None:
            logger.warning("%s", message)
        else:
            logger.warning("%s: %s", message, exc)
    else:
        if exc is None:
            logger.debug("%s", message)
        else:
            logger.debug("%s: %s", message, exc)


def _reasoning_suppressed(provider: str) -> bool:
    if not is_provider_suppressed(provider):
        return False
    logger.debug("%s temporarily suppressed after recent failures", provider)
    return True


def _maybe_suppress_reasoning_provider(
    provider: str,
    message: str,
    failures: int,
    *,
    details: Dict[str, Any],
) -> None:
    cooldown = int(getattr(get_settings(), "provider_warning_cooldown_sec", 300) or 300)
    backoff = recommended_suppression_seconds(message, default_cooldown=cooldown)
    lowered = str(message or "").lower()
    if "could not contact dns servers" in lowered or "name resolution" in lowered:
        backoff = max(backoff, 3600)
    elif "timeout on reading data from socket" in lowered or "timed out" in lowered:
        backoff = max(backoff, 1800)
    threshold = 1 if backoff >= 3600 else 2
    if backoff > 0 and failures >= threshold:
        suppress_provider(
            provider,
            f"Temporarily suppressing {provider} after repeated failures",
            cooldown_sec=backoff,
            category="reasoning",
            configured=True,
            optional=True,
            details={**details, "error": message},
        )


def _reasoning_backend_context() -> Dict[str, Dict[str, str]]:
    statuses = load_provider_statuses()
    context: Dict[str, Dict[str, str]] = {}
    for key, label in (("ollama", "Ollama"), ("nvidia_nim", "NVIDIA NIM")):
        record = statuses.get(key) or {}
        context[key] = {
            "provider": label,
            "status": str(record.get("status", "unknown") or "unknown"),
            "message": str(record.get("last_error") or record.get("message") or "").strip(),
        }
    return context


def _reasoning_backend_note(context: Dict[str, Dict[str, str]]) -> str:
    fragments = []
    for key in ("ollama", "nvidia_nim"):
        entry = context.get(key) or {}
        status = entry.get("status", "unknown")
        message = entry.get("message", "")
        if status == "healthy":
            continue

        fragment = f"{entry.get('provider', key)} {status}"
        if message:
            fragment += f" ({message[:120]})"
        fragments.append(fragment)

    return "; ".join(fragments)


async def _query_ollama(prompt: str, model: str, host: str) -> str:
    """Send prompt to local Ollama instance and return response text."""
    import aiohttp

    if not bool(getattr(get_settings(), "enable_ollama_reasoning", True)):
        mark_provider_disabled(
            "Ollama",
            "Disabled in settings",
            category="reasoning",
            configured=False,
            optional=True,
            details={"flag": "enable_ollama_reasoning"},
        )
        return ""
    if _reasoning_suppressed("Ollama"):
        return ""

    url = f"{host.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 512,
        },
    }
    timeout_sec = _reasoning_timeout_sec()
    try:
        timeout = aiohttp.ClientTimeout(
            total=timeout_sec,
            connect=min(2, timeout_sec),
            sock_connect=min(2, timeout_sec),
            sock_read=timeout_sec,
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    record = mark_provider_failure(
                        "Ollama",
                        f"HTTP {resp.status}",
                        category="reasoning",
                        configured=True,
                        optional=True,
                        details={"model": model, "body": body[:200]},
                    )
                    _maybe_suppress_reasoning_provider(
                        "Ollama",
                        f"HTTP {resp.status}: {body[:200]}",
                        int(record.get("consecutive_failures", 0) or 0),
                        details={"model": model, "host": host},
                    )
                    _reasoning_warning("Ollama", f"Ollama returned {resp.status}: {body[:200]}")
                    return ""
                data = await resp.json()
                response = str(data.get("response", "")).strip()
                if not response:
                    record = mark_provider_failure(
                        "Ollama",
                        "Empty response",
                        category="reasoning",
                        configured=True,
                        optional=True,
                        details={"model": model, "host": host},
                    )
                    _maybe_suppress_reasoning_provider(
                        "Ollama",
                        "Empty response",
                        int(record.get("consecutive_failures", 0) or 0),
                        details={"model": model, "host": host},
                    )
                    _reasoning_warning("Ollama", "Ollama returned an empty reasoning response")
                    return ""
                if response:
                    mark_provider_success(
                        "Ollama",
                        "Reasoning response healthy",
                        category="reasoning",
                        configured=True,
                        optional=True,
                        details={"model": model},
                    )
                return response
    except Exception as exc:
        record = mark_provider_failure(
            "Ollama",
            str(exc),
            category="reasoning",
            configured=True,
            optional=True,
            details={"model": model, "host": host},
        )
        _maybe_suppress_reasoning_provider(
            "Ollama",
            str(exc),
            int(record.get("consecutive_failures", 0) or 0),
            details={"model": model, "host": host},
        )
        _reasoning_warning("Ollama", "Ollama query failed", exc)
        return ""


async def _query_nvidia_nim(prompt: str, model: str, base_url: str, api_key: str) -> str:
    """Send prompt to NVIDIA NIM's OpenAI-compatible chat endpoint."""
    if not bool(getattr(get_settings(), "enable_nvidia_nim_reasoning", True)):
        mark_provider_disabled(
            "NVIDIA NIM",
            "Disabled in settings",
            category="reasoning",
            configured=False,
            optional=True,
            details={"flag": "enable_nvidia_nim_reasoning"},
        )
        return ""
    if not api_key:
        mark_provider_disabled(
            "NVIDIA NIM",
            "API key not configured",
            category="reasoning",
            configured=False,
            optional=True,
            details={"setting": "nvidia_nim_api_key"},
        )
        return ""
    if _reasoning_suppressed("NVIDIA NIM"):
        return ""

    import aiohttp

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise crypto-trading debate assistant. Respond with valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 512,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout_sec = _reasoning_timeout_sec()

    try:
        timeout = aiohttp.ClientTimeout(
            total=timeout_sec,
            connect=min(2, timeout_sec),
            sock_connect=min(2, timeout_sec),
            sock_read=timeout_sec,
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    record = mark_provider_failure(
                        "NVIDIA NIM",
                        f"HTTP {resp.status}",
                        category="reasoning",
                        configured=True,
                        optional=True,
                        details={"model": model, "body": body[:200]},
                    )
                    _maybe_suppress_reasoning_provider(
                        "NVIDIA NIM",
                        f"HTTP {resp.status}: {body[:200]}",
                        int(record.get("consecutive_failures", 0) or 0),
                        details={"model": model, "base_url": base_url},
                    )
                    _reasoning_warning("NVIDIA NIM", f"NVIDIA NIM returned {resp.status}: {body[:200]}")
                    return ""

                data = await resp.json()
                choices = data.get("choices") or []
                if not choices:
                    record = mark_provider_failure(
                        "NVIDIA NIM",
                        "No choices in response",
                        category="reasoning",
                        configured=True,
                        optional=True,
                        details={"model": model},
                    )
                    _maybe_suppress_reasoning_provider(
                        "NVIDIA NIM",
                        "No choices in response",
                        int(record.get("consecutive_failures", 0) or 0),
                        details={"model": model, "base_url": base_url},
                    )
                    _reasoning_warning("NVIDIA NIM", "NVIDIA NIM returned no choices")
                    return ""

                message = choices[0].get("message") or {}
                response = str(message.get("content", "")).strip()
                if not response:
                    record = mark_provider_failure(
                        "NVIDIA NIM",
                        "Empty response",
                        category="reasoning",
                        configured=True,
                        optional=True,
                        details={"model": model, "base_url": base_url},
                    )
                    _maybe_suppress_reasoning_provider(
                        "NVIDIA NIM",
                        "Empty response",
                        int(record.get("consecutive_failures", 0) or 0),
                        details={"model": model, "base_url": base_url},
                    )
                    _reasoning_warning("NVIDIA NIM", "NVIDIA NIM returned an empty reasoning response")
                    return ""
                if response:
                    mark_provider_success(
                        "NVIDIA NIM",
                        "Reasoning response healthy",
                        category="reasoning",
                        configured=True,
                        optional=True,
                        details={"model": model},
                    )
                return response
    except Exception as exc:
        record = mark_provider_failure(
            "NVIDIA NIM",
            str(exc),
            category="reasoning",
            configured=True,
            optional=True,
            details={"model": model, "base_url": base_url},
        )
        _maybe_suppress_reasoning_provider(
            "NVIDIA NIM",
            str(exc),
            int(record.get("consecutive_failures", 0) or 0),
            details={"model": model, "base_url": base_url},
        )
        _reasoning_warning("NVIDIA NIM", "NVIDIA NIM query failed", exc)
        return ""


async def _query_reasoning_model(prompt: str) -> tuple[str, str]:
    """Try Ollama first, then NVIDIA NIM, then return empty for rule fallback."""
    settings = get_settings()

    response = await _query_ollama(prompt, settings.ollama_model, settings.ollama_host)
    if response:
        return response, "ollama"

    if settings.nvidia_nim_api_key:
        response = await _query_nvidia_nim(
            prompt,
            settings.nvidia_nim_model,
            settings.nvidia_nim_base_url,
            settings.nvidia_nim_api_key,
        )
        if response:
            return response, "nvidia_nim"

    return "", ""


def _build_debate_prompt(symbol: str, signals: Dict[str, Any]) -> str:
    """Build a structured prompt for the LLM debater."""
    signal_text = "\n".join(
        f"- {name}: direction={s.get('direction', '?')}, "
        f"confidence={s.get('confidence', 0):.2f}, "
        f"reasoning={s.get('reasoning', 'N/A')}"
        for name, s in signals.items()
    )
    mode_context = format_mode_policy_prompt()

    return f"""You are an expert crypto trader performing adversarial analysis.

{mode_context}

SYMBOL: {symbol}
CURRENT AGENT SIGNALS:
{signal_text}

TASK:
1. Identify the majority consensus direction.
2. Present the STRONGEST counter-arguments against this trade.
3. Evaluate whether the counter-arguments are strong enough to invalidate the thesis.
4. Give a final verdict: AGREE or DISAGREE with the consensus.
5. Rate your conviction (0.0 to 1.0) that the consensus trade will succeed.

RUNTIME RULES:
- Keep your reasoning scoped to the current runtime mode.
- If the runtime mode is PAPER or TESTNET, judge the trade as rehearsal quality, not as live wealth generation.
- If the runtime mode is LIVE, favor capital protection and execution quality over experimentation.

Respond in this exact JSON format:
{{"consensus_direction": "LONG or SHORT", "counter_arguments": ["arg1", "arg2"], "verdict": "AGREE or DISAGREE", "conviction": 0.75, "summary": "one sentence"}}
"""


def _parse_llm_response(text: str) -> Dict[str, Any]:
    """Parse the LLM response JSON. Fall back to neutral on failure."""
    text = text.strip()
    # Try to find JSON block
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError as exc:
            logger.warning(
                "Failed to parse LLM JSON (%d chars): %.200s — %s",
                len(text), text, exc,
            )
    return {
        "consensus_direction": "NEUTRAL",
        "counter_arguments": [],
        "verdict": "NEUTRAL",
        "conviction": 0.5,
        "summary": "Failed to parse LLM response",
    }


def _normalize_llm_response_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize LLM output so malformed payloads degrade gracefully."""
    consensus_dir = str(parsed.get("consensus_direction", "NEUTRAL") or "NEUTRAL").upper()
    if consensus_dir not in {"LONG", "SHORT"}:
        consensus_dir = "NEUTRAL"

    verdict = str(parsed.get("verdict", "NEUTRAL") or "NEUTRAL").upper()
    if verdict not in {"AGREE", "DISAGREE"}:
        verdict = "NEUTRAL"

    try:
        conviction = float(parsed.get("conviction", 0.5))
    except (TypeError, ValueError):
        conviction = 0.5
    if not math.isfinite(conviction):
        conviction = 0.5
    conviction = max(0.0, min(1.0, conviction))

    raw_counter_args = parsed.get("counter_arguments", [])
    if isinstance(raw_counter_args, str):
        counter_args = [raw_counter_args.strip()] if raw_counter_args.strip() else []
    elif isinstance(raw_counter_args, list):
        counter_args = [str(item).strip() for item in raw_counter_args if str(item).strip()]
    else:
        counter_args = []

    summary = str(parsed.get("summary", "No summary") or "No summary").strip() or "No summary"

    return {
        "consensus_direction": consensus_dir,
        "counter_arguments": counter_args,
        "verdict": verdict,
        "conviction": conviction,
        "summary": summary,
    }


class DebaterAgent(BaseAgent):
    """
    LLM-powered contrarian debater.
    Challenges the consensus to avoid groupthink.
    """

    def __init__(self):
        super().__init__(name="debater", weight=AGENT_WEIGHTS["debater"])
        self._other_signals: Dict[str, Dict[str, Any]] = {}

    def set_other_signals(self, signals: Dict[str, Dict[str, Any]]):
        """Inject signals from other agents for the debate context."""
        self._other_signals = signals

    def _rule_based_fallback(
        self, symbol: str, signals: Dict[str, Dict[str, Any]]
    ) -> AgentSignal:
        """Contrarian analysis without LLM — counts consensus and pushes back."""
        long_votes = 0
        short_votes = 0
        total_conf = 0.0

        for name, s in signals.items():
            d = s.get("direction", "NEUTRAL").upper()
            c = float(s.get("confidence", 0))
            if d == "LONG":
                long_votes += 1
                total_conf += c
            elif d == "SHORT":
                short_votes += 1
                total_conf += c

        n = max(len(signals), 1)
        avg_conf = total_conf / n

        # Strong consensus → mild disagreement; weak consensus → agreement
        if long_votes > short_votes:
            consensus_dir = "LONG"
        elif short_votes > long_votes:
            consensus_dir = "SHORT"
        else:
            return AgentSignal(
                agent_name=self.name,
                direction="NEUTRAL",
                confidence=0.2,
                score=0.0,
                reasoning="Rule-based: no clear consensus to challenge",
            )

        unanimity = abs(long_votes - short_votes) / n
        if unanimity > 0.7 and avg_conf > 0.6:
            # Strong consensus — contrarian pushback
            flip = "SHORT" if consensus_dir == "LONG" else "LONG"
            score = 25.0 if flip == "LONG" else -25.0
            return AgentSignal(
                agent_name=self.name,
                direction=flip,
                confidence=round(0.3 + unanimity * 0.2, 4),
                score=round(score, 2),
                reasoning=(
                    f"Rule-based contrarian: strong {consensus_dir} consensus "
                    f"(unanimity={unanimity:.0%}, avg_conf={avg_conf:.2f}) "
                    f"— mild pushback toward {flip}"
                ),
            )

        # Weak consensus — agree
        score = 20.0 if consensus_dir == "LONG" else -20.0
        return AgentSignal(
            agent_name=self.name,
            direction=consensus_dir,
            confidence=round(0.2 + avg_conf * 0.3, 4),
            score=round(score, 2),
            reasoning=(
                f"Rule-based: weak {consensus_dir} consensus "
                f"(unanimity={unanimity:.0%}, avg_conf={avg_conf:.2f}) — agreeing"
            ),
        )

    async def analyze(self, symbol: str) -> AgentSignal:
        if not self._other_signals:
            return AgentSignal(
                agent_name=self.name,
                direction="NEUTRAL",
                confidence=0.0,
                score=0.0,
                reasoning="No other agent signals provided for debate",
            )

        prompt = _build_debate_prompt(symbol, self._other_signals)
        response_text, provider = await _query_reasoning_model(prompt)

        if not response_text:
            # No LLM backend available — use rule-based contrarian analysis
            signal = self._rule_based_fallback(symbol, self._other_signals)
            backend_context = _reasoning_backend_context()
            backend_note = _reasoning_backend_note(backend_context)
            if backend_note:
                signal.reasoning = f"{signal.reasoning}. Fallback active because {backend_note}"
            signal.metadata.update(
                {
                    "llm_provider": "rule_based",
                    "llm_fallback_used": True,
                    "reasoning_backends": backend_context,
                }
            )
            return signal

        try:
            parsed = _normalize_llm_response_payload(_parse_llm_response(response_text))
        except Exception as exc:
            signal = self._rule_based_fallback(symbol, self._other_signals)
            backend_context = _reasoning_backend_context()
            signal.reasoning = (
                f"{signal.reasoning}. LLM parse fallback because {type(exc).__name__}: {exc}"
            )
            signal.metadata.update(
                {
                    "llm_provider": "rule_based",
                    "llm_fallback_used": True,
                    "llm_runtime_error": str(exc),
                    "reasoning_backends": backend_context,
                }
            )
            return signal

        verdict = parsed["verdict"]
        conviction = parsed["conviction"]
        consensus_dir = parsed["consensus_direction"]
        summary = parsed["summary"]
        counter_args = parsed["counter_arguments"]

        if verdict == "AGREE":
            direction = consensus_dir if consensus_dir in ("LONG", "SHORT") else "NEUTRAL"
            score = conviction * 50.0 if direction == "LONG" else -conviction * 50.0
        elif verdict == "DISAGREE":
            # Flip direction
            if consensus_dir == "LONG":
                direction = "SHORT"
                score = -conviction * 50.0
            elif consensus_dir == "SHORT":
                direction = "LONG"
                score = conviction * 50.0
            else:
                direction = "NEUTRAL"
                score = 0.0
        else:
            direction = "NEUTRAL"
            score = 0.0

        confidence = conviction * 0.8  # debater is less certain by nature

        counter_str = "; ".join(counter_args[:3]) if counter_args else "none"
        provider_label = "NVIDIA NIM fallback" if provider == "nvidia_nim" else "Ollama"
        reasoning = (
            f"{provider_label} verdict: {verdict} (conviction={conviction:.2f}). "
            f"Counter-args: [{counter_str}]. {summary}"
        )

        metadata = dict(parsed)
        metadata["llm_provider"] = provider
        metadata["llm_fallback_used"] = provider == "nvidia_nim"

        return AgentSignal(
            agent_name=self.name,
            direction=direction,
            confidence=round(confidence, 4),
            score=round(score, 2),
            reasoning=reasoning,
            metadata=metadata,
        )
