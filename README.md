# 🤖 ORB Scalping Trading Bot — Complete Documentation

> **Automated rule-based intraday trading bot** for the Indian stock market (NSE) using the **Opening Range Breakout (ORB)** strategy with VWAP confirmation, multi-stock portfolio management, and confidence-based capital allocation — powered by the [Zerodha Kite Connect API](https://kite.trade).
>
> *Note: This bot is entirely rule-based — no machine learning or trained models are used. The confidence scoring system is a hand-tuned weighted formula, not a learned model.*

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
11. [Backtesting Framework](#11-backtesting-framework)
12. [Configuration Reference](#12-configuration-reference)
13. [Setup & Installation](#13-setup--installation)
14. [Environment Variables](#14-environment-variables)
15. [Running the Bot](#15-running-the-bot)
16. [Deployment](#16-deployment)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      REACT FRONTEND (:3000)                         │
│  Dashboard │ Portfolio │ Market Watch │ Trading Monitor │ Terminal  │
│  (Recharts charts, auto-refresh, manual trade entry, API tester)   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ REST API (axios + fetch)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FLASK BACKEND (:5000)                             │
│  Auth │ Bot Control │ Analytics │ Kite OAuth │ Trade CRUD           │
│  Manual Trade/Exit │ Portfolio │ Watchlist │ Trade Reconciliation    │
│                            │                                        │
│              ┌─────────────┴─────────────┐                          │
│              ▼                           ▼                          │
│     TradingService              SQLAlchemy (PostgreSQL/SQLite)       │
│     (bot lifecycle)             Users/Trades/Logs/Stats/Sessions     │
└──────────────┬──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BOT ENGINE (app_files/)                           │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐          │
│  │  bot_kite.py  │  │ kite_service │  │   config.py      │          │
│  │  (3500+ lines)│  │  (580 lines) │  │  (360 lines)     │          │
│  │  40+ methods  │  │  25+ methods │  │  (all params)    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘          │
│         │                 │                                          │
│         ▼                 ▼                                          │
│  ┌────────────────────────────────────┐                             │
│  │   Zerodha Kite Connect API         │                             │
│  │   (Orders, Quotes, Historical)     │                             │
│  └────────────────────────────────────┘                             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │ kite_login.py │  │kite_session.py│  ← Auto-Login System          │
│  │ (5-step auth) │  │(token manager)│                               │
│  └──────────────┘  └──────────────┘                                 │
└─────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BACKTESTING ENGINE (backtest/)                    │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐          │
│  │run_backtest.py│  │optimize_     │  │ analyze_results  │          │
│  │(1020 lines)   │  │params.py     │  │    .py           │          │
│  │Full simulator │  │(500 lines)   │  │ Deep diagnostics │          │
│  └──────┬───────┘  │810-combo grid │  └──────────────────┘          │
│         │          └──────────────┘                                  │
│         ▼                                                            │
│  ┌────────────────┐  ┌────────────────┐                             │
│  │download_data.py │  │ data/*.json    │  10 stocks × 2 intervals   │
│  │ (Kite hist API) │  │ results/*.csv  │  3 months of candle data   │
│  └────────────────┘  └────────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
```

**Tech Stack:**

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, React Router 6, Axios, Recharts, Tailwind CSS |
| Backend | Python Flask 2.3, Flask-SQLAlchemy, Flask-CORS, PyJWT |
| Database | PostgreSQL (production) / SQLite (dev) |
| Broker API | Zerodha Kite Connect SDK (`kiteconnect==4.2.0`) |
| Auth | JWT tokens, TOTP 2FA via `pyotp` |
| Backtesting | Custom Python engine with parameter optimization |

---

## 2. Project Structure

```
Trading-bot/
├── app_files/                  # Core bot engine
│   ├── bot_kite.py             # Main trading algorithm (3500+ lines, 40+ methods)
│   ├── config.py               # All strategy parameters & configuration (360 lines)
│   ├── kite_service.py         # Kite API wrapper with caching & rate limiting (580 lines)
│   ├── kite_login.py           # Automated 5-step Kite login (TOTP 2FA)
│   ├── kite_session.py         # Session manager with token persistence
│   └── requirements.txt        # Python dependencies (bot)
│
├── backend/                    # Flask REST API
│   ├── app.py                  # API endpoints (1800+ lines, 25+ routes)
│   ├── models.py               # SQLAlchemy models (User, Trade, DailyStats, Session, BotLog)
│   ├── trading_service.py      # Bot lifecycle manager (thread-based)
│   ├── trigger_cache.json      # Persisted opening range triggers
│   └── requirements.txt        # Python dependencies (backend)
│
├── frontend/                   # React dashboard
│   ├── src/
│   │   ├── App.jsx             # Router setup (6 routes)
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx   # Main dashboard — bot controls, P&L charts, Refresh Login
│   │   │   ├── Portfolio.jsx   # Holdings breakdown, P&L, pie/bar charts
│   │   │   ├── MarketWatch.jsx # Live prices for all 50 NIFTY stocks with trigger levels
│   │   │   ├── TradingMonitor.jsx  # Real-time trade monitoring with mini candle charts
│   │   │   ├── LiveTerminalPage.jsx # Streaming bot logs (terminal-style)
│   │   │   └── APITesterPage.jsx   # API health checker wrapper
│   │   ├── components/
│   │   │   ├── APITester.jsx   # API health-check runner (6 endpoint tests)
│   │   │   └── LiveTerminal.jsx # Log viewer + live prices + manual trade entry form
│   │   └── services/
│   │       └── api.js          # Centralized Axios client with JWT interceptors
│   └── package.json
│
├── backtest/                   # Backtesting framework
│   ├── run_backtest.py         # Full strategy backtester (1020 lines)
│   ├── optimize_params.py      # Parameter grid search optimizer (500 lines, 810 combos)
│   ├── analyze_results.py      # Deep trade analysis & diagnostics
│   ├── download_data.py        # Historical data downloader from Kite API
│   ├── data/                   # Downloaded candle data (10 stocks × 5min + 15min)
│   │   ├── HDFCBANK_5min.json, HDFCBANK_15min.json
│   │   ├── RELIANCE_5min.json, RELIANCE_15min.json
│   │   ├── ... (10 stock pairs + NIFTY50 + manifest.json)
│   └── results/                # Backtest output
│       ├── backtest_results.json
│       ├── equity_curve.csv
│       └── trades.csv
│
├── .env                        # Credentials (gitignored)
├── access_token.txt            # Cached Kite token (auto-managed)
├── trigger_cache.json          # Opening range trigger persistence
└── README.md
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
  │   • Calculate dynamic ATR buffer (0.15 × ATR(10))
  │   • Calculate gap % from previous close
  │   • Calculate open-position bias
  │   • Set triggers: Long = High + Buffer, Short = Low - Buffer
  │   • Lock triggers in cache (persisted to trigger_cache.json)
  │
09:30 ──── Primary Entry Window Opens ──────────────────────────
  │
  │   PHASE 2: SIGNAL SCANNING (09:30 → 10:30)
  │   • Poll 5-minute candles every 30 seconds
  │   • Check each symbol for breakout conditions
  │   • Apply all filters (Volume, NIFTY, Trend, Gap, Open Bias)
  │   • Calculate 7-factor confidence score
  │   • Execute trade when signal passes all filters
  │
  │   09:30-10:15  PRIMARY WINDOW   → Normal entry rules
  │   10:15-10:30  SOFT CUTOFF      → Extra confirmation needed (2x volume)
  │   10:30+       HARD STOP        → No new entries allowed
  │
10:30 ──── Entry Window Closes ─────────────────────────────────
  │
  │   PHASE 3: POSITION MANAGEMENT (until 15:25)
  │   • Monitor live price every 10 seconds
  │   • Execute 3-stage partial booking exits
  │   • Trail stop loss using ATR (after 1.5R)
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
          AND
NIFTY 50 is below its own VWAP (hard requirement)
```

> **Backtest insight**: SHORT trades with `open_bias=SHORT` had a 28% win rate and lost ₹313 — all trades where the open bias is SHORT are now skipped entirely (`SKIP_OPEN_BIAS_SHORT = True`).

### 3.3 Stop Loss Calculation

The bot uses a **dynamic stop loss** with the full risk distance (backtest-optimized):

```python
# Standard ORB SL = VWAP or Candle Low/High
# STOPLOSS_DISTANCE_FACTOR = 1.0 (full range — gives trades maximum room)

risk = abs(entry_price - standard_sl)
actual_sl = entry_price - (risk * 1.0)   # For LONG
actual_sl = entry_price + (risk * 1.0)   # For SHORT
```

> **Backtest insight**: `SL=1.0` was the single biggest improvement — +₹1,320 vs +₹339 at `SL=0.75`. Giving trades the full range to develop dramatically reduced premature stop-outs.

---

## 4. Signal Filters & Enhancements

Every breakout signal must pass through a **cascade of filters** before becoming a trade. Each filter can independently skip a signal:

### Filter Pipeline (in order)

```
Breakout Detected (price > trigger + above VWAP)
    │
    ├── ① Entry Window Filter ── Is it within 09:30-10:30?
    │                             (SOFT window 10:15-10:30 needs 2x volume)
    │
    ├── ② Volume Confirmation ── Is current volume > 1.0× average?
    │                             (time-of-day adjusted: 1.2× early, 0.8× late)
    │
    ├── ③ Gap Alignment ──────── Does pre-market gap support direction?
    │                             LONG: skip if gap < -0.3%
    │                             SHORT: skip if gap > +0.3%
    │
    ├── ④ Open Position Bias ─── Does candle structure confirm direction?
    │                             LONG: skip if open near candle high (SHORT bias)
    │                             SHORT: SKIP ALL (open_bias=SHORT is toxic)
    │
    ├── ⑤ NIFTY Index Filter ── Is NIFTY 50 trending in same direction?
    │                             Soft bias for LONG, hard block for SHORT
    │
    ├── ⑥ Trend Filter ──────── Is 15-min VWAP trending with signal?
    │
    ├── ⑦ Range Quality ──────── Is opening range 0.1%-2.5% of price?
    │                             (Rejects too narrow/wide ranges)
    │
    ├── ⑧ Retest Confirmation ── Did price retest the breakout level?
    │                             (Max 3 candles to wait for retest)
    │
    └── ⑨ Liquidity Filter ──── Is daily volume > 500K shares?
                                  (Currently disabled to save API calls)
```

### 4.1 Gap Alignment Filter

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

### 4.2 Open Position Bias Filter

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
| SHORT (open near high) | ❌ **SKIP ALL** ⛔ | ❌ **SKIP ALL** ⛔ |

> **Backtest insight**: `SKIP_OPEN_BIAS_SHORT = True` — when the opening candle has a SHORT bias (open near high), ALL trades are skipped regardless of direction, as this pattern had only 28% win rate.

### 4.3 Symbol Focus (Backtest-Validated)

The bot focuses on the **top 6 highest-performing NIFTY 50 stocks** and excludes underperformers:

```python
FOCUS_SYMBOLS = ["INFY", "RELIANCE", "TCS", "HDFCBANK", "BAJFINANCE", "SBIN"]
EXCLUDED_SYMBOLS = ["ITC", "TATASTEEL", "AXISBANK", "ICICIBANK"]
```

> **Backtest insight**: Top 6 symbols with optimized params = +34.7% return on ₹20K capital.

---

## 5. Exit Strategy — 3-Stage Partial Booking

The bot uses a **"Let Winners Run"** exit strategy that books profits in three stages while maximizing the runner portion:

```
                                ┌─── STAGE 3: Exit 55% at 2.5R or 3:25 PM ──┐
                                │    (Runner — risk-free after Stage 2)      │
                                │                                            │
                    ┌───────────┤                                            │
                    │ STAGE 2   │                                            │
                    │ Exit 20%  │     55% riding with SL at entry           │
                    │ at 1.0R   │     (GUARANTEED — can't lose)              │
         ┌──────────┤           │                                            │
         │ STAGE 1  │  SL moves │                                            │
         │ Exit 25% │  to ENTRY │                                            │
         │ at 1.0R  │    ↕      │                                            │
    ─────┤          │           │                                            │
  ENTRY  │          │           │                                            │
    ─────┤──────────┤───────────┤────────────────────────────────────────────┤
         │    SL    │           │                                      3:25 PM
         │  (full)  │           │
         └──────────┘           │
              ↑                 │
        Initial SL              2.5R Target or EOD
     (100% of risk)
```

### Stage Breakdown

| Stage | R-Multiple | % of Position | Action | After Exit |
|-------|-----------|--------------|--------|-----------|
| **Stage 1** | 1.0R | 25% | Book quick profit | SL stays at original, 75% still running |
| **Stage 2** | 1.0R | 20% | Lock 1:1 RR profit | **SL moves to entry** → remaining 55% is risk-free |
| **Stage 3** | 2.5R or 3:25 PM | 55% | Exit runner (ATR-trailed) | Position fully closed |

> **Backtest optimization**: First target moved from 0.5R → 1.0R. This lets trades breathe longer and improves overall win rate. The profit target ratio was also increased from 2.0R → 2.5R to let runners go further.

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
  ├── Filter by FOCUS_SYMBOLS / EXCLUDED_SYMBOLS
  ├── Fetch 15-min opening candle → calculate triggers
  ├── Every 30s: fetch 5-min candle, check breakout
  ├── If breakout: run all filters (9-stage pipeline)
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
MAX_POSITIONS  = 2 simultaneous  # Concentrated capital (optimized from 5)
MIN_CONFIDENCE = 0.40            # Minimum score to trade

# Example: 2 signals with scores 0.8, 0.6
# Normalized weights: 0.57, 0.43
# With ₹80,000 effective capital:
#   Stock A: ₹45,600 (57%) → clamped to ₹32,000 (MAX 40%)
#   Stock B: ₹34,400 (43%) → clamped to ₹32,000 (MAX 40%)
```

> **Backtest insight**: `MAX_POSITIONS = 2` concentrates capital better than 5 positions, producing higher per-trade returns.

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

The frontend dashboard has a **🔑 Refresh Login** button that calls `POST /api/kite/auto-login` to force a fresh token generation. The backend also auto-refreshes the token when starting the bot if auto-login is configured.

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
       = split across 2 positions max (multi-stock)
```

### 8.2 Loss Limits

| Protection | Setting | Behavior |
|-----------|---------|---------|
| **Daily Loss Limit** | 2% of capital (₹400) | Auto-closes all positions, stops trading for the day |
| **Per-Trade SL** | 100% of calculated risk | Full range SL (backtest-optimized from 50%) |
| **Breakeven Lock** | After 1R profit | SL moves to entry price — remaining 55% is risk-free |
| **Auto-Exit** | 3:25 PM IST | Closes all MIS positions before market close |
| **ATR Trailing** | After 1.5R | Trailing stop follows price using 1.2 × ATR |
| **Position Restoration** | On bot restart | Restores active positions from broker to resume SL monitoring |

### 8.3 Order Safety

- **Smart Limit Orders**: Uses stop-limit orders instead of market orders (`LIMIT_ORDER_BUFFER = ₹0.20`)
- **Order Timeout**: Converts to market order if limit not filled within 30 seconds
- **Rate Limiting**: Built-in API rate limiter in `kite_service.py` (1s between calls, 10s backoff on rate limit)
- **Quote Caching**: 5-second TTL quote cache, instrument cache (1 hour), batch quotes (up to 500 in one call)
- **Trade Reconciliation**: Backend auto-detects when SL/TP orders fill on the exchange, closes trade in DB, and cancels the opposite exit order (handles race conditions where both SL+TP fill)

---

## 9. Frontend Dashboard

The React frontend provides 6 pages with auto-refreshing data:

| Page | Route | Purpose | Refresh |
|------|-------|---------|---------|
| **Dashboard** | `/` | Bot controls, P&L summary, cumulative P&L line chart, win/loss pie chart, daily bar chart, settings modal, 🔑 Refresh Login | 5s |
| **Portfolio** | `/portfolio` | Holdings breakdown with investment/current/P&L, summary cards, holdings distribution pie chart, per-stock P&L bar chart | 30s |
| **Market Watch** | `/market-watch` | Live prices for all monitored NIFTY 50 stocks, OHLC data, trigger levels (buy/sell), signal status (LONG/SHORT/NEUTRAL) | 3s |
| **Trading Monitor** | `/trading-monitor` | Open positions with real-time mini line + candle charts, unrealized P&L, manual exit with confirmation modal, watchlist grid | 5s |
| **Live Terminal** | `/terminal` | Streaming bot logs with color-coded entries (error/warning/trade/success), filter by type, live price monitor, **manual trade entry form** (BUY/SELL with SL% and TP ratio) | 2s (logs), 3s (prices) |
| **API Tester** | `/api-tester` | API health checker — runs 6 endpoint tests (profile, quote, orders, positions, holdings, balance), shows pass/fail with response details | Manual |

### Key Frontend Features

- **JWT Authentication** — Token stored in `localStorage`, auto-redirect on 401
- **Axios Interceptors** — Auto-attaches Bearer token to every request
- **Real-time Updates** — Polling-based refresh at page-specific intervals
- **Charts** — Recharts library: line charts (cumulative P&L), bar charts (daily P&L, per-stock), pie charts (win/loss, holdings)
- **Manual Trading** — Place manual BUY/SELL orders with auto SL + TP bracket orders from the Live Terminal
- **Manual Exit** — Close open positions directly from Trading Monitor with confirmation
- **Custom Candle Chart** — SVG mini-candle chart with 15-second aggregation in Trading Monitor

---

## 10. Backend API

The Flask backend (`backend/app.py`, 1800+ lines) exposes 25+ endpoints:

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create new user account with trading config |
| POST | `/api/auth/login` | Login → JWT token |
| POST | `/api/auth/logout` | Logout |

### Bot Control
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/bot/start` | Start the trading bot (background thread) |
| POST | `/api/bot/stop` | Stop the trading bot (graceful shutdown) |
| GET | `/api/bot/status` | Get bot running state and live data |

### Kite Integration
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/kite/login` | Get Kite Connect OAuth login URL |
| GET | `/api/kite/callback` | Handle OAuth callback, store access token |
| POST | `/api/kite/auto-login` | Trigger automated TOTP login to refresh token |

### Trading
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/manual-trade` | Place manual trade with auto SL + TP bracket orders |
| POST | `/api/manual-exit` | Manually exit open position, cancel linked SL/TP |
| POST | `/api/orders/cancel` | Cancel an open order by order ID |

### Portfolio & Market Data
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/portfolio/holdings` | Holdings with P&L and performance metrics |
| GET | `/api/portfolio/positions` | Open intraday positions |
| GET | `/api/market/watchlist` | Batch live data for all monitored symbols (5s cache) |
| GET | `/api/market/live` | Live data with trigger levels for a specific symbol |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/today` | Today's P&L and stats (includes live open P&L) |
| GET | `/api/analytics/weekly` | Last 7 days with daily breakdown |
| GET | `/api/analytics/trades` | Trade history with date/status filtering & pagination |
| GET | `/api/analytics/performance` | 30-day metrics (win rate, profit factor, Sharpe, etc.) |

### Configuration & Logs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get user trading configuration |
| PUT | `/api/config` | Update config (trading params + Kite credentials) |
| GET | `/api/logs` | Get bot logs with type/level filtering |
| GET | `/api/health` | Health check |

### Key Backend Features

- **Trade Reconciliation**: Auto-detects SL/TP fills on exchange, closes trades in DB, cancels opposite orders (debounced to 30s per user)
- **Trigger Cache**: Opening range triggers locked at 9:30 AM, persisted to `trigger_cache.json` for restart resilience
- **Dynamic ATR Buffer**: Calculates ATR-based buffer for market data endpoints (matches bot logic)
- **Default User Mode**: Single-user setup with auto-created default account
- **Watchlist Batching**: Single Kite API call for all symbols with 5s TTL cache

### Database Models

```
User ──┬── Trade (one-to-many)
       ├── Session (one-to-many)
       ├── DailyStats (one-to-many)
       └── BotLog (via user_id)

User: email, password, capital/leverage config, Kite credentials, bot_active
Trade: symbol, side, entry/exit price, quantity, SL/TP prices, pnl, status, order IDs, notes
DailyStats: date, total/winning/losing trades, win_rate, total_pnl, largest win/loss
Session: session_token, created/expires timestamps, is_active
BotLog: log_type, message, log_level, timestamp, trade_id (optional)
```

---

## 11. Backtesting Framework

The project includes a complete backtesting suite that validates the strategy on historical data.

### 11.1 Data Pipeline

```bash
python backtest/download_data.py
```

Downloads 5-minute and 15-minute intraday candles from Kite Connect API for the **top 10 NIFTY 50 stocks** covering the last 3 months. Data is saved as JSON files in `backtest/data/`.

**Stocks downloaded**: HDFCBANK, RELIANCE, ICICIBANK, SBIN, TATASTEEL, INFY, TCS, AXISBANK, BAJFINANCE, ITC + NIFTY50 index

### 11.2 Backtester (`run_backtest.py`)

Simulates the **exact trading algorithm** from `bot_kite.py` on historical data:

- Opening range breakout (15-min candle high/low)
- VWAP confirmation
- Dynamic ATR buffer (0.15 × ATR(10))
- Volume confirmation (time-of-day adjusted)
- Gap alignment filter
- Open position bias filter (with `SKIP_OPEN_BIAS_SHORT`)
- 3-stage partial booking exit (25/20/55 split)
- ATR trailing stop loss
- Entry window (09:30-10:30 with soft cutoff at 10:15)
- Range quality filter
- Daily loss limit (2%)

**Outputs** (in `backtest/results/`):
- `backtest_results.json` — Complete results with per-symbol and per-stage analysis
- `trades.csv` — All individual trades
- `equity_curve.csv` — Daily equity progression

### 11.3 Parameter Optimizer (`optimize_params.py`)

Runs a **grid search** across 11 parameter dimensions to find optimal configuration:

| Parameter | Values Tested |
|-----------|--------------|
| Symbol selection | All 10, Top 8, Top 6, Top 5, Top 3 |
| SL distance factor | 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0 |
| Entry window cutoff | 9:45, 10:00, 10:15, 10:30, 10:45, 11:00 |
| Max positions | 1, 2, 3, 5, 8, 10 |
| Profit target (R) | 1.5, 2.0, 2.5, 3.0, 4.0 |
| Volume multiplier | 0.8, 1.0, 1.2, 1.5, 2.0 |
| ATR buffer multiplier | 0.1, 0.15, 0.2, 0.3, 0.5, 0.7 |
| Short side options | No shorts, NIFTY required, Free |
| First partial target | 0.5R, 0.75R, 1.0R, 1.25R |
| Gap filter | On / Off |
| Skip OpenBias SHORT | True / False |

**MEGA sweep**: 5 SL × 3 Window × 3 Target × 2 FirstT × 3 ATR × 3 MaxPos = **810 combinations**

Each combination reports: PnL (₹ + %), trade count, win rate, profit factor, max drawdown, avg win/loss.

### 11.4 Results Analyzer (`analyze_results.py`)

Deep diagnostic analysis of backtest trades:
- **Trade outcome breakdown**: Pure SL, Partial + SL, Full winners
- **Entry hour analysis**: Win rate and P&L by hour of day
- **Gap + direction analysis**: Aligned vs contradicting gap performance
- **Open bias analysis**: LONG/SHORT/NEUTRAL bias win rates
- **Holding time**: Average, median, winners vs losers duration
- **Monthly breakdown**: P&L by month
- **Per-symbol performance**: Individual stock analysis

### 11.5 Key Backtest Results

The optimized parameters currently in `config.py` were derived from backtesting:

| Metric | Value |
|--------|-------|
| **SL Distance Factor** | 1.0 (full range — biggest single improvement) |
| **Entry Window** | 09:30-10:30 (extended from 10:15) |
| **First Partial Target** | 1.0R (up from 0.5R — trades breathe longer) |
| **Profit Target** | 2.5R (up from 2.0R — let runners go further) |
| **Volume Multiplier** | 1.0× (down from 1.2× — more quality signals) |
| **ATR Buffer** | 0.15 × ATR(10) (lower catches more valid breakouts) |
| **Max Positions** | 2 (down from 5 — concentrates capital better) |
| **Focus Symbols** | Top 6 NIFTY stocks: INFY, RELIANCE, TCS, HDFCBANK, BAJFINANCE, SBIN |

---

## 12. Configuration Reference

All configurable parameters live in `app_files/config.py` (360 lines). Here are the key categories:

### Capital & Leverage
| Parameter | Default | Description |
|-----------|---------|-------------|
| `STARTING_CAPITAL` | ₹20,000 | Base trading capital |
| `LEVERAGE` | 5x | MIS intraday leverage |
| `HARDSTOP_CAPITAL` | ₹20,000 | Absolute maximum capital |
| `HARDSTOP_UTILIZATION` | 80% | % of hardstop to actually use (→ ₹16,000 base, ₹80,000 effective) |
| `MARGIN_UTILIZATION` | 85% | % of available margin per trade |

### Multi-Stock Mode
| Parameter | Default | Description |
|-----------|---------|-------------|
| `MULTI_STOCK_MODE` | `True` | Enable portfolio mode |
| `MAX_POSITIONS` | 2 | Max simultaneous trades (optimized from 5) |
| `MAX_STOCKS_TO_SCAN` | 20 | Stocks to scan from NIFTY 50 |
| `MIN_ALLOCATION_PCT` | 10% | Min capital per stock |
| `MAX_ALLOCATION_PCT` | 40% | Max capital per stock |
| `MIN_CONFIDENCE_SCORE` | 0.40 | Min score to trade |
| `FOCUS_SYMBOLS` | 6 stocks | INFY, RELIANCE, TCS, HDFCBANK, BAJFINANCE, SBIN |
| `EXCLUDED_SYMBOLS` | 4 stocks | ITC, TATASTEEL, AXISBANK, ICICIBANK |

### Entry Filters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `USE_DYNAMIC_ATR_BUFFER` | `True` | ATR-based trigger buffer (0.15 × ATR) |
| `USE_VOLUME_FILTER` | `True` | Require volume confirmation (1.0× avg) |
| `USE_NIFTY_FILTER` | `True` | Check NIFTY 50 alignment |
| `USE_TREND_FILTER` | `True` | 15-min VWAP trend check |
| `USE_GAP_FILTER` | `True` | Gap direction filter |
| `USE_OPEN_POSITION_FILTER` | `True` | Candle structure filter |
| `USE_RETEST_ENTRY` | `True` | Wait for breakout retest (max 3 candles) |
| `SKIP_OPEN_BIAS_SHORT` | `True` | Skip ALL trades when open_bias=SHORT |
| `SHORT_REQUIRES_NIFTY_BELOW_VWAP` | `True` | Hard block shorts when NIFTY > VWAP |

### Entry Windows
| Parameter | Default | Description |
|-----------|---------|-------------|
| `PRIMARY_ENTRY_START` | 09:30 | Primary window opens |
| `PRIMARY_ENTRY_END` | 10:30 | Primary window closes (optimized from 10:15) |
| `SOFT_CUTOFF_START` | 10:15 | Soft cutoff starts (needs 2x volume) |
| `SOFT_CUTOFF_END` | 10:30 | Soft cutoff ends |
| `NO_ENTRY_AFTER` | 10:30 | Hard stop for new entries (optimized from 10:45) |

### Exit Strategy (25/20/55 Split)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `PARTIAL_BOOKING_FIRST_CLOSE_PCT` | 25% | Exit at 1.0R |
| `PARTIAL_BOOKING_FIRST_TARGET_R` | 1.0R | First target (optimized from 0.75R) |
| `PARTIAL_BOOKING_SECOND_CLOSE_PCT` | 20% | Exit at 1.0R + SL → breakeven |
| `PARTIAL_BOOKING_EOD_CLOSE_PCT` | 55% | Runner — exit at 2.5R or 3:25 PM |
| `PROFIT_TARGET_RATIO` | 2.5R | Final target (optimized from 2.0R) |
| `STOPLOSS_DISTANCE_FACTOR` | 1.0 | Full range SL (optimized from 0.75) |
| `ATR_TRAIL_MULTIPLIER` | 1.2 | ATR trailing distance |
| `ATR_TRAIL_START_R` | 1.5R | Start trailing after 1.5R |

### Risk Limits
| Parameter | Default | Description |
|-----------|---------|-------------|
| `DAILY_LOSS_LIMIT_PCT` | 2% | Max daily loss (auto-shutdown) |
| `MAX_TRADES_PER_DAY` | 999 | Effectively unlimited |
| `MAX_TRADES_PER_SYMBOL` | 999 | Effectively unlimited |

---

## 13. Setup & Installation

### Prerequisites

- **Python 3.9+**
- **Node.js 18+** (for frontend)
- **PostgreSQL** (production) or SQLite (development — default)
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

## 14. Environment Variables

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

## 15. Running the Bot

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

### Running Backtests

```bash
# Download historical data (requires valid Kite session)
python backtest/download_data.py

# Run full backtest with current config
python backtest/run_backtest.py

# Run parameter optimization (810 combinations)
python backtest/optimize_params.py

# Analyze backtest results
python backtest/analyze_results.py
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
3. → Syncs fresh token to database
4. → Creates KiteApp instance with validated credentials
5. → Restores any existing positions from broker
6. → Calls bot.run() (continuous daily loop)
7.   → get_symbols_setup_data()     ← Fetches candles, calculates triggers
8.   → run_multi_stock_trading()    ← Scans, scores, allocates, executes
9.     → Signal scanning loop        ← 30-second polling
10.    → calculate_signal_confidence() for each signal
11.    → allocate_capital_to_signals()
12.    → execute_multi_stock_entries()
13.  → monitor_multi_stock_positions() ← 3-stage exits + ATR trailing
14.  → generate_multi_stock_report()
15.  → wait_until_next_day_market()  ← Reset state, wait for 9:15 AM
```

---

## 16. Deployment

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
- Trigger cache is persisted to file — survives bot restarts during the trading day
- The bot auto-restores open positions from the broker on restart
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
