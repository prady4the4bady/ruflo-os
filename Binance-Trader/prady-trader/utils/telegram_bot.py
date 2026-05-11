"""
PRADY TRADER — Production Telegram notification bot.
Sends trade alerts, council decisions, system status, and daily summaries.
Includes retry logic with exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from config.settings import get_settings

logger = logging.getLogger("prady.utils.telegram_bot")

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


class TelegramBot:
    """Async Telegram notification sender with retry logic."""

    def __init__(self):
        settings = get_settings()
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id
        self._enabled = bool(
            self._token
            and self._chat_id
            and self._token != "your_token"
            and self._chat_id != "your_chat_id"
        )
        if not self._enabled:
            logger.info("Telegram notifications disabled (no token configured)")

    @property
    def is_configured(self) -> bool:
        return self._enabled

    def validate_connection_sync(self, send_test: bool = False) -> Dict[str, Any]:
        """Validate Telegram bot configuration and optionally send a delivery test."""
        if not self._enabled:
            return {
                "configured": False,
                "ok": False,
                "message": "Telegram bot token or chat id not configured",
            }

        import requests as _req

        base_url = f"https://api.telegram.org/bot{self._token}"

        try:
            me_resp = _req.get(f"{base_url}/getMe", timeout=10)
            me_data = me_resp.json()
            if me_resp.status_code != 200 or not me_data.get("ok"):
                return {
                    "configured": True,
                    "ok": False,
                    "message": f"Telegram getMe failed: {me_data.get('description', me_resp.text[:160])}",
                }

            chat_resp = _req.get(
                f"{base_url}/getChat",
                params={"chat_id": self._chat_id},
                timeout=10,
            )
            chat_data = chat_resp.json()
            if chat_resp.status_code != 200 or not chat_data.get("ok"):
                return {
                    "configured": True,
                    "ok": False,
                    "message": f"Telegram getChat failed: {chat_data.get('description', chat_resp.text[:160])}",
                }

            bot_info = me_data.get("result") or {}
            chat_info = chat_data.get("result") or {}
            chat_label = chat_info.get("title") or chat_info.get("username") or str(chat_info.get("id") or self._chat_id)

            result = {
                "configured": True,
                "ok": True,
                "bot_username": bot_info.get("username", "unknown"),
                "chat": chat_label,
                "message": f"Telegram bot @{bot_info.get('username', 'unknown')} and chat {chat_label} verified",
            }

            if send_test:
                send_resp = _req.post(
                    f"{base_url}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": "PRADY TRADER Telegram delivery test: wiring is healthy.",
                    },
                    timeout=10,
                )
                send_data = send_resp.json()
                if send_resp.status_code != 200 or not send_data.get("ok"):
                    return {
                        "configured": True,
                        "ok": False,
                        "message": f"Telegram sendMessage failed: {send_data.get('description', send_resp.text[:160])}",
                    }

                result["message"] = f"Telegram delivery test sent to {chat_label}"

            return result
        except Exception as exc:
            return {
                "configured": True,
                "ok": False,
                "message": f"Telegram validation failed: {exc}",
            }

    async def _send(self, text: str, parse_mode: str = "HTML"):
        """Send a message via Telegram Bot API with retry."""
        if not self._enabled:
            return
        import aiohttp

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        for attempt in range(MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            return
                        data = await resp.text()
                        logger.warning("Telegram send failed (%d, attempt %d): %s", resp.status, attempt + 1, data)
            except Exception as exc:
                logger.warning("Telegram send error (attempt %d): %s", attempt + 1, exc)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF ** attempt)

    async def trade_opened(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        confidence: float,
        paper: bool = True,
    ):
        """Send a trade entry notification."""
        mode = "📄 PAPER" if paper else "💰 LIVE"
        emoji = "🟢" if direction == "LONG" else "🔴"
        text = (
            f"{mode} {emoji} <b>NEW TRADE</b>\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Direction: <b>{direction}</b>\n"
            f"Entry: <code>${entry_price:,.2f}</code>\n"
            f"Quantity: <code>{quantity:.4f}</code>\n"
            f"Confidence: <code>{confidence:.2%}</code>"
        )
        await self._send(text)

    # Backward compatibility alias
    send_trade_alert = trade_opened

    async def trade_closed(
        self,
        symbol: str,
        direction: str,
        pnl: float,
        pnl_pct: float,
        reason: str = "signal",
    ):
        """Send a trade close notification."""
        emoji = "✅" if pnl > 0 else "❌"
        text = (
            f"{emoji} <b>TRADE CLOSED</b>\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Direction: <b>{direction}</b>\n"
            f"PnL: <code>${pnl:+,.2f} ({pnl_pct:+.2f}%)</code>\n"
            f"Reason: {reason}"
        )
        await self._send(text)

    # Backward compatibility alias
    send_trade_closed = trade_closed

    async def daily_summary(
        self,
        balance: float,
        daily_pnl: float,
        total_trades: int,
        win_rate: float,
        open_positions: int = 0,
    ):
        """Send end-of-day summary."""
        emoji = "📈" if daily_pnl >= 0 else "📉"
        text = (
            f"{emoji} <b>DAILY SUMMARY</b>\n"
            f"Balance: <code>${balance:,.2f}</code>\n"
            f"Daily PnL: <code>${daily_pnl:+,.2f}</code>\n"
            f"Trades: <code>{total_trades}</code>\n"
            f"Win Rate: <code>{win_rate:.1%}</code>\n"
            f"Open Positions: <code>{open_positions}</code>"
        )
        await self._send(text)

    # Backward compatibility alias
    send_daily_summary = daily_summary

    async def system_started(self, mode: str = "paper", pairs: int = 5):
        """Send system startup notification."""
        text = (
            f"🚀 <b>PRADY TRADER STARTED</b>\n"
            f"Mode: <code>{mode.upper()}</code>\n"
            f"Pairs: <code>{pairs}</code>\n"
            f"Time: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>"
        )
        await self._send(text)

    async def kill_switch_triggered(self, reason: str = "manual"):
        """Send kill switch activation alert."""
        text = (
            f"🛑 <b>KILL SWITCH ACTIVATED</b>\n"
            f"Reason: {reason}\n"
            f"Time: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"All trading halted."
        )
        await self._send(text)

    async def health_alert(self, check_name: str, status: str, message: str):
        """Send health monitor alert."""
        emoji = "⚠️" if status == "degraded" else "❌"
        text = (
            f"{emoji} <b>HEALTH ALERT</b>\n"
            f"Check: <code>{check_name}</code>\n"
            f"Status: <b>{status.upper()}</b>\n"
            f"Details: {message}"
        )
        await self._send(text)

    async def weekly_report(
        self,
        balance: float,
        weekly_pnl: float,
        total_trades: int,
        win_rate: float,
        best_trade: float,
        worst_trade: float,
    ):
        """Send weekly performance report."""
        emoji = "📈" if weekly_pnl >= 0 else "📉"
        text = (
            f"{emoji} <b>WEEKLY REPORT</b>\n"
            f"Balance: <code>${balance:,.2f}</code>\n"
            f"Weekly PnL: <code>${weekly_pnl:+,.2f}</code>\n"
            f"Trades: <code>{total_trades}</code>\n"
            f"Win Rate: <code>{win_rate:.1%}</code>\n"
            f"Best: <code>${best_trade:+,.2f}</code>\n"
            f"Worst: <code>${worst_trade:+,.2f}</code>"
        )
        await self._send(text)

    async def send_council_decision(
        self,
        symbol: str,
        action: str,
        score: float,
        confidence: float,
        veto: bool = False,
    ):
        """Send council vote result."""
        emoji = "🟢" if action == "LONG" else "🔴" if action == "SHORT" else "⚪"
        veto_text = " 🚫 VETOED" if veto else ""
        text = (
            f"{emoji} <b>COUNCIL VOTE</b>{veto_text}\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Action: <b>{action}</b>\n"
            f"Score: <code>{score:+.1f}</code>\n"
            f"Confidence: <code>{confidence:.2%}</code>"
        )
        await self._send(text)

    async def send_warden_alert(self, symbol: str, reason: str):
        """Send Warden veto alert."""
        text = (
            f"🚨 <b>WARDEN VETO</b>\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Reason: {reason}"
        )
        await self._send(text)

    async def send_system_status(self, status: str, details: str = ""):
        """Send system status update."""
        text = f"⚙️ <b>SYSTEM</b>: {status}"
        if details:
            text += f"\n{details}"
        await self._send(text)

    async def send_test(self):
        """Send a test message to verify bot configuration."""
        text = (
            "🤖 <b>PRADY TRADER — Test Message</b>\n"
            "✅ Telegram notifications are working!"
        )
        await self._send(text)
        return self._enabled

    def send_sync(self, text: str):
        """Synchronous send wrapper for non-async contexts."""
        if not self._enabled:
            logger.info("Telegram disabled — message not sent: %s", text[:60])
            return
        import requests as _req
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        for attempt in range(MAX_RETRIES):
            try:
                resp = _req.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    return
                logger.warning("Telegram sync send failed (%d, attempt %d): %s", resp.status_code, attempt + 1, resp.text)
            except Exception as exc:
                logger.warning("Telegram sync send error (attempt %d): %s", attempt + 1, exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF ** attempt)


# Singleton
_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    global _bot
    if _bot is None:
        _bot = TelegramBot()
    return _bot
