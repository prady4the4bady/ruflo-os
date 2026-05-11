# PRADY TRADER

Multi-agent AI crypto trading bot.  
Seven specialised AI agents vote through a council to produce high-confidence trade signals,
executed in paper or live mode on Binance.

---

## Architecture

```
┌──────────────────── Data Layer ─────────────────────┐
│  Binance WS · CoinGecko · NewsData · NewsAPI         │
│  CoinAPI · CryptoCompare · Reddit · Blockchain.info  │
│  Macro feeds · FreeCryptoAPI · Whale detector          │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌──────────────────── Indicators ─────────────────────┐
│  RSI · MACD · Bollinger · ATR · OBV · VWAP · ADX    │
│  Ichimoku · Fibonacci · Heikin-Ashi · Stochastic     │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌──────────────────── Agents ─────────────────────────┐
│  Oracle (25%) · Prophet (22%) · Sentinel (13%)       │
│  Arbiter (13%) · Oracle Extended (10%)               │
│  Debater (9%) · Warden (8% — veto power)             │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌──────────────────── Council ────────────────────────┐
│  Weighted voting · Confidence thresholds             │
│  Long ≥ 65 · Short ≤ −65 · Decision logging         │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌──────────────────── Execution ──────────────────────┐
│  Paper executor (default) · Live executor            │
│  Position sizing · Stop-loss · Take-profit           │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌──────────────────── Production ─────────────────────┐
│  Process manager · Health monitor · Rate limiter     │
│  Structured logging (loguru) · Telegram alerts       │
│  10-screen native PyQt desktop workstation           │
└─────────────────────────────────────────────────────┘
```

---

## Agents

| Agent | Weight | Role |
|---|---|---|
| **Oracle** | 25 % | Primary technical analysis (RSI, MACD, Bollinger, ADX) |
| **Prophet** | 22 % | ML-based price prediction (XGBoost, feature engineering) |
| **Sentinel** | 13 % | Sentiment analysis (news, social, Fear & Greed index) |
| **Arbiter** | 13 % | Orderbook and volume analysis, whale detection |
| **Oracle Extended** | 10 % | Extended indicators (Ichimoku, Fibonacci, Stochastic, VWAP) |
| **Debater** | 9 % | Contrarian analysis — challenges consensus |
| **Warden** | 8 % | Risk management — can veto any trade |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL, Redis, Ollama)
- Binance API key (paper trading)

### 1. Clone & Install

```powershell
git clone <repo-url> prady-trader
cd prady-trader
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your keys:

```powershell
Copy-Item .env.example .env
```

Required:
- `BINANCE_API_KEY` / `BINANCE_API_SECRET`

Optional (more data sources):
- `COINGECKO_API_KEY`, `NEWSDATA_KEY`, `NEWSAPI_KEY`
- `COINAPI_KEY`, `NEWSDATA_KEY`, `CRYPTOCOMPARE_KEY`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### 3. Start Infrastructure

```powershell
docker compose up -d
```

This starts PostgreSQL (port 5433), Redis (6379), and Ollama (11434).

### 4. Launch Desktop Workstation

```powershell
python run_desktop.py
```

The desktop shell now exposes the full routed workstation: Home, Markets, Trading Floor, Agent Matrix, Ledger, Performance, System Health, Strategy Builder, Control Room, and Settings.

### 5. Optional: Run Headless Trading Runtime

```powershell
python scripts/start_paper.py
```

Or use the process manager for auto-restart:

```powershell
python scripts/process_manager.py
```

---

## Project Structure

```
prady-trader/
├── agents/               # 7 AI agents + base class
├── config/               # settings.py (env), constants.py (numbers)
├── council/              # Voting, orchestrator, decision log, weight mgr
├── dashboard/            # Shared state + analytics helpers
├── data/                 # Binance client, free APIs, feeds, whale detector
├── desktop/              # Native PyQt workstation shell and pages
├── execution/            # Paper & live trade executors
├── indicators/           # 15+ technical indicators
├── ml/                   # XGBoost model, feature engineering
├── models/               # Saved model artifacts
├── scripts/              # Launchers, backtest, validate, process manager
├── tests/                # 89 unit tests
├── utils/                # Telegram, health monitor, rate limiter, logging
├── docker-compose.yml
├── Makefile
└── requirements.txt
```

---

## Makefile Targets

| Target | Description |
|---|---|
| `make install` | Install Python dependencies |
| `make desktop` | Launch the native desktop workstation |
| `make run` | Start headless paper trading |
| `make run-managed` | Start with process manager (auto-restart) |
| `make test` | Run pytest (89 tests) |
| `make validate` | Run full validation suite |
| `make backtest` | Run backtester |
| `make train` | Train ML models |
| `make lint` | Compile-check all modules |
| `make docker-up` | Start Docker services |
| `make docker-down` | Stop Docker services |
| `make telegram-test` | Send test Telegram message |
| `make health` | Show last health check |
| `make clean` | Remove caches and artifacts |

---

## Production Features

- **Process Manager** — Supervises the headless orchestrator runtime with auto-restart and exponential backoff (max 10 restarts).
- **Health Monitor** — 7 checks every 30 s: Binance connectivity, cycle freshness, Redis, balance safety, position age, disk, memory. Auto-recovery callbacks.
- **Rate Limiter** — Token-bucket per API provider with daily usage caps. Integrated into all 10+ free API functions.
- **Structured Logging** — Loguru with 5 sinks: console, main log, trades log, errors, JSON structured. Rotating files with 7-day retention.
- **Telegram Alerts** — Trade opened/closed, council decisions, daily/weekly summaries, health alerts, kill switch, system status. Retry with exponential backoff.
- **Graceful Shutdown** — Signal handling (SIGINT/SIGTERM), state persistence to `data/last_state.json`, clean position unwind.

---

## Testing

```powershell
# Unit tests
pytest tests/ -v

# Full validation suite
python scripts/validate_build.py
```

---

## License

Private — all rights reserved.
