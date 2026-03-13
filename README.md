# 🤖 ORB Scalping Trading Bot — Complete Documentation

> **Automated rule-based intraday trading bot** for the Indian stock market (NSE) using the **Opening Range Breakout (ORB)** strategy with VWAP confirmation, multi-stock portfolio management, confidence-based capital allocation, and **pre-session auto-scanning** — powered by the [Zerodha Kite Connect API](https://kite.trade).
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
7. [Pre-Session Auto-Scanner](#7-pre-session-auto-scanner)
8. [Auto-Login System](#8-auto-login-system)
9. [Risk Management](#9-risk-management)
10. [Trade Journal](#10-trade-journal)
11. [Frontend Dashboard](#11-frontend-dashboard)
12. [Backend API](#12-backend-api)
13. [Backtesting Framework](#13-backtesting-framework)
14. [Configuration Reference](#14-configuration-reference)
15. [Setup & Installation](#15-setup--installation)
16. [Environment Variables](#16-environment-variables)
17. [Running the Bot](#17-running-the-bot)
18. [Deployment](#18-deployment)

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
│  │  (3800+ lines)│  │  (580 lines) │  │  (~450 lines)    │          │
│  │  40+ methods  │  │  25+ methods │  │  (all params)    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘          │
│         │                 │                                          │
│         ▼                 ▼                                          │
│  ┌────────────────────────────────────┐                             │
│  │   Zerodha Kite Connect API         │                             │
│  │   (Orders, Quotes, Historical)     │                             │
│  └────────────────────────────────────┘                             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐      │
│  │ kite_login.py │  │kite_session.py│  │pre_session_scanner.py│     │
│  │ (5-step auth) │  │(token manager)│  │ (643 lines, 8 scores)│     │
│  └──────────────┘  └──────────────┘  └──────────────────────┘      │
│                                        ↑ Auto-picks best ORB stocks │
└─────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BACKTESTING ENGINE (backtest/)                    │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐          │
│  │run_backtest.py│  │optimize_     │  │ analyze_results  │          │
│  │(1022 lines)   │  │params.py     │  │    .py           │          │
│  │Full simulator │  │(500 lines)   │  │ Deep diagnostics │          │
│  └──────┬───────┘  │810-combo grid │  └──────────────────┘          │
│         │          └──────────────┘                                  │
│         ▼                                                            │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────────┐   │
│  │download_data.py │  │ data/*.json    │  │orb_readiness_scanner │   │
│  │ (Kite hist API) │  │ 50 stocks × 2  │  │   + scan_all_stocks  │   │
│  └────────────────┘  │ intervals      │  │   (stock ranking)    │   │
│                      └────────────────┘  └──────────────────────┘   │
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
│   ├── bot_kite.py             # Main trading algorithm (3800+ lines, 40+ methods)
│   ├── config.py               # All strategy parameters & configuration (~450 lines)
│   ├── kite_service.py         # Kite API wrapper with caching & rate limiting (580 lines)
│   ├── kite_login.py           # Automated 5-step Kite login (TOTP 2FA)
│   ├── kite_session.py         # Session manager with token persistence
│   ├── pre_session_scanner.py  # Auto-picks best ORB stocks before each session (643 lines)
│   ├── trade_journal.py        # JSONL trade logging (entry/partial exit/full exit/session summary)
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
│   ├── run_backtest.py         # Full strategy backtester (1022 lines)
│   ├── optimize_params.py      # Parameter grid search optimizer (500 lines, 810 combos)
│   ├── analyze_results.py      # Deep trade analysis & diagnostics
│   ├── download_data.py        # Historical data downloader from Kite API
│   ├── orb_readiness_scanner.py # ORB readiness scoring engine (573 lines, 8 metrics)
│   ├── scan_all_stocks.py      # Rank all NIFTY 50 stocks by ORB performance
│   ├── data/                   # Downloaded candle data (50 stocks × 5min + 15min)
│   │   ├── HDFCBANK_5min.json, HDFCBANK_15min.json
│   │   ├── RELIANCE_5min.json, RELIANCE_15min.json
│   │   ├── NIFTY50_5min.json, NIFTY50_15min.json
│   │   ├── ... (50 stock pairs + NIFTY50 + NIFTYBEES + manifest.json)
│   └── results/                # Backtest output
│       ├── backtest_results.json
│       ├── pre_session_scan.json  # Auto-scanner results
│       ├── equity_curve.csv
│       └── trades.csv
│
├── .env                        # Credentials (gitignored)
├── .gitignore                  # Git ignore rules
├── access_token.txt            # Cached Kite token (auto-managed, gitignored)
├── trade_journal.jsonl          # Persistent trade log (JSONL format, one record per event)
├── trigger_cache.json          # Opening range trigger persistence
└── README.md
```

---

## 3. Core Trading Algorithm

The bot implements an **Opening Range Breakout (ORB)** strategy enhanced with VWAP confirmation, volume filters, and multiple exit stages.

### 3.1 Daily Lifecycle

```
09:00 ──── Pre-Session Scanner Runs ────────────────────────────
  │
  │   PHASE 0: AUTO-SCAN (before market open)
  │   • Scan all 50 NIFTY stocks using last 30 days of data
  │   • Score each stock on 8 ORB-specific metrics
  │   • Pick top 10 stocks with sector diversification
  │   • Update FOCUS_SYMBOLS dynamically for today
  │
09:15 ──── Market Opens ────────────────────────────────────────
  │
  │   PHASE 1: SETUP (09:15 → 09:30)
  │   • Fetch actual wallet balance (Dynamic Capital Mode)
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
  │   PHASE 2: SIGNAL SCANNING (09:30 → 10:15)
  │   • Poll 5-minute candles every 30 seconds (optimized from 60s)
  │   • Check each symbol for breakout conditions
  │   • Apply all filters (Volume, NIFTY, Trend, Gap, Open Bias)
  │   • Wait for breakout RETEST confirmation (max 3 candles)
  │   • Calculate 7-factor confidence score
  │   • Execute trade when signal passes all filters
  │
  │   09:30-09:50  PRIMARY WINDOW   → Normal entry rules (peak WR: 52-55%)
  │   09:50-10:15  SOFT CUTOFF      → 2.5× volume required, skip LONGs in NIFTY downtrend
  │   10:15+       HARD STOP        → No new entries allowed
  │
10:15 ──── Entry Window Closes ─────────────────────────────────
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

The bot uses a **dynamic stop loss** with breathing room and progressive tightening:

```python
# Standard ORB SL = VWAP or Candle Low/High
# STOPLOSS_DISTANCE_FACTOR = 1.0 (full range — gives trades maximum room)
# SL_BREATHING_ROOM_FACTOR = 1.25 (25% extra cushion beyond calculated SL)

risk = abs(entry_price - standard_sl)
risk = risk * 1.0    # Distance factor (full range)
risk = risk * 1.25   # Breathing room (+25% extra)

actual_sl = entry_price - risk   # For LONG
actual_sl = entry_price + risk   # For SHORT
```

**Progressive SL Tightening** — After partial profit-taking, the SL is moved gradually instead of jumping straight to breakeven:

| Stage | Trigger | SL Moves To | Example (Entry=₹100, Risk=₹5) |
|-------|---------|-------------|-------------------------------|
| Initial | Entry | Full SL (breathing room) | SL = ₹93.75 |
| Stage 1 | 1.0R partial (25%) | Entry - 25% of original risk | SL = ₹98.75 |
| Stage 2 | 1.0R partial (20%) | Entry + 10% of original risk (profit locked) | SL = ₹100.50 |
| Trail | 1.5R+ | ATR trailing (1.2 × ATR) | Dynamic |

> **Backtest insight**: `SL=1.0` was the single biggest improvement — +₹1,320 vs +₹339 at `SL=0.75`. The 25% breathing room further reduces premature stop-outs from intraday noise. Progressive SL tightening prevents the shock of a sudden breakeven move that often gets clipped by pullbacks.

---

## 4. Signal Filters & Enhancements

Every breakout signal must pass through a **cascade of filters** before becoming a trade. Each filter can independently skip a signal:

### Filter Pipeline (in order)

```
Breakout Detected (price > trigger + above VWAP)
    │
    ├── ① Entry Window Filter ── Is it within 09:30-10:15?
    │                             (SOFT window 09:50-10:15 needs 2.5× volume)
    │
    ├── ② Volume Confirmation ── Is current volume > threshold?
    │                             PRIMARY: 1.0× avg (time-of-day adjusted)
    │                             SOFT: 2.5× avg (higher bar for late entries)
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
    │                             NIFTY downtrend → skip LONGs in soft cutoff
    │
    ├── ⑥ NIFTY Regime Sizing ── Adjust position size by market regime
    │                             Uptrend + LONG: +20% size boost
    │                             Downtrend + LONG: -30% size penalty
    │                             Downtrend + SHORT: +20% size boost
    │                             Ranging: 60% standard size
    │
    ├── ⑦ Trend Filter ──────── Is 15-min VWAP trending with signal?
    │
    ├── ⑧ Range Quality ──────── Is opening range 0.1%-2.5% of price?
    │                             (Rejects too narrow/wide ranges)
    │
    ├── ⑨ Dynamic ATR Buffer ── Volatility-regime-aware buffer
    │                             Tight range (<0.5%): 0.30 × ATR (stronger conviction)
    │                             Normal (0.5-1.0%): 0.15 × ATR (standard)
    │                             Wide range (>1.0%): 0.08 × ATR (already volatile)
    │
    ├── ⑩ Retest Confirmation ── Did price retest the breakout level?
    │                             (Max 3 candles to wait for retest)
    │
    └── ⑪ Liquidity Filter ──── Is daily volume > 500K shares?
                                  (Currently disabled to save API calls)

    ⚡ Active positions are monitored for SL/exit during each scan cycle
       to prevent positions from blowing past stop losses during entry scanning.
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
| SHORT (open near high) | ❌ **SKIP** ⛔ | ⚠️ Allow |

> **Backtest insight**: `SKIP_OPEN_BIAS_SHORT = True` — when the opening candle has a SHORT bias (open near high), **BUY signals are skipped** since buying into bearish candle structure had only 28% win rate. SHORT signals are still allowed since the bias confirms the sell direction.

### 4.3 Symbol Focus (Backtest-Validated)

The bot focuses on **11 backtest-validated NIFTY 50 top performers** across 9 sectors, and excludes 11 underperformers:

```python
# Top 11 stocks — backtest-validated on Jun 2024 → Mar 2026 data
FOCUS_SYMBOLS = [
    "INDUSINDBK",   # Banking    — #1 overall, +₹5,296, PF 1.51
    "TCS",          # IT         — #2 overall, +₹5,227, PF 1.84
    "INFY",         # IT         — #3 overall, +₹4,900, PF 1.95, 61% WR
    "NESTLEIND",    # FMCG       — #4 overall, +₹4,524, PF 1.59
    "SBILIFE",      # Insurance  — #5 overall, +₹4,286, PF 2.12 (best PF)
    "BAJFINANCE",   # Finance    — #6 overall, +₹3,720, PF 1.33
    "RELIANCE",     # Energy     — #8 overall, +₹2,823, PF 1.36
    "APOLLOHOSP",   # Healthcare — #9 overall, +₹2,646, PF 1.64
    "BAJAJ-AUTO",   # Auto       — #10 overall, +₹2,564, PF 1.30
    "COALINDIA",    # Mining     — #11 overall, +₹2,428, PF 1.31
    "HDFCBANK",     # Banking    — #12 overall, -₹204, PF 0.98
]
# Portfolio backtest: +₹16,007 (+20.01%), 52.2% WR, PF 1.54, MaxDD 1.71%

EXCLUDED_SYMBOLS = [
    "ICICIBANK",    # -₹5,844 — worst performer
    "BRITANNIA",    # -₹5,712
    "DRREDDY",      # -₹5,315
    "BAJAJFINSV",   # -₹4,859
    "ITC",          # -₹3,068
    "TRENT",        # -₹2,976
    "JSWSTEEL",     # -₹2,698
    "BPCL",         # -₹2,286
    "TATASTEEL",    # -₹1,860
    "KOTAKBANK",    # -₹1,902
    "AXISBANK",     # -₹1,431
]
```

> **Note**: When `AUTO_SCAN_SYMBOLS = True` (default), the pre-session scanner overrides `FOCUS_SYMBOLS` daily with data-driven picks. The hardcoded list above serves as a fallback if the scanner fails.

---

## 5. Exit Strategy — 3-Stage Partial Booking

The bot uses a **"Let Winners Run"** exit strategy that books profits in three stages while maximizing the runner portion:

```
                                ┌─── STAGE 3: Exit 55% at 2.5R or 3:25 PM ──┐
                                │    (Runner — risk-free after Stage 2)      │
                                │                                            │
                    ┌───────────┤                                            │
                    │ STAGE 2   │                                            │
                    │ Exit 20%  │     55% riding with SL above entry        │
                    │ at 1.0R   │     (PROFIT LOCKED — progressive SL)       │
         ┌──────────┤           │                                            │
         │ STAGE 1  │  SL moves │                                            │
         │ Exit 25% │  to entry │                                            │
         │ at 1.0R  │  - 25%    │                                            │
    ─────┤          │  risk     │                                            │
  ENTRY  │          │           │                                            │
    ─────┤──────────┤───────────┤────────────────────────────────────────────┤
         │    SL    │           │                                      3:25 PM
         │ (breath- │           │
         │  ing rm) │           │
         └──────────┘           │
              ↑                 │
        Initial SL              2.5R Target or EOD
     (125% of risk)
```

### Stage Breakdown

| Stage | R-Multiple | % of Position | Action | SL After Exit |
|-------|-----------|--------------|--------|---------------|
| **Stage 1** | 1.0R | 25% | Book quick profit | SL tightened to entry - 25% of original risk |
| **Stage 2** | 1.0R | 20% | Lock 1:1 RR profit | **SL moves above entry** (+10% of original risk = profit locked) |
| **Stage 3** | 2.5R or 3:25 PM | 55% | Exit runner (ATR-trailed) | Position fully closed |

> **Backtest optimization**: First target moved from 0.5R → 1.0R. This lets trades breathe longer and improves overall win rate. The profit target ratio was also increased from 2.0R → 2.5R to let runners go further. Progressive SL tightening prevents the sudden breakeven jump that often causes premature stop-outs.

### Why 25/20/55 Instead of 25/50/25?

The old split (25/50/25) closed 50% at 1R, leaving only 25% to run. The new split:
- **Keeps 55% riding** after breakeven → captures significantly more from big moves
- After Stage 2, the remaining position has **profit locked** via progressive SL (SL above entry by 10% of original risk), so letting 55% ride is near risk-free
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
  ├── Pre-session scanner auto-picks today's FOCUS_SYMBOLS (top 10)
  ├── Filter by auto-selected FOCUS_SYMBOLS / EXCLUDED_SYMBOLS
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
MAX_ALLOCATION = 60% of capital  # Allows concentration on best signal
MAX_POSITIONS  = 1 simultaneous  # Full capital on highest-confidence signal
MIN_CONFIDENCE = 0.55            # Higher quality bar (raised from 0.40)

# NIFTY Regime-Adaptive Sizing:
# Uptrend + LONG: 120% of normal size (trend confirmation)
# Downtrend + LONG: 70% of normal size (counter-trend penalty)
# Downtrend + SHORT: 120% of normal size (trend confirmation)
# Ranging/Neutral: 60% of normal size (low-conviction markets)
```

> **Backtest insight**: `MAX_POSITIONS = 1` concentrates capital on the single best signal, producing higher per-trade returns than splitting across 2-5 positions.

---

## 7. Pre-Session Auto-Scanner

A **brand-new system** (`pre_session_scanner.py`, 643 lines) that automatically picks the best stocks for ORB trading before each session. When `AUTO_SCAN_SYMBOLS = True` (default), the scanner replaces the hardcoded `FOCUS_SYMBOLS` with data-driven picks every day.

### 7.1 How It Works

```
┌──────────────────────────────────────────────────────────┐
│         PRE-SESSION SCANNER (runs at ~9:15 AM)           │
│                                                          │
│  1. Fetch last 30 days of 5-min + 15-min candle data     │
│     for ALL 50 NIFTY stocks (from Kite API or local)     │
│                                                          │
│  2. Score each stock on 8 ORB-specific metrics:          │
│     ├── Volatility (ATR%) — needs enough movement        │
│     ├── Volume Trend — rising volume = better            │
│     ├── Clean Breakout Ratio — how often ORB triggers    │
│     ├── Gap Quality — moderate gaps (0.3-1.5%) ideal     │
│     ├── Recent ORB Win Rate (HEAVILY WEIGHTED: 25%)      │
│     ├── R-Multiple Quality — how far winners run         │
│     ├── Trend Clarity — clear trend = better signals     │
│     └── Range Quality — opening range 0.3-1.5% ideal    │
│                                                          │
│  3. Rank stocks by composite score                       │
│                                                          │
│  4. Pick top N stocks with sector diversification        │
│     (max 2 per sector to avoid correlation)              │
│                                                          │
│  5. Update config.FOCUS_SYMBOLS for today's session      │
└──────────────────────────────────────────────────────────┘
```

### 7.2 Scoring Weights

| # | Metric | Weight | What It Measures |
|---|--------|--------|-----------------|
| 1 | Recent ORB Win Rate | 25% | Simulated ORB win rate over last 10-30 days |
| 2 | Volatility (ATR%) | 15% | Recent average true range as % of price |
| 3 | Clean Breakout Ratio | 15% | Fraction of days with clean (non-choppy) breakouts |
| 4 | R-Multiple Quality | 15% | Average risk-reward on simulated ORB trades |
| 5 | Volume Trend | 10% | Is volume rising or falling recently? |
| 6 | Trend Clarity | 10% | How directional (up/down) is the stock? |
| 7 | Gap Quality | 5% | Average gap size (moderate = best) |
| 8 | Range Quality | 5% | Average opening range as % of price |

### 7.3 Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AUTO_SCAN_SYMBOLS` | `True` | Enable pre-session auto-scanning |
| `AUTO_SCAN_TOP_N` | 10 | Pick top N stocks from scan |
| `AUTO_SCAN_MIN_SCORE` | 40.0 | Minimum composite score to qualify (0-100) |
| `AUTO_SCAN_MAX_PER_SECTOR` | 2 | Max stocks per sector (diversification) |
| `AUTO_SCAN_USE_API` | `True` | `True` = live Kite API data, `False` = local backtest files |

### 7.4 Fallback Mode

If the scanner fails (API unavailable, insufficient data), the bot falls back to the hardcoded `FOCUS_SYMBOLS` from `config.py`. The scanner can also run offline using local backtest data files via `run_pre_session_scan_from_files()`.

### 7.5 Related Files

| File | Purpose |
|------|---------|
| `app_files/pre_session_scanner.py` | Live scanner (Kite API or local files) |
| `backtest/orb_readiness_scanner.py` | ORB readiness scoring engine (573 lines, reusable) |
| `backtest/scan_all_stocks.py` | Ranks all NIFTY 50 stocks by full backtest performance |

---

## 8. Auto-Login System

Zerodha's access token expires every 24 hours. The bot includes a **fully automated login system** that handles this without manual intervention.

### 8.1 How It Works

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

### 8.2 5-Step Login Process (`kite_login.py`)

| Step | Action | Detail |
|------|--------|--------|
| 1 | Load login page | `GET kite.trade/connect/login` → establishes session cookies |
| 2 | POST credentials | `POST kite.zerodha.com/api/login` with `user_id` + `password` |
| 3 | POST TOTP | `POST kite.zerodha.com/api/twofa` with `pyotp.TOTP(key).now()` |
| 4 | Capture redirect | `GET` login URL with `allow_redirects=False` → extract `request_token` from `Location` header |
| 5 | Exchange token | `kite.generate_session(request_token, api_secret)` → get `access_token` |

The token is saved to `access_token.txt` and cached in memory for 1 hour.

### 8.3 Dashboard Refresh Button

The frontend dashboard has a **🔑 Refresh Login** button that calls `POST /api/kite/auto-login` to force a fresh token generation. The backend also auto-refreshes the token when starting the bot if auto-login is configured.

---

## 9. Risk Management

### 9.1 Dynamic Capital Mode

The bot supports two capital modes:

**Dynamic Capital (default, `DYNAMIC_CAPITAL = True`):**
```
At session start → Fetch actual Kite wallet balance
   → Apply CAPITAL_UTILIZATION (85%) → Base capital for the day
   → Apply LEVERAGE (5x MIS) → Effective capital
   → Profits compound automatically day to day

Example:
  Day 1: Wallet ₹20,000 → 85% = ₹17,000 base → ₹85,000 effective
  Day 2: Wallet ₹21,000 (profit) → 85% = ₹17,850 → ₹89,250 effective
  Day 3: Wallet ₹18,000 (loss) → 85% = ₹15,300 → ₹76,500 effective
```

**Fixed Capital (`DYNAMIC_CAPITAL = False`):**
```
Uses HARDSTOP_CAPITAL = ₹20,000
   × HARDSTOP_UTILIZATION = 80% → ₹16,000 base
   × HARDSTOP_LEVERAGE = 5x → ₹80,000 effective max
```

### 9.2 Capital Guardrails

```
STARTING_CAPITAL = ₹20,000 (fallback if API unreachable)
       × LEVERAGE = 5x (MIS intraday)
       = ₹100,000 effective

CAPITAL_UTILIZATION = 85% (of wallet balance)
MARGIN_UTILIZATION = 85% per trade

Split across MAX_POSITIONS = 2 (multi-stock mode)
```

### 9.3 Loss Limits

| Protection | Setting | Behavior |
|-----------|---------|---------|
| **Daily Loss Limit** | 2% of capital | Auto-closes all positions, stops trading for the day |
| **Per-Trade SL** | 100% of calculated risk | Full range SL (backtest-optimized from 75%) |
| **Breakeven Lock** | After 1R profit | SL moves to entry price — remaining 55% is risk-free |
| **Auto-Exit** | 3:25 PM IST | Closes all MIS positions before market close |
| **ATR Trailing** | After 1.5R | Trailing stop follows price using 1.2 × ATR |
| **Position Restoration** | On bot restart | Restores active positions from broker to resume SL monitoring |

### 9.4 Order Safety

- **Smart Limit Orders**: Uses stop-limit orders instead of market orders (`LIMIT_ORDER_BUFFER = ₹0.20`)
- **Order Timeout**: Converts to market order if limit not filled within 30 seconds
- **Rate Limiting**: Built-in API rate limiter in `kite_service.py` (1s between calls, 10s backoff on rate limit)
- **Quote Caching**: 5-second TTL quote cache, instrument cache (1 hour), batch quotes (up to 500 in one call)
- **Trade Reconciliation**: Backend auto-detects when SL/TP orders fill on the exchange, closes trade in DB, and cancels the opposite exit order (handles race conditions where both SL+TP fill)
- **Real-Time DB Sync**: Trades are saved to the database immediately on entry (`save_trade_to_db`) and updated on every partial exit, SL change, or position close (`update_trade_in_db`)
- **Scan-Phase Position Monitoring**: Active positions are checked for SL hits and partial booking targets during each signal scan cycle (every 30 seconds), preventing stop losses from being missed while the bot is busy scanning for new entries

---

## 10. Trade Journal

The bot maintains a persistent **JSONL trade journal** (`trade_journal.jsonl`) that logs every trading event in structured JSON format — one record per line. This provides a complete audit trail for analysis and debugging.

### 10.1 Event Types

| Event | When Logged | Key Fields |
|-------|-------------|------------|
| **ENTRY** | Trade is placed | Symbol, side, price, SL, quantity, confidence score + breakdown, volume ratio, breakout strength, allocation %, capital allocated, opening range data, NIFTY bias, entry window state, account balance, active position count |
| **PARTIAL_EXIT** | Stage 1 or Stage 2 partial booking | Symbol, side, quantity exited, R-multiple reached, realized P&L, remaining quantity, whether SL moved to breakeven |
| **FULL_EXIT** | Position fully closed (SL/target/EOD) | Symbol, side, exit price, exit reason, entry price, SL price, partial P&L, final exit P&L, total P&L, entry time, full position data |
| **SESSION_SUMMARY** | End of trading day (~3:30 PM) | Date, symbols scanned, symbols traded, total P&L, account balance, positions entered/closed, per-position P&L breakdown |

### 10.2 Usage

```python
# Read journal for analysis with pandas
import pandas as pd
journal = pd.read_json("trade_journal.jsonl", lines=True)

# Filter entries
entries = journal[journal["event"] == "ENTRY"]
exits = journal[journal["event"] == "FULL_EXIT"]
```

Each record includes a full **config snapshot** (all strategy parameters at the moment of the event) for reproducibility. The journal file is append-only and survives bot restarts.

---

## 11. Frontend Dashboard

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

## 12. Backend API

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
- **Auto-Login on Startup**: Token validation and auto-refresh when fetching default user

### Database Models

```
User ──┬── Trade (one-to-many)
       ├── Session (one-to-many)
       ├── DailyStats (one-to-many)
       └── BotLog (via user_id)

User: email, password, capital/leverage config, Kite credentials, bot_active
Trade: symbol, side, entry/exit price, quantity, SL/TP prices, pnl, status,
       order IDs (entry, exit, stoploss), notes (with TARGET_ORDER_ID tracking)
DailyStats: date, total/winning/losing trades, win_rate, total_pnl, largest win/loss
Session: session_token, created/expires timestamps, is_active
BotLog: log_type, message, log_level, timestamp, trade_id (optional)
```

---

## 13. Backtesting Framework

The project includes a complete backtesting suite that validates the strategy on historical data.

### 13.1 Data Pipeline

```bash
python backtest/download_data.py
```

Downloads 5-minute and 15-minute intraday candles from Kite Connect API for **all 50 NIFTY stocks** plus NIFTY 50 index and NIFTYBEES. Data is saved as JSON files in `backtest/data/`.

**Current coverage**: 50 stocks × 2 intervals + NIFTY50 + NIFTYBEES = **104 data files**, covering Jun 2024 → Mar 2026.

### 13.2 Backtester (`run_backtest.py`)

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

### 13.3 Parameter Optimizer (`optimize_params.py`)

Runs a **grid search** across 11 parameter dimensions to find optimal configuration:

| Parameter | Values Tested |
|-----------|--------------|
| Symbol selection | All 50, Top 8, Top 6, Top 5, Top 3 |
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

### 13.4 Results Analyzer (`analyze_results.py`)

Deep diagnostic analysis of backtest trades:
- **Trade outcome breakdown**: Pure SL, Partial + SL, Full winners
- **Entry hour analysis**: Win rate and P&L by hour of day
- **Gap + direction analysis**: Aligned vs contradicting gap performance
- **Open bias analysis**: LONG/SHORT/NEUTRAL bias win rates
- **Holding time**: Average, median, winners vs losers duration
- **Monthly breakdown**: P&L by month
- **Per-symbol performance**: Individual stock analysis

### 13.5 ORB Readiness Scanner (`orb_readiness_scanner.py`)

A reusable scoring engine (573 lines) that analyzes a stock's recent ORB readiness using 8 metrics:
1. Recent Volatility (ATR% of price)
2. Volume Trend (rising vs falling)
3. Clean Breakout Ratio (how often ORB triggers cleanly)
4. Gap Behavior (moderate gaps = ideal for ORB)
5. Trend Clarity (directional stocks give better signals)
6. Recent ORB Win Rate (simulated performance)
7. Average R-Multiple (how far winners run)
8. Range Quality (opening range size)

Used by `pre_session_scanner.py` (for local file mode) and can be run standalone.

### 13.6 Stock Ranker (`scan_all_stocks.py`)

Runs the full backtester on **every NIFTY 50 stock individually** and produces a ranking table by P&L. This is what generated the `FOCUS_SYMBOLS` and `EXCLUDED_SYMBOLS` lists in `config.py`.

### 13.7 Key Backtest Results

The optimized parameters currently in `config.py` were derived from backtesting:

| Metric | Value |
|--------|-------|
| **SL Distance Factor** | 1.0 (full range — biggest single improvement) |
| **SL Breathing Room** | 1.25× (25% extra cushion beyond SL) |
| **Progressive SL** | Stage 1: keep 25% risk, Stage 2: lock profit above entry |
| **Entry Window** | 09:30-10:15 (tightened from 10:30; peak WR at 9:30-9:50) |
| **Soft Cutoff Volume** | 2.5× average (raised from 2.0×) |
| **First Partial Target** | 1.0R (up from 0.5R — trades breathe longer) |
| **Profit Target** | 2.5R (up from 2.0R — let runners go further) |
| **Volume Multiplier** | 1.0× (down from 1.2× — more quality signals) |
| **ATR Buffer** | Regime-aware: 0.30/0.15/0.08 × ATR for tight/normal/wide ranges |
| **Max Positions** | 1 (down from 2 — concentrates capital on best signal) |
| **Min Confidence** | 0.55 (up from 0.40 — higher quality filter) |
| **NIFTY Regime Sizing** | +20% LONGs in uptrend, -30% LONGs in downtrend |
| **Focus Symbols** | Top 11 NIFTY stocks (auto-selected daily or fallback list) |
| **Portfolio Backtest** | +₹16,007 (+20.01%), 52.2% WR, PF 1.54, MaxDD 1.71% |

---

## 14. Configuration Reference

All configurable parameters live in `app_files/config.py` (406 lines). Here are the key categories:

### Capital & Leverage
| Parameter | Default | Description |
|-----------|---------|-------------|
| `DYNAMIC_CAPITAL` | `True` | Fetch live wallet balance each session (profits compound) |
| `CAPITAL_UTILIZATION` | 85% | % of wallet balance to use when dynamic mode is on |
| `STARTING_CAPITAL` | ₹20,000 | Fallback capital if Kite API unreachable |
| `LEVERAGE` | 5x | MIS intraday leverage |
| `USE_LEVERAGE_IN_SIZING` | `True` | Explicitly scale capital by leverage in qty calculation |
| `USE_HARDSTOP_LIMIT` | `False` | Enable fixed capital ceiling (only when dynamic=off) |
| `HARDSTOP_CAPITAL` | ₹20,000 | Maximum base capital (only if hardstop enabled) |
| `HARDSTOP_UTILIZATION` | 80% | % of hardstop to use (→ ₹16,000 base, ₹80,000 effective) |
| `MARGIN_UTILIZATION` | 85% | % of available margin per trade |

### Auto-Scan (Pre-Session Scanner)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `AUTO_SCAN_SYMBOLS` | `True` | Auto-pick best ORB stocks before each session |
| `AUTO_SCAN_TOP_N` | 10 | Number of stocks to pick from scan |
| `AUTO_SCAN_MIN_SCORE` | 40.0 | Minimum composite score (0-100) |
| `AUTO_SCAN_MAX_PER_SECTOR` | 2 | Max stocks per sector (diversification) |
| `AUTO_SCAN_USE_API` | `True` | Use live Kite API data (vs local files) |

### Multi-Stock Mode
| Parameter | Default | Description |
|-----------|---------|-------------|
| `MULTI_STOCK_MODE` | `True` | Enable portfolio mode |
| `MAX_POSITIONS` | 1 | Max simultaneous trades (optimized: 1 concentrates capital best) |
| `MAX_STOCKS_TO_SCAN` | 20 | Stocks to scan from NIFTY 50 |
| `MIN_ALLOCATION_PCT` | 10% | Min capital per stock |
| `MAX_ALLOCATION_PCT` | 60% | Max capital per stock (raised from 40% for concentration) |
| `MIN_CONFIDENCE_SCORE` | 0.55 | Min score to trade (raised from 0.40 for quality) |
| `FOCUS_SYMBOLS` | 11 stocks | Fallback: INDUSINDBK, TCS, INFY, NESTLEIND, SBILIFE, etc. |
| `EXCLUDED_SYMBOLS` | 11 stocks | ICICIBANK, BRITANNIA, DRREDDY, BAJAJFINSV, etc. |

### Entry Filters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `USE_DYNAMIC_ATR_BUFFER` | `True` | ATR-based trigger buffer (regime-aware) |
| `USE_DYNAMIC_ATR_REGIME` | `True` | Select ATR multiplier by opening range width |
| `ATR_MULTIPLIER_TIGHT_RANGE` | 0.30 | Tight range (<0.5%): need stronger conviction |
| `ATR_MULTIPLIER_NORMAL_RANGE` | 0.15 | Normal range (0.5-1.0%): standard buffer |
| `ATR_MULTIPLIER_WIDE_RANGE` | 0.08 | Wide range (>1.0%): smaller buffer is meaningful |
| `USE_VOLUME_FILTER` | `True` | Require volume confirmation |
| `SOFT_CUTOFF_VOL_MULTIPLIER` | 2.5 | Volume multiplier required in soft window |
| `USE_NIFTY_FILTER` | `True` | Check NIFTY 50 alignment |
| `USE_NIFTY_REGIME_SIZING` | `True` | Adjust position size by NIFTY market regime |
| `NIFTY_DOWNTREND_SKIP_LONG_IN_SOFT` | `True` | Skip LONGs in soft cutoff when NIFTY bearish |
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
| `PRIMARY_ENTRY_END` | 09:50 | Primary window closes (optimized: peak WR 52-55%) |
| `SOFT_CUTOFF_START` | 09:50 | Soft cutoff starts (needs 2.5× volume) |
| `SOFT_CUTOFF_END` | 10:15 | Soft cutoff ends |
| `NO_ENTRY_AFTER` | 10:15 | Hard stop for new entries (was 10:30, late entries have 35-38% WR) |

### Exit Strategy (25/20/55 Split)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `PARTIAL_BOOKING_FIRST_CLOSE_PCT` | 25% | Exit at 1.0R |
| `PARTIAL_BOOKING_FIRST_TARGET_R` | 1.0R | First target (optimized from 0.75R) |
| `PARTIAL_BOOKING_SECOND_CLOSE_PCT` | 20% | Exit at 1.0R + progressive SL |
| `PARTIAL_BOOKING_EOD_CLOSE_PCT` | 55% | Runner — exit at 2.5R or 3:25 PM |
| `PROFIT_TARGET_RATIO` | 2.5R | Final target (optimized from 2.0R) |
| `STOPLOSS_DISTANCE_FACTOR` | 1.0 | Full range SL (optimized from 0.75) |
| `SL_BREATHING_ROOM_FACTOR` | 1.25 | 25% extra cushion beyond calculated SL |
| `USE_PROGRESSIVE_SL` | `True` | Gradual SL tightening after partial exits |
| `PROGRESSIVE_SL_STAGE1_FACTOR` | 0.25 | At Stage 1: keep 25% risk below entry |
| `PROGRESSIVE_SL_STAGE2_FACTOR` | -0.10 | At Stage 2: SL 10% of risk above entry (profit locked) |
| `ATR_TRAIL_MULTIPLIER` | 1.2 | ATR trailing distance |
| `ATR_TRAIL_START_R` | 1.5R | Start trailing after 1.5R |

### Risk Limits
| Parameter | Default | Description |
|-----------|---------|-------------|
| `DAILY_LOSS_LIMIT_PCT` | 2% | Max daily loss (auto-shutdown) |
| `MAX_TRADES_PER_DAY` | 999 | Effectively unlimited |
| `MAX_TRADES_PER_SYMBOL` | 999 | Effectively unlimited |

---

## 15. Setup & Installation

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

## 16. Environment Variables

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

## 17. Running the Bot

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

# Rank all NIFTY 50 stocks by ORB performance
python backtest/scan_all_stocks.py

# Run standalone ORB readiness scanner (uses local data)
python -m app_files.pre_session_scanner
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
7.   → [AUTO-SCAN] run_pre_session_scan()  ← Picks today's best stocks
8.   → get_symbols_setup_data()           ← Fetches candles, calculates triggers
9.   → run_multi_stock_trading()          ← Scans, scores, allocates, executes
10.    → Signal scanning loop              ← 30-second polling
11.    → calculate_signal_confidence() for each signal
12.    → allocate_capital_to_signals()
13.    → execute_multi_stock_entries()
14.  → monitor_multi_stock_positions()    ← 3-stage exits + ATR trailing
15.  → generate_multi_stock_report()
16.  → wait_until_next_day_market()       ← Reset state, wait for 9:15 AM
```

---

## 18. Deployment

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
- The pre-session scanner auto-picks stocks before each session starts trading
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
