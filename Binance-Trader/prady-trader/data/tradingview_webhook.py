"""
PRADY TRADER — TradingView Webhook Receiver.

FastAPI server that receives TradingView alert webhooks, validates them via
HMAC secret, stores signals in Redis (or in-memory queue), and exposes a
TVSignalReader for agents to consume the latest signals.

Usage:
    python -m data.tradingview_webhook          # start server on port 8080
    from data.tradingview_webhook import TVSignalReader
    reader = TVSignalReader()
    signals = await reader.get_recent_signals("BTCUSDT", max_age_sec=300)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("prady.data.tv_webhook")

# ═══════════════════════════════════════════════════════════════
# TVSignal dataclass
# ═══════════════════════════════════════════════════════════════


@dataclass
class TVSignal:
    """Parsed TradingView webhook signal."""

    symbol: str
    action: str          # "BUY", "SELL", "LONG", "SHORT", "CLOSE"
    price: float = 0.0
    timeframe: str = ""  # "1m", "5m", "1h", "4h", "1d"
    indicator: str = ""  # "RSI", "MACD", "EMA Cross", etc.
    message: str = ""
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "price": self.price,
            "timeframe": self.timeframe,
            "indicator": self.indicator,
            "message": self.message,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TVSignal":
        return cls(
            symbol=d.get("symbol", "BTCUSDT"),
            action=d.get("action", "").upper(),
            price=float(d.get("price", 0)),
            timeframe=d.get("timeframe", ""),
            indicator=d.get("indicator", ""),
            message=d.get("message", ""),
            confidence=float(d.get("confidence", 0.5)),
            timestamp=float(d.get("timestamp", time.time())),
        )


# ═══════════════════════════════════════════════════════════════
# Signal Store (Redis + in-memory fallback)
# ═══════════════════════════════════════════════════════════════

_MEM_SIGNALS: List[Dict[str, Any]] = []
_MAX_MEM_SIGNALS = 500


async def _store_signal(signal: TVSignal) -> None:
    """Store signal in Redis list (and in-memory for fallback)."""
    payload = json.dumps(signal.to_dict(), default=str)

    # In-memory always
    _MEM_SIGNALS.append(signal.to_dict())
    if len(_MEM_SIGNALS) > _MAX_MEM_SIGNALS:
        del _MEM_SIGNALS[: len(_MEM_SIGNALS) - _MAX_MEM_SIGNALS]

    # Redis if available
    try:
        from config.settings import get_settings
        url = get_settings().redis_url
        if url:
            import redis as _redis
            r = _redis.from_url(url, decode_responses=True)
            r.lpush("tv_signals", payload)
            r.ltrim("tv_signals", 0, _MAX_MEM_SIGNALS - 1)
            r.expire("tv_signals", 3600)  # 1 hour TTL
    except Exception as exc:
        logger.debug("Redis signal store failed: %s", exc)


def _verify_secret(body: bytes, secret: str, received_sig: str) -> bool:
    """Verify HMAC-SHA256 signature from TradingView webhook."""
    if not secret:
        return True  # no secret configured = accept all
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_sig)


# ═══════════════════════════════════════════════════════════════
# FastAPI Webhook Server
# ═══════════════════════════════════════════════════════════════


def create_webhook_app():
    """Create and return the FastAPI app for TradingView webhooks."""
    from fastapi import FastAPI, Request, HTTPException

    app = FastAPI(title="PRADY TRADER — TradingView Webhook", version="3.0")

    @app.post("/webhook")
    async def receive_webhook(request: Request):
        """Receive and validate a TradingView webhook alert."""
        from config.settings import get_settings

        body = await request.body()
        secret = getattr(get_settings(), 'tradingview_webhook_secret', '')

        # Verify HMAC if secret is configured
        sig = request.headers.get("X-TV-Signature", "")
        if secret and not _verify_secret(body, secret, sig):
            logger.warning("Invalid webhook signature — rejecting")
            raise HTTPException(status_code=403, detail="Invalid signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        # Parse signal
        signal = TVSignal.from_dict(payload)

        # Validate required fields
        if not signal.symbol or not signal.action:
            raise HTTPException(
                status_code=400, detail="Missing 'symbol' or 'action'"
            )

        if signal.action not in ("BUY", "SELL", "LONG", "SHORT", "CLOSE"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action: {signal.action}",
            )

        await _store_signal(signal)
        logger.info(
            "TV Signal received: %s %s @ %.2f [%s/%s]",
            signal.action, signal.symbol, signal.price,
            signal.indicator, signal.timeframe,
        )
        return {"status": "ok", "signal": signal.to_dict()}

    @app.get("/health")
    async def health():
        return {"status": "healthy", "signals_in_memory": len(_MEM_SIGNALS)}

    @app.get("/signals")
    async def list_signals(symbol: str = "", limit: int = 20):
        """List recent signals, optionally filtered by symbol."""
        signals = _MEM_SIGNALS[-limit:]
        if symbol:
            signals = [s for s in signals if s.get("symbol") == symbol.upper()]
        return {"signals": signals}

    return app


# ═══════════════════════════════════════════════════════════════
# TVSignalReader — for agents to consume signals
# ═══════════════════════════════════════════════════════════════


class TVSignalReader:
    """Read TradingView signals from Redis or in-memory store.
    Used by OracleExtendedAgent and others."""

    async def get_recent_signals(
        self, symbol: str = "", max_age_sec: int = 300
    ) -> List[TVSignal]:
        """Get recent TV signals, optionally filtered by symbol."""
        cutoff = time.time() - max_age_sec
        signals: List[TVSignal] = []

        # Try Redis first
        try:
            from config.settings import get_settings
            url = get_settings().redis_url
            if url:
                import redis as _redis
                r = _redis.from_url(url, decode_responses=True)
                raw_list = r.lrange("tv_signals", 0, 100)
                for raw in raw_list:
                    d = json.loads(raw)
                    if d.get("timestamp", 0) >= cutoff:
                        if not symbol or d.get("symbol") == symbol.upper():
                            signals.append(TVSignal.from_dict(d))
                if signals:
                    return signals
        except Exception:
            pass

        # Fallback to in-memory
        for d in reversed(_MEM_SIGNALS):
            if d.get("timestamp", 0) < cutoff:
                break
            if not symbol or d.get("symbol") == symbol.upper():
                signals.append(TVSignal.from_dict(d))

        return signals

    async def get_consensus(self, symbol: str, max_age_sec: int = 300) -> Dict[str, Any]:
        """Get consensus direction from recent TV signals for a symbol.
        Returns {'direction': 'LONG'|'SHORT'|'NEUTRAL', 'confidence': 0-1,
                 'signal_count': N, 'buy_count': N, 'sell_count': N}."""
        signals = await self.get_recent_signals(symbol, max_age_sec)
        if not signals:
            return {
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "signal_count": 0,
                "buy_count": 0,
                "sell_count": 0,
            }

        buy_count = sum(1 for s in signals if s.action in ("BUY", "LONG"))
        sell_count = sum(1 for s in signals if s.action in ("SELL", "SHORT"))
        total = len(signals)

        if buy_count > sell_count:
            direction = "LONG"
            confidence = buy_count / total
        elif sell_count > buy_count:
            direction = "SHORT"
            confidence = sell_count / total
        else:
            direction = "NEUTRAL"
            confidence = 0.5

        return {
            "direction": direction,
            "confidence": round(confidence, 3),
            "signal_count": total,
            "buy_count": buy_count,
            "sell_count": sell_count,
        }


# ═══════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    from config.settings import get_settings, setup_logging

    setup_logging()
    settings = get_settings()
    port = getattr(settings, 'tv_webhook_port', 8080)

    logger.info("Starting TradingView webhook server on port %d", port)
    app = create_webhook_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
