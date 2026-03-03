# 🤖 ML Scalping Trading Bot — Complete Documentation

> **Automated intraday trading bot** for the Indian stock market (NSE) using the **Opening Range Breakout (ORB)** strategy with VWAP confirmation, multi-stock portfolio management, and confidence-based capital allocation — powered by the [Zerodha Kite Connect API](https://kite.trade).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Core Trading Algorithm](#3-core-trading-algorithm)
4. [Signal Filters & Enhancements](#4-signal-filters--enhancements)
5. [Exit Strategy — 3-Stage Partial Booking](#5-exit-strategy--3-stage-partial-booking)
6. [Multi-Stock Mode & Confidence Scoring](#6-multi-stock-mode--confidence-scoring)
7. [Auto-Login System](#7-auto-login-system)
8. [Risk Management](#8-risk-management)
9. [Frontend Dashboard](#9-frontend-dashboard)
10. [Backend API](#10-backend-api)
11. [Configuration Reference](#11-configuration-reference)
12. [Setup & Installation](#12-setup--installation)
13. [Environment Variables](#13-environment-variables)
14. [Running the Bot](#14-running-the-bot)
15. [Deployment](#15-deployment)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    REACT FRONTEND (:3000)                    │
│  Dashboard │ Portfolio │ Market Watch │ Live Terminal │ API  │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST API (axios)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  FLASK BACKEND (:5000)                       │
│  Auth │ Bot Control │ Analytics │ Kite OAuth │ Trade CRUD   │
│                            │                                │
│              ┌─────────────┴─────────────┐                  │
│              ▼                           ▼                  │
│     TradingService              SQLAlchemy (PostgreSQL)      │
│     (bot lifecycle)             Users/Trades/Logs/Stats      │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                    BOT ENGINE (app_files/)                   │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  bot_kite.py  │  │ kite_service │  │   config.py      │  │
│  │  (3400+ lines)│  │  (API wrapper)│  │  (all params)    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘  │
│         │                 │                                  │
│         ▼                 ▼                                  │
│  ┌────────────────────────────────┐                         │
│  │   Zerodha Kite Connect API     │                         │
│  │   (Orders, Quotes, Historical) │                         │
│  └────────────────────────────────┘                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │ kite_login.py │  │kite_session.py│  ← Auto-Login System  │
│  │ (5-step auth) │  │(token manager)│                       │
│  └──────────────┘  └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

**Tech Stack:**

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, React Router, Axios, Recharts |
| Backend | Python Flask, Flask-SQLAlchemy, Flask-CORS |
| Database | PostgreSQL (production) / SQLite (dev) |
| Broker API | Zerodha Kite Connect SDK (`kiteconnect==4.2.0`) |
| Auth | JWT tokens, TOTP 2FA via `pyotp` |

---

## 2. Project Structure

```
Trading-bot/
├── app_files/                  # Core bot engine
│   ├── bot_kite.py             # Main trading algorithm (3400+ lines)
│   ├── config.py               # All strategy parameters & configuration
│   ├── kite_service.py         # Kite API wrapper with caching & rate limiting
│   ├── kite_login.py           # Automated 5-step Kite login (TOTP 2FA)
│   ├── kite_session.py         # Session manager with token persistence
│   └── requirements.txt        # Python dependencies (bot)
│
├── backend/                    # Flask REST API
│   ├── app.py                  # API endpoints (1700+ lines)
│   ├── models.py               # SQLAlchemy models (User, Trade, DailyStats, etc.)
│   ├── trading_service.py      # Bot lifecycle manager
│   └── requirements.txt        # Python dependencies (backend)
│
├── frontend/                   # React dashboard
│   ├── src/
│   │   ├── App.jsx             # Router setup
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx   # Main dashboard + Refresh Login button
│   │   │   ├── Portfolio.jsx   # Trade history & P&L
│   │   │   ├── MarketWatch.jsx # Live market data
│   │   │   ├── TradingMonitor.jsx  # Real-time trade monitoring
│   │   │   └── LiveTerminalPage.jsx # Bot log streaming
│   │   ├── components/
│   │   │   ├── APITester.jsx   # Manual API testing tool
│   │   │   └── LiveTerminal.jsx # WebSocket-style log viewer
│   │   └── services/
│   │       └── api.js          # Axios API client
│   └── package.json
│
├── backtest/                   # Backtesting framework
│   ├── backtest.py             # Full backtester
│   ├── backtest_analyzer.py    # Trade analysis & metrics
│   └── ...
│
├── .env                        # Credentials (gitignored)
├── access_token.txt            # Cached Kite token (gitignored)
└── .gitignore
```

---

## 3. Core Trading Algorithm

The bot implements an **Opening Range Breakout (ORB)** strategy enhanced with VWAP confirmation, volume filters, and multiple exit stages.

### 3.1 Daily Lifecycle

```
09:15 ──── Market Opens ────────────────────────────────────────
  │
  │   PHASE 1: SETUP (09:15 → 09:30)
  │   • Fetch 15-minute opening candle (High, Low, Open, Close)
  │   • Calculate VWAP (Volume Weighted Average Price)
  │   • Calculate dynamic ATR buffer
  │   • Calculate gap % from previous close (Enhancement 2)
  │   • Calculate open-position bias (Enhancement 3)
  │   • Set triggers: Long = High + Buffer, Short = Low - Buffer
  │
09:30 ──── Primary Entry Window Opens ──────────────────────────
  │
  │   PHASE 2: SIGNAL SCANNING (09:30 → 10:45)
  │   • Poll 5-minute candles every 30 seconds
  │   • Check each symbol for breakout conditions
  │   • Apply all filters (Volume, NIFTY, Trend, Gap, Open Bias)
  │   • Execute trade when signal passes all filters
  │
  │   09:30-10:15  PRIMARY WINDOW   → Normal entry rules
  │   10:15-10:45  SOFT CUTOFF      → Extra confirmation needed (2x volume)
  │   10:45+       HARD STOP        → No new entries allowed
  │
10:45 ──── Entry Window Closes ─────────────────────────────────
  │
  │   PHASE 3: POSITION MANAGEMENT (until 15:25)
  │   • Monitor live price every 10 seconds
  │   • Execute 3-stage partial booking exits
  │   • Trail stop loss using ATR
  │   • Check daily loss limits
  │
15:25 ──── Auto-Exit All Positions (MIS requirement) ──────────
  │
15:30 ──── Market Close / Generate Report ──────────────────────
```

### 3.2 Entry Conditions

**LONG (BUY) Signal:**
```
5-min candle close  >  Opening Range High + ATR Buffer
          AND
5-min candle close  >  VWAP
          AND
All filters pass (Volume, NIFTY, Gap, Open Bias, Trend)
```

**SHORT (SELL) Signal:**
```
5-min candle close  <  Opening Range Low - ATR Buffer
          AND
5-min candle close  <  VWAP
          AND
All filters pass (Volume, NIFTY, Gap, Open Bias, Trend)
```

### 3.3 Stop Loss Calculation

The bot uses a **dynamic stop loss** that's tighter than the standard ORB stop:

```python
# Standard ORB SL = VWAP or Candle Low/High
# Bot applies STOPLOSS_DISTANCE_FACTOR = 0.5 (tighter by 50%)

risk = abs(entry_price - standard_sl)
actual_sl = entry_price - (risk * 0.5)   # For LONG
actual_sl = entry_price + (risk * 0.5)   # For SHORT
```

This means the SL is placed **50% closer** to entry than the traditional ORB SL, reducing risk per trade while maintaining the same profit targets.

---

## 4. Signal Filters & Enhancements

Every breakout signal must pass through a **cascade of filters** before becoming a trade. Each filter can independently skip a signal:

### Filter Pipeline (in order)

```
Breakout Detected (price > trigger + above VWAP)
    │
    ├── ① Entry Window Filter ── Is it within 09:30-10:45?
    │                             (SOFT window needs 2x volume)
    │
    ├── ② Volume Confirmation ── Is current volume > 1.2× average?
    │                             (time-of-day adjusted)
    │
    ├── ③ Gap Alignment ──────── Does pre-market gap support direction?
    │     (Enhancement 2)         LONG: skip if gap < -0.3%
    │                             SHORT: skip if gap > +0.3%
    │
    ├── ④ Open Position Bias ─── Does candle structure confirm direction?
    │     (Enhancement 3)         LONG: skip if open near candle low
    │                             SHORT: skip if open near candle high
    │
    ├── ⑤ NIFTY Index Filter ── Is NIFTY 50 trending in same direction?
    │                             Soft bias (warns) or hard block
    │
    ├── ⑥ Trend Filter ──────── Is 15-min VWAP trending with signal?
    │
    ├── ⑦ Range Quality ──────── Is opening range 0.1%-2.5% of price?
    │                             (Rejects too narrow/wide ranges)
    │
    └── ⑧ Liquidity Filter ──── Is daily volume > 500K shares?
                                  (Currently disabled to save API calls)
```

### 4.1 Gap Alignment Filter (Enhancement 2)

Calculates the percentage gap between the previous day's close and today's open:

```python
gap_pct = ((today_open - prev_close) / prev_close) × 100
```

| Gap Value | LONG Signal | SHORT Signal |
|-----------|------------|-------------|
| > +1.0% (strong gap up) | ✅ Strong confirmation | ❌ **SKIP** (contradicts) |
| +0.3% to +1.0% | ✅ Moderate confirmation | ❌ **SKIP** |
| -0.3% to +0.3% | ⚠️ Neutral (allow) | ⚠️ Neutral (allow) |
| -0.3% to -1.0% | ❌ **SKIP** (contradicts) | ✅ Moderate confirmation |
| < -1.0% (strong gap down) | ❌ **SKIP** | ✅ Strong confirmation |

### 4.2 Open Position Bias Filter (Enhancement 3)

Analyzes WHERE the open price sits within the opening range candle:

```python
open_position_in_range = (open - low) / (high - low)
```

- **Open near HIGH of range** (≥ 0.75) → **SHORT bias** — price opened high, sellers pushed it down = bearish candle structure
- **Open near LOW of range** (≤ 0.25) → **LONG bias** — price opened low, buyers pushed it up = bullish candle structure
- **Middle** (0.25–0.75) → **NEUTRAL**

| Open Bias | LONG Signal | SHORT Signal |
|-----------|------------|-------------|
| LONG (open near low) | ✅ Confirmed | ❌ **SKIP** |
| NEUTRAL | ⚠️ Allow | ⚠️ Allow |
| SHORT (open near high) | ❌ **SKIP** | ✅ Confirmed |

---

## 5. Exit Strategy — 3-Stage Partial Booking

The bot uses a **"Let Winners Run"** exit strategy that books profits in three stages while maximizing the runner portion:

```
                                ┌─── STAGE 3: Exit 55% at 2R or 3:25 PM ───┐
                                │    (Runner — risk-free after Stage 2)     │
                                │                                           │
                    ┌───────────┤                                           │
                    │ STAGE 2   │                                           │
                    │ Exit 20%  │     55% riding with SL at entry          │
                    │ at 1.0R   │     (GUARANTEED — can't lose)             │
         ┌──────────┤           │                                           │
         │ STAGE 1  │  SL moves │                                           │
         │ Exit 25% │  to ENTRY │                                           │
         │ at 0.5R  │    ↕      │                                           │
    ─────┤          │           │                                           │
  ENTRY  │          │           │                                           │
    ─────┤──────────┤───────────┤───────────────────────────────────────────┤
         │    SL    │           │                                     3:25 PM
         │  (tight) │           │
         └──────────┘           │
              ↑                 │
        Initial SL              2R Target or EOD
        (50% of risk)
```

### Stage Breakdown

| Stage | R-Multiple | % of Position | Action | After Exit |
|-------|-----------|--------------|--------|-----------|
| **Stage 1** | 0.5R | 25% | Book quick profit | SL stays tight, 75% still running |
| **Stage 2** | 1.0R | 20% | Lock 1:1 RR profit | **SL moves to entry** → remaining 55% is risk-free |
| **Stage 3** | 2.0R or 3:25 PM | 55% | Exit runner | Position fully closed |

### Why 25/20/55 Instead of 25/50/25?

The old split (25/50/25) closed 50% at 1R, leaving only 25% to run. The new split:
- **Keeps 55% riding** after breakeven → captures significantly more from big moves
- After Stage 2, the remaining position is **risk-free** (SL = entry), so letting 55% ride costs nothing
- On a 3R move: old strategy captures ~1.125R average, new strategy captures ~1.775R average (+58% more profit on runners)

### Small Quantity Handling

For positions with very few shares (1–3), the bot has special logic:

| Total Qty | Stage 1 | Stage 2 | Stage 3 |
|-----------|---------|---------|---------|
| 1 share | 1 | 0 | 0 |
| 2 shares | 1 | 1 | 0 |
| 3 shares | 1 | 1 | 1 |
| 4+ shares | 25% | 20% | 55% |

Rounding remainders are distributed to Stage 3 (the runner) to maximize profit potential.

---

## 6. Multi-Stock Mode & Confidence Scoring

When `MULTI_STOCK_MODE = True`, the bot scans up to 20 stocks simultaneously and allocates capital based on a **7-factor confidence score**.

### 6.1 Signal Scanning

```
For each of 50 NIFTY stocks (capped at MAX_STOCKS_TO_SCAN = 20):
  ├── Fetch 15-min opening candle → calculate triggers
  ├── Every 30s: fetch 5-min candle, check breakout
  ├── If breakout: run all filters
  ├── If passes: calculate confidence score (0.0 → 1.0)
  └── Collect all valid signals → allocate capital proportionally
```

### 6.2 Confidence Score (7 Factors)

| # | Factor | Weight | Scoring Logic |
|---|--------|--------|--------------|
| 1 | **Volume** | 20% | 1.5x avg = 0.5, 3x avg = 1.0 |
| 2 | **Breakout Strength** | 20% | How far past trigger (0.5% = 0.5, 1%+ = 1.0) |
| 3 | **NIFTY Alignment** | 15% | Index trending same direction |
| 4 | **Gap Alignment** | 15% | Gap direction matches signal |
| 5 | **Trend** | 10% | 15-min VWAP confirms direction |
| 6 | **Open Bias** | 10% | Candle structure confirms direction |
| 7 | **Volatility (ATR)** | 10% | Ideal ATR 0.5-2% of price |

**Total = 1.0** (100%)

### 6.3 Capital Allocation

```python
# Confidence-proportional allocation with guardrails:
MIN_ALLOCATION = 10% of capital  # No micro-positions
MAX_ALLOCATION = 40% of capital  # No over-concentration
MAX_POSITIONS  = 5 simultaneous  # Portfolio diversification
MIN_CONFIDENCE = 0.40            # Minimum score to trade

# Example: 3 signals with scores 0.8, 0.6, 0.5
# Normalized weights: 0.42, 0.31, 0.26
# With ₹80,000 effective capital:
#   Stock A: ₹33,600 (42%)
#   Stock B: ₹24,800 (31%)
#   Stock C: ₹20,800 (26%) → clamped to ₹20,800 (≥ MIN 10%)
```

---

## 7. Auto-Login System

Zerodha's access token expires every 24 hours. The bot includes a **fully automated login system** that handles this without manual intervention.

### 7.1 How It Works

```
┌──────────────────────────────────────────────────────────┐
│                  kite_session.py                          │
│                                                          │
│  get_kite_session()                                      │
│    │                                                     │
│    ├─ 1. Check in-memory cache (valid for 1 hour)        │
│    │     └─ If fresh → return immediately                │
│    │                                                     │
│    ├─ 2. Read access_token.txt                           │
│    │     └─ Validate with kite.profile()                 │
│    │     └─ If valid → cache & return                    │
│    │                                                     │
│    ├─ 3. Read KITE_ACCESS_TOKEN from .env                │
│    │     └─ Validate → cache & return                    │
│    │                                                     │
│    └─ 4. Trigger auto-login (kite_login.py)              │
│          └─ 5-step browser-less login                    │
│          └─ Save new token → cache & return              │
└──────────────────────────────────────────────────────────┘
```

### 7.2 5-Step Login Process (`kite_login.py`)

| Step | Action | Detail |
|------|--------|--------|
| 1 | Load login page | `GET kite.trade/connect/login` → establishes session cookies |
| 2 | POST credentials | `POST kite.zerodha.com/api/login` with `user_id` + `password` |
| 3 | POST TOTP | `POST kite.zerodha.com/api/twofa` with `pyotp.TOTP(key).now()` |
| 4 | Capture redirect | `GET` login URL with `allow_redirects=False` → extract `request_token` from `Location` header |
| 5 | Exchange token | `kite.generate_session(request_token, api_secret)` → get `access_token` |

The token is saved to `access_token.txt` and cached in memory for 1 hour.

### 7.3 Dashboard Refresh Button

The frontend dashboard has a **🔑 Refresh Login** button that calls `POST /api/kite/auto-login` to force a fresh token generation.

---

## 8. Risk Management

### 8.1 Capital Guardrails

```
STARTING_CAPITAL = ₹20,000
       × LEVERAGE = 5x (MIS intraday)
       = ₹100,000 effective

HARDSTOP_UTILIZATION = 80%
       = ₹80,000 maximum deployed

MARGIN_UTILIZATION = 85%
       = ₹68,000 per trade (single stock)
       = split across positions (multi-stock)
```

### 8.2 Loss Limits

| Protection | Setting | Behavior |
|-----------|---------|---------|
| **Daily Loss Limit** | 2% of capital (₹400) | Auto-closes all positions, stops trading for the day |
| **Per-Trade SL** | 50% of calculated risk | Tighter than standard ORB stop loss |
| **Breakeven Lock** | After 1R profit | SL moves to entry price — remaining position is risk-free |
| **Auto-Exit** | 3:25 PM IST | Closes all MIS positions before market close |
| **ATR Trailing** | After 1.5R | Trailing stop follows price using 1.2 × ATR |

### 8.3 Order Safety

- **Smart Limit Orders**: Uses stop-limit orders instead of market orders (`LIMIT_ORDER_BUFFER = ₹0.20`)
- **Order Timeout**: Converts to market order if limit not filled within 30 seconds
- **Rate Limiting**: Built-in API rate limiter in `kite_service.py` with exponential backoff
- **Quote Caching**: Reduces API calls with TTL-based quote cache

---

## 9. Frontend Dashboard

The React frontend provides 6 pages:

| Page | Route | Purpose |
|------|-------|---------|
| **Dashboard** | `/` | Bot status, P&L summary, quick controls, 🔑 Refresh Login |
| **Portfolio** | `/portfolio` | Trade history, open positions, performance metrics |
| **Market Watch** | `/market-watch` | Live stock prices, watchlist |
| **Trading Monitor** | `/trading-monitor` | Real-time trade execution monitoring |
| **Live Terminal** | `/terminal` | Streaming bot logs (like a CLI in the browser) |
| **API Tester** | `/api-tester` | Manual API endpoint testing tool |

### Key Frontend Features

- **JWT Authentication** — Token stored in `localStorage`, auto-redirect on 401
- **Axios Interceptors** — Auto-attaches Bearer token to every request
- **Real-time Updates** — Polling-based dashboard refresh
- **Responsive Design** — CSS Grid/Flexbox layout

---

## 10. Backend API

The Flask backend (`backend/app.py`) exposes these endpoint groups:

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create new user account |
| POST | `/api/auth/login` | Login → JWT token |

### Bot Control
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/bot/start` | Start the trading bot |
| POST | `/api/bot/stop` | Stop the trading bot |
| GET | `/api/bot/status` | Get bot running state |

### Kite Integration
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/kite/login` | Initiate Kite OAuth flow |
| POST | `/api/kite/auto-login` | Trigger automated login (TOTP) |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/today` | Today's P&L and stats |
| GET | `/api/analytics/weekly` | Weekly performance |
| GET | `/api/analytics/trades` | Trade history (paginated) |
| GET | `/api/analytics/performance` | Overall performance metrics |

### Database Models

```
User ──┬── Trade (one-to-many)
       ├── Session (one-to-many)
       └── DailyStats (one-to-many)

Trade: symbol, side, entry_price, exit_price, quantity, pnl, status, timestamps
BotLog: timestamp, message, level (for terminal streaming)
```

---

## 11. Configuration Reference

All configurable parameters live in `app_files/config.py`. Here are the key categories:

### Capital & Leverage
| Parameter | Default | Description |
|-----------|---------|-------------|
| `STARTING_CAPITAL` | ₹20,000 | Base trading capital |
| `LEVERAGE` | 5x | MIS intraday leverage |
| `HARDSTOP_CAPITAL` | ₹20,000 | Absolute maximum capital |
| `HARDSTOP_UTILIZATION` | 80% | % of hardstop to actually use |
| `MARGIN_UTILIZATION` | 85% | % of available margin per trade |

### Multi-Stock Mode
| Parameter | Default | Description |
|-----------|---------|-------------|
| `MULTI_STOCK_MODE` | `True` | Enable portfolio mode |
| `MAX_POSITIONS` | 5 | Max simultaneous trades |
| `MAX_STOCKS_TO_SCAN` | 20 | Stocks to scan from NIFTY 50 |
| `MIN_ALLOCATION_PCT` | 10% | Min capital per stock |
| `MAX_ALLOCATION_PCT` | 40% | Max capital per stock |
| `MIN_CONFIDENCE_SCORE` | 0.40 | Min score to trade |

### Entry Filters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `USE_DYNAMIC_ATR_BUFFER` | `True` | ATR-based trigger buffer |
| `USE_VOLUME_FILTER` | `True` | Require volume confirmation |
| `USE_NIFTY_FILTER` | `True` | Check NIFTY 50 alignment |
| `USE_TREND_FILTER` | `True` | 15-min VWAP trend check |
| `USE_GAP_FILTER` | `True` | Gap direction filter |
| `USE_OPEN_POSITION_FILTER` | `True` | Candle structure filter |
| `USE_RETEST_ENTRY` | `True` | Wait for breakout retest |

### Exit Strategy (25/20/55 Split)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `PARTIAL_BOOKING_FIRST_CLOSE_PCT` | 25% | Exit at 0.5R |
| `PARTIAL_BOOKING_SECOND_CLOSE_PCT` | 20% | Exit at 1.0R + SL → breakeven |
| `PARTIAL_BOOKING_EOD_CLOSE_PCT` | 55% | Runner — exit at 2R or 3:25 PM |
| `STOPLOSS_DISTANCE_FACTOR` | 0.5 | SL 50% tighter than normal |
| `ATR_TRAIL_MULTIPLIER` | 1.2 | ATR trailing distance |
| `ATR_TRAIL_START_R` | 1.5R | Start trailing after 1.5R |

### Risk Limits
| Parameter | Default | Description |
|-----------|---------|-------------|
| `DAILY_LOSS_LIMIT_PCT` | 2% | Max daily loss (auto-shutdown) |
| `MAX_TRADES_PER_DAY` | 999 | Effectively unlimited |
| `PRIMARY_ENTRY_END` | 10:15 | End of primary window |
| `NO_ENTRY_AFTER` | 10:45 | Hard stop for new entries |

---

## 12. Setup & Installation

### Prerequisites

- **Python 3.9+**
- **Node.js 18+** (for frontend)
- **PostgreSQL** (production) or SQLite (development)
- **Zerodha Kite Connect** developer account ([kite.trade](https://kite.trade))

### Step 1: Clone the Repository

```bash
git clone https://github.com/aayushparikh22/my-trading-bot.git
cd my-trading-bot
```

### Step 2: Backend Setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Install backend dependencies
pip install -r backend/requirements.txt
pip install -r app_files/requirements.txt
```

### Step 3: Frontend Setup

```bash
cd frontend
npm install
cd ..
```

### Step 4: Environment Variables

Create a `.env` file in the project root:

```env
# Kite Connect API (from https://developers.kite.trade)
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_ACCESS_TOKEN=your_initial_token

# Auto-Login (enables 24/7 unattended operation)
KITE_AUTO_LOGIN=true
KITE_USER_ID=your_zerodha_user_id
KITE_PASSWORD=your_zerodha_password
KITE_TOTP_KEY=your_totp_secret_key

# Backend
SECRET_KEY=your_jwt_secret
DATABASE_URL=sqlite:///trading.db
```

> **Getting your TOTP Key**: In Zerodha → My Profile → Security → Two-Factor Auth → scan the QR code with a TOTP app that shows the secret key (e.g., Aegis, 2FAS), or extract it from the QR's `otpauth://` URI.

### Step 5: Initialize Database

```bash
cd backend
python -c "from app import app, db; app.app_context().push(); db.create_all(); print('DB created')"
cd ..
```

---

## 13. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KITE_API_KEY` | ✅ | Kite Connect API key |
| `KITE_API_SECRET` | For auto-login | Kite Connect API secret |
| `KITE_ACCESS_TOKEN` | Initial only | Manual token (auto-login replaces this) |
| `KITE_AUTO_LOGIN` | ❌ | Set `true` for automated token refresh |
| `KITE_USER_ID` | For auto-login | Zerodha user ID (e.g., AB1234) |
| `KITE_PASSWORD` | For auto-login | Zerodha login password |
| `KITE_TOTP_KEY` | For auto-login | TOTP secret for 2FA |
| `SECRET_KEY` | ✅ | JWT signing secret |
| `DATABASE_URL` | ❌ | Database URL (default: SQLite) |
| `KITE_DEBUG` | ❌ | Enable Kite API debug logging |

---

## 14. Running the Bot

### Development (manual start)

```bash
# Terminal 1: Start backend
cd backend
python app.py
# → Runs on http://localhost:5000

# Terminal 2: Start frontend
cd frontend
npm start
# → Runs on http://localhost:3000

# Terminal 3: Test auto-login
cd app_files
python kite_login.py
```

### Production

Use the dashboard **Start Bot** button or call:

```bash
curl -X POST http://localhost:5000/api/bot/start \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Bot Execution Flow

```
1. TradingService.start_bot()
2. → Validates/refreshes Kite session (auto-login if needed)
3. → Creates BotKite instance with validated credentials
4. → Calls bot.run_trading_day()
5.   → get_symbols_setup_data()     ← Fetches candles, calculates triggers
6.   → Signal scanning loop          ← 30-second polling
7.   → If signal found:
8.     → place_buy_order() or place_sell_order()
9.     → Enter monitoring loop
10.    → Execute 3-stage exit strategy
11.  → generate_final_report()
```

---

## 15. Deployment

### Recommended: AWS Lightsail (₹400–850/month)

| Plan | vCPU | RAM | Cost |
|------|------|-----|------|
| **$3.50/mo** | 1 | 512MB | ₹290 — minimal (bot only) |
| **$5/mo** ⭐ | 1 | 1GB | ₹420 — recommended |
| **$10/mo** | 1 | 2GB | ₹850 — with full frontend |

### Deployment Steps

```bash
# 1. SSH into your VM
ssh ubuntu@your-vm-ip

# 2. Clone & setup
git clone https://github.com/aayushparikh22/my-trading-bot.git
cd my-trading-bot
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
pip install -r app_files/requirements.txt

# 3. Create .env with your credentials
nano .env

# 4. Run with systemd (auto-restart)
sudo nano /etc/systemd/system/trading-bot.service
```

**Systemd service file:**
```ini
[Unit]
Description=Trading Bot Backend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/my-trading-bot/backend
Environment=PATH=/home/ubuntu/my-trading-bot/venv/bin
ExecStart=/home/ubuntu/my-trading-bot/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

### Key Deployment Notes

- The bot auto-logs in at market open (~9:15 AM IST) via the session manager
- All MIS positions are auto-closed by 3:25 PM IST
- The bot generates a daily report after market close
- Consider setting up cron to restart the bot process daily at 9:00 AM IST

---

## ⚠️ Disclaimer

This bot is for **educational and personal use only**. Trading in the stock market involves significant risk:

- Past performance does not guarantee future results
- Automated trading can amplify both gains AND losses
- Always test with paper trading / small capital first
- The author is not responsible for any financial losses

---

*Built with Python, React, and the Zerodha Kite Connect API.*
