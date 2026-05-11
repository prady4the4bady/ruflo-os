"""
PRADY TRADER — Magic numbers centralised in one place.
"""

from decimal import Decimal

# ── Timeframes (Binance kline intervals) ────────────────────
TIMEFRAMES = ["1m", "3m", "5m", "15m", "1h", "4h", "1d", "1w"]

# Weights for multi-timeframe scoring
TIMEFRAME_WEIGHTS = {
    "1m": 0.05,
    "3m": 0.05,
    "5m": 0.08,
    "15m": 0.12,
    "1h": 0.20,
    "4h": 0.25,
    "1d": 0.20,
    "1w": 0.05,
}

# ── Default trading pairs ───────────────────────────────────
DEFAULT_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "MATICUSDT", "DOTUSDT",
]

# ── EMA periods used by Oracle ──────────────────────────────
EMA_PERIODS = [8, 13, 21, 34, 55, 89, 200]

# ── Indicator defaults ──────────────────────────────────────
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

STOCH_RSI_PERIOD = 14
STOCH_RSI_SMOOTH_K = 3
STOCH_RSI_SMOOTH_D = 3

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ADX_PERIOD = 14
ADX_STRONG_TREND = 25

ICHIMOKU_TENKAN = 9
ICHIMOKU_KIJUN = 26
ICHIMOKU_SENKOU = 52

BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2.0

ATR_PERIOD = 14

KELTNER_PERIOD = 20
KELTNER_MULT = 1.5

DONCHIAN_PERIOD = 20

CCI_PERIOD = 20
WILLIAMS_PERIOD = 14
MFI_PERIOD = 14
ROC_PERIOD = 10
TSI_LONG = 25
TSI_SHORT = 13

CMF_PERIOD = 20

SUPERTREND_ATR_MULT = 3.0
SUPERTREND_ATR_PERIOD = 10

# ── Structure detection ─────────────────────────────────────
STRUCTURE_LOOKBACK = 50
FIBONACCI_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

# ── Agent council weights ───────────────────────────────────
AGENT_WEIGHTS = {
    "oracle": 0.27,
    "prophet": 0.09,
    "arbiter": 0.16,
    "sentinel": 0.10,
    "oracle_extended": 0.10,
    "strategy_fusion": 0.18,
    "debater": 0.05,
    "warden": 0.05,  # VETO-only agent, weight used for tie-breaking
}
AGENT_WEIGHT_MIN = 0.05
AGENT_WEIGHT_MAX = 0.45

# ── Council thresholds ──────────────────────────────────────
COUNCIL_LONG_THRESHOLD = 12
COUNCIL_SHORT_THRESHOLD = -12
COUNCIL_CONFIDENCE_SCALE = 16.0
MIN_AGENT_CONFIDENCE = 0.5

# ── Backtest thresholds (relaxed for more trade signals) ────
BACKTEST_LONG_THRESHOLD = 58
BACKTEST_SHORT_THRESHOLD = 42
BACKTEST_MIN_CONFIDENCE = 0.50

# ── Mode-based confidence thresholds ────────────────────────
LIVE_MIN_CONFIDENCE = 0.85
PAPER_MIN_CONFIDENCE = 0.60
UNTRAINED_MIN_CONFIDENCE = 0.55

# ── Risk constants ──────────────────────────────────────────
MAX_POSITION_PCT = Decimal("0.10")
MIN_TIME_BETWEEN_TRADES_SEC = 30
KELLY_ROLLING_WINDOW = 50
MAX_LEVERAGE = 10

# ── Hedge grid constants ────────────────────────────────────
DEFAULT_HEDGE_RATIO = Decimal("0.4")
DEFAULT_HARVEST_THRESHOLD = Decimal("0.003")
DEFAULT_MAX_HOLD_MINUTES = 240
DEFAULT_DAILY_PROFIT_TARGET = Decimal("0.03")

# ── Sentiment thresholds ────────────────────────────────────
FEAR_GREED_EXTREME_FEAR = 25
FEAR_GREED_EXTREME_GREED = 75
FUNDING_RATE_CROWDED_LONG = Decimal("0.001")
FUNDING_RATE_CROWDED_SHORT = Decimal("-0.0005")
LONG_SHORT_RATIO_BEAR = Decimal("2.0")
LONG_SHORT_RATIO_BULL = Decimal("0.5")

# ── Order book thresholds ───────────────────────────────────
OB_IMBALANCE_BULL = 0.3
OB_IMBALANCE_BEAR = -0.3
LARGE_ORDER_MULT = 5.0
ORDERFLOW_NEUTRAL_BAND = 12.0
FORCE_SIGNAL_EXIT_CONFIDENCE = 0.88
FORCE_SIGNAL_EXIT_LOSS_PCT = Decimal("-0.25")
SAFE_RESERVE_MIN_NOTIONAL_USDT = Decimal("10")
SAFE_RESERVE_BUFFER_USDT = Decimal("25")

# ── ML constants ────────────────────────────────────────────
PROPHET_NEUTRAL_EDGE = 0.10
PROPHET_MIN_SIGNAL_STRENGTH = 0.12
LSTM_SEQUENCE_LEN = 200
LSTM_FEATURES = 10
LSTM_HIDDEN_1 = 128
LSTM_HIDDEN_2 = 64
LSTM_DENSE_1 = 32

XGB_N_ESTIMATORS = 500
XGB_MAX_DEPTH = 8
XGB_LEARNING_RATE = 0.05

TFT_HIDDEN_SIZE = 64
TFT_ATTENTION_HEADS = 4
TFT_NUM_LAYERS = 2

ENSEMBLE_WEIGHTS = {
    "lstm": 0.35,
    "xgboost": 0.40,
    "tft": 0.25,
}
ENSEMBLE_DISAGREE_THRESHOLD = 0.3

# ── API retry settings ──────────────────────────────────────
API_MAX_RETRIES = 3
API_RETRY_BACKOFF = 2.0

# ── Dashboard refresh ───────────────────────────────────────
DASHBOARD_REFRESH_SEC = 2

# ── Council cycle interval (seconds) ────────────────────────
COUNCIL_CYCLE_SEC = 30

# ── Model versioning directory ──────────────────────────────
MODEL_DIR = "models"

# ── Confidence exit threshold ────────────────────────────────
CONFIDENCE_EXIT_THRESHOLD = 0.60
