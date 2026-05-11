"""
PRADY TRADER — Centralised configuration loaded from .env
Uses Pydantic BaseSettings so every value is validated on startup.
"""

from __future__ import annotations

import logging
import re
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*copy_on_write.*")
from decimal import Decimal
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
VALID_TRADING_MODES = ("paper", "testnet", "live")
VALID_SAFE_RESERVE_ASSETS = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USDP", "DAI"}


def normalize_runtime_mode(mode: str) -> str:
    normalized = str(mode).lower().strip()
    if normalized not in VALID_TRADING_MODES:
        raise ValueError(
            "TRADING_MODE must be one of: paper, testnet, live"
        )
    return normalized


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Binance ──────────────────────────────────────────────
    binance_api_key: str = ""
    binance_secret_key: str = ""
    binance_live_api_key: str = ""
    binance_live_secret_key: str = ""
    binance_testnet_api_key: str = ""
    binance_testnet_secret_key: str = ""
    binance_testnet: bool = True
    binance_tld: str = "com"

    # ── Trading mode ─────────────────────────────────────────
    trading_mode: str = "paper"

    # ── Risk parameters ──────────────────────────────────────
    max_risk_per_trade: Decimal = Decimal("0.02")
    max_daily_loss: Decimal = Decimal("0.05")
    max_concurrent_positions: int = 3
    max_consecutive_losses: int = 3
    kelly_fraction: Decimal = Decimal("0.25")
    min_confidence: Decimal = Decimal("0.85")
    default_leverage: int = 5
    live_min_rehearsal_trades: int = 20
    live_min_rehearsal_win_rate: Decimal = Decimal("0.55")
    live_require_positive_rehearsal_pnl: bool = True
    safe_reserve_asset: str = "USDT"
    enable_safe_reserve_conversion: bool = True

    # ── Free API keys (all optional) ─────────────────────────
    coingecko_api_key: str = ""
    news_api_key: str = ""
    newsdata_api_key: str = ""
    cryptocompare_api_key: str = ""
    coinapi_key: str = ""
    bitquery_api_key: str = ""
    taapi_secret: str = ""
    freecrypto_api_key: str = ""
    enable_newsapi: bool = True
    enable_newsdata: bool = True
    enable_cryptocompare: bool = True
    enable_coinapi: bool = True
    enable_bitquery: bool = True
    enable_freecrypto: bool = True
    enable_ollama_reasoning: bool = True
    enable_nvidia_nim_reasoning: bool = True
    provider_warning_cooldown_sec: int = 300
    provider_startup_grace_sec: int = 180
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "prady-trader/1.0"

    # ── Telegram (optional) ──────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite:///./prady_trader.db"

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = ""

    # ── Ollama ───────────────────────────────────────────────
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    ollama_timeout_sec: int = 60

    # ── NVIDIA NIM fallback ──────────────────────────────────
    nvidia_nim_api_key: str = ""
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_nim_model: str = "meta/llama-3.1-70b-instruct"

    # ── Symbols ──────────────────────────────────────────────
    trading_pairs: List[str] = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

    # ── Hedge grid parameters ────────────────────────────────
    hedge_ratio: Decimal = Decimal("0.4")
    harvest_threshold: Decimal = Decimal("0.003")
    max_hold_minutes: int = 240
    daily_profit_target: Decimal = Decimal("0.03")

    @field_validator("trading_pairs", mode="before")
    @classmethod
    def split_pairs(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("trading_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        return normalize_runtime_mode(v)

    @field_validator("safe_reserve_asset")
    @classmethod
    def validate_safe_reserve_asset(cls, v: str) -> str:
        normalized = str(v or "USDT").upper().strip()
        if normalized not in VALID_SAFE_RESERVE_ASSETS:
            raise ValueError(
                f"SAFE_RESERVE_ASSET must be one of: {', '.join(sorted(VALID_SAFE_RESERVE_ASSETS))}"
            )
        return normalized

    def model_post_init(self, __context) -> None:
        if self.trading_mode == "testnet":
            self.binance_testnet = True
        elif self.trading_mode == "live":
            self.binance_testnet = False

    @property
    def runtime_mode(self) -> str:
        return self.trading_mode

    @property
    def is_paper(self) -> bool:
        return self.trading_mode == "paper"

    @property
    def is_testnet(self) -> bool:
        return self.trading_mode == "testnet"

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @property
    def uses_binance_execution(self) -> bool:
        return self.trading_mode in ("testnet", "live")

    @property
    def mode_label(self) -> str:
        return self.trading_mode.upper()

    @property
    def live_binance_api_key(self) -> str:
        return self.binance_live_api_key or self.binance_api_key

    @property
    def live_binance_secret_key(self) -> str:
        return self.binance_live_secret_key or self.binance_secret_key

    @property
    def testnet_binance_api_key(self) -> str:
        return self.binance_testnet_api_key

    @property
    def testnet_binance_secret_key(self) -> str:
        return self.binance_testnet_secret_key

    @property
    def trading_binance_api_key(self) -> str:
        if self.execution_environment == "testnet":
            return self.testnet_binance_api_key
        if self.execution_environment == "live":
            return self.live_binance_api_key
        return self.testnet_binance_api_key if self.binance_testnet else self.live_binance_api_key

    @property
    def trading_binance_secret_key(self) -> str:
        if self.execution_environment == "testnet":
            return self.testnet_binance_secret_key
        if self.execution_environment == "live":
            return self.live_binance_secret_key
        return self.testnet_binance_secret_key if self.binance_testnet else self.live_binance_secret_key

    @property
    def display_binance_api_key(self) -> str:
        return self.live_binance_api_key

    @property
    def display_binance_secret_key(self) -> str:
        return self.live_binance_secret_key

    @property
    def live_binance_tld(self) -> str:
        normalized = str(self.binance_tld or "com").strip().lower()
        return normalized or "com"

    @property
    def execution_environment(self) -> str:
        if self.is_paper:
            return "paper"
        if self.is_testnet:
            return "testnet"
        return "live"

    @property
    def has_live_account_credentials(self) -> bool:
        return bool(self.live_binance_api_key and self.live_binance_secret_key)

    @property
    def has_testnet_account_credentials(self) -> bool:
        return bool(self.testnet_binance_api_key and self.testnet_binance_secret_key)

    @property
    def effective_min_confidence(self) -> Decimal:
        """Mode-aware min confidence with a softer threshold for paper and testnet."""
        from config.constants import (
            LIVE_MIN_CONFIDENCE,
            PAPER_MIN_CONFIDENCE,
            BACKTEST_MIN_CONFIDENCE,
        )
        if self.is_live:
            return Decimal(str(LIVE_MIN_CONFIDENCE))
        if self.is_testnet or self.is_paper:
            return Decimal(str(PAPER_MIN_CONFIDENCE))
        return Decimal(str(BACKTEST_MIN_CONFIDENCE))


# ── Singleton ────────────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def persist_runtime_mode(mode: str) -> None:
    normalized = normalize_runtime_mode(mode)
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8")
    else:
        text = ""

    target_testnet = normalized in ("paper", "testnet")

    if re.search(r"^TRADING_MODE\s*=", text, re.MULTILINE):
        text = re.sub(
            r"^TRADING_MODE\s*=.*$",
            f"TRADING_MODE={normalized}",
            text,
            flags=re.MULTILINE,
        )
    else:
        text += f"\nTRADING_MODE={normalized}"

    if re.search(r"^BINANCE_TESTNET\s*=", text, re.MULTILINE):
        text = re.sub(
            r"^BINANCE_TESTNET\s*=.*$",
            f"BINANCE_TESTNET={'true' if target_testnet else 'false'}",
            text,
            flags=re.MULTILINE,
        )
    else:
        text += f"\nBINANCE_TESTNET={'true' if target_testnet else 'false'}"

    env_path.write_text(text.strip() + "\n", encoding="utf-8")


def apply_runtime_mode(mode: str, *, persist: bool = False) -> Settings:
    normalized = normalize_runtime_mode(mode)
    settings = get_settings()
    settings.trading_mode = normalized
    settings.binance_testnet = normalized in ("paper", "testnet")

    if persist:
        persist_runtime_mode(normalized)

    try:
        from data.binance_client import reset_binance_client

        reset_binance_client()
    except Exception:
        pass

    return settings


class SafeStreamHandler(logging.StreamHandler):
    """Console handler that degrades unsupported characters instead of crashing."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                msg = self.format(record)
                stream = self.stream
                encoding = getattr(stream, "encoding", None) or "utf-8"
                safe_msg = msg.encode(encoding, errors="replace").decode(encoding, errors="replace")
                stream.write(safe_msg + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)


# ── Logging setup ────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = SafeStreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(level)

    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        log_dir / "prady_trader.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    root = logging.getLogger("prady")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)
    return root
