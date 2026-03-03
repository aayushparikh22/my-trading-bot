import os

# ===== KITE API CREDENTIALS =====
KITE_API_KEY = os.getenv("KITE_API_KEY", "YOUR_KITE_API_KEY")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "YOUR_KITE_ACCESS_TOKEN")
ZERODHA_USER_ID = os.getenv("ZERODHA_USER_ID", "YOUR_ZERODHA_USER_ID")

# ===== KITE API CONFIGURATION =====
KITE_DEBUG = os.getenv("KITE_DEBUG", "False").lower() == 'true'
KITE_TIMEOUT = 30  # API request timeout in seconds

# ===== TRADING CAPITAL & LEVERAGE =====
STARTING_CAPITAL = 20000      # Your actual capital in INR
LEVERAGE = 5                  # Default 5x intraday margin leverage (MIS product type)
                              # NOTE: This value is for tracking/display only
                              # Kite API applies leverage AUTOMATICALLY based on product_type='MIS'
EFFECTIVE_CAPITAL = STARTING_CAPITAL * LEVERAGE  # = 100,000 INR effective trading power

# Use leverage factor in quantity sizing (explicitly scale capital)
USE_LEVERAGE_IN_SIZING = True

# ===== HARDSTOP CAPITAL LIMIT =====
# This is the MAXIMUM capital the bot will ever use, regardless of account balance
HARDSTOP_CAPITAL = 20000      # Maximum base capital: ₹20,000
HARDSTOP_UTILIZATION = 0.80   # Use only 80% of hardstop: ₹16,000
HARDSTOP_LEVERAGE = 5         # With 5x leverage: ₹80,000 effective max
# Calculated limits:
HARDSTOP_USABLE_CAPITAL = HARDSTOP_CAPITAL * HARDSTOP_UTILIZATION  # = ₹16,000
HARDSTOP_EFFECTIVE_MAX = HARDSTOP_USABLE_CAPITAL * HARDSTOP_LEVERAGE  # = ₹80,000

# ===== MARGIN UTILIZATION =====
MARGIN_UTILIZATION = 0.85    # Use 85% of available capital as margin per trade

# ===== MULTI-STOCK PORTFOLIO ALLOCATION =====
# Enable trading multiple stocks simultaneously with confidence-based allocation
MULTI_STOCK_MODE = True       # Enable multi-stock trading (False = single stock like before)
MAX_POSITIONS = 5             # Maximum simultaneous positions (1-10)
MIN_ALLOCATION_PCT = 0.10     # Minimum 10% allocation per stock (prevents tiny positions)
MAX_ALLOCATION_PCT = 0.40     # Maximum 40% allocation per stock (prevents over-concentration)
MAX_STOCKS_TO_SCAN = 20       # Limit stocks to scan (reduces API calls) - top N from list

# Confidence Scoring Weights (total should = 1.0)
# Higher weight = more importance in allocation decision
CONFIDENCE_WEIGHT_VOLUME = 0.20      # Volume strength (how much above average)
CONFIDENCE_WEIGHT_BREAKOUT = 0.20    # Breakout strength (how far past trigger)
CONFIDENCE_WEIGHT_NIFTY = 0.15       # NIFTY alignment strength
CONFIDENCE_WEIGHT_TREND = 0.10       # Higher timeframe trend alignment
CONFIDENCE_WEIGHT_VOLATILITY = 0.10  # ATR/volatility favorability
CONFIDENCE_WEIGHT_GAP = 0.15         # Gap alignment (relative strength vs prev close)
CONFIDENCE_WEIGHT_OPEN_BIAS = 0.10   # Open position within candle range

# Confidence Thresholds
MIN_CONFIDENCE_SCORE = 0.40   # Minimum score to consider (0-1 scale, 0.4 = 40%)
HIGH_CONFIDENCE_THRESHOLD = 0.70  # Score above this gets priority allocation

# ===== ENHANCEMENT: RELATIVE STRENGTH / GAP FILTER =====
USE_GAP_FILTER = True              # Enable gap direction alignment filter
GAP_ALIGNMENT_MIN_PCT = 0.3        # Minimum gap % to consider significant (e.g. 0.3%)
GAP_STRONG_PCT = 1.0               # Strong gap threshold (1%+ gap = very bullish/bearish)
GAP_CONTRADICTION_SKIP = True      # Skip signals where gap contradicts breakout direction

# ===== ENHANCEMENT: OPEN POSITION BIAS FILTER =====
USE_OPEN_POSITION_FILTER = True    # Enable open-position-in-range bias filter
OPEN_POSITION_STRONG_ZONE = 0.25   # Top/bottom 25% of range = strong directional bias
OPEN_POSITION_SKIP_CONTRADICTION = True  # Skip signals contradicting open position bias
                              
# ===== TRADING STRATEGY CONFIG =====
# Multiple symbols to monitor - bot will trade the first one that hits criteria
# Complete NIFTY 50 Index Constituents
SYMBOLS_TO_MONITOR = [
    # ===== NIFTY 50 STOCKS (All 50 Index Constituents) =====
    
    # --- Banking & Financial Services ---
    {"symbol": "HDFCBANK", "exchange": "NSE"},     # HDFC Bank
    {"symbol": "ICICIBANK", "exchange": "NSE"},    # ICICI Bank
    {"symbol": "SBIN", "exchange": "NSE"},         # State Bank of India
    {"symbol": "KOTAKBANK", "exchange": "NSE"},    # Kotak Mahindra Bank
    {"symbol": "AXISBANK", "exchange": "NSE"},     # Axis Bank
    {"symbol": "INDUSINDBK", "exchange": "NSE"},   # IndusInd Bank
    {"symbol": "BAJFINANCE", "exchange": "NSE"},   # Bajaj Finance
    {"symbol": "BAJAJFINSV", "exchange": "NSE"},   # Bajaj Finserv
    {"symbol": "HDFCLIFE", "exchange": "NSE"},     # HDFC Life Insurance
    {"symbol": "SBILIFE", "exchange": "NSE"},      # SBI Life Insurance
    {"symbol": "SHRIRAMFIN", "exchange": "NSE"},   # Shriram Finance
    
    # --- Information Technology ---
    {"symbol": "TCS", "exchange": "NSE"},          # Tata Consultancy Services
    {"symbol": "INFY", "exchange": "NSE"},         # Infosys
    {"symbol": "HCLTECH", "exchange": "NSE"},      # HCL Technologies
    {"symbol": "WIPRO", "exchange": "NSE"},        # Wipro
    {"symbol": "TECHM", "exchange": "NSE"},        # Tech Mahindra
    {"symbol": "LTIM", "exchange": "NSE"},         # LTI Mindtree
    
    # --- Oil, Gas & Energy ---
    {"symbol": "RELIANCE", "exchange": "NSE"},     # Reliance Industries
    {"symbol": "ONGC", "exchange": "NSE"},         # Oil and Natural Gas Corporation
    {"symbol": "BPCL", "exchange": "NSE"},         # Bharat Petroleum
    {"symbol": "NTPC", "exchange": "NSE"},         # NTPC Limited
    {"symbol": "POWERGRID", "exchange": "NSE"},    # Power Grid Corporation
    {"symbol": "COALINDIA", "exchange": "NSE"},    # Coal India
    {"symbol": "ADANIPORTS", "exchange": "NSE"},   # Adani Ports and SEZ
    {"symbol": "ADANIENT", "exchange": "NSE"},     # Adani Enterprises
    
    # --- Automobiles ---
    {"symbol": "TATAMOTORS", "exchange": "NSE"},   # Tata Motors
    {"symbol": "MARUTI", "exchange": "NSE"},       # Maruti Suzuki
    {"symbol": "M&M", "exchange": "NSE"},          # Mahindra & Mahindra
    {"symbol": "BAJAJ-AUTO", "exchange": "NSE"},   # Bajaj Auto
    {"symbol": "EICHERMOT", "exchange": "NSE"},    # Eicher Motors
    {"symbol": "HEROMOTOCO", "exchange": "NSE"},   # Hero MotoCorp
    
    # --- Metals & Mining ---
    {"symbol": "TATASTEEL", "exchange": "NSE"},    # Tata Steel
    {"symbol": "JSWSTEEL", "exchange": "NSE"},     # JSW Steel
    {"symbol": "HINDALCO", "exchange": "NSE"},     # Hindalco Industries
    
    # --- Consumer Goods & FMCG ---
    {"symbol": "HINDUNILVR", "exchange": "NSE"},   # Hindustan Unilever
    {"symbol": "ITC", "exchange": "NSE"},          # ITC Limited
    {"symbol": "NESTLEIND", "exchange": "NSE"},    # Nestle India
    {"symbol": "BRITANNIA", "exchange": "NSE"},    # Britannia Industries
    {"symbol": "TATACONSUM", "exchange": "NSE"},   # Tata Consumer Products
    {"symbol": "TITAN", "exchange": "NSE"},        # Titan Company
    {"symbol": "TRENT", "exchange": "NSE"},        # Trent Limited
    
    # --- Pharmaceuticals & Healthcare ---
    {"symbol": "SUNPHARMA", "exchange": "NSE"},    # Sun Pharmaceutical
    {"symbol": "DRREDDY", "exchange": "NSE"},      # Dr. Reddy's Laboratories
    {"symbol": "CIPLA", "exchange": "NSE"},        # Cipla
    {"symbol": "APOLLOHOSP", "exchange": "NSE"},   # Apollo Hospitals
    
    # --- Infrastructure & Construction ---
    {"symbol": "LT", "exchange": "NSE"},           # Larsen & Toubro
    {"symbol": "ULTRACEMCO", "exchange": "NSE"},   # UltraTech Cement
    {"symbol": "GRASIM", "exchange": "NSE"},       # Grasim Industries
    
    # --- Telecom ---
    {"symbol": "BHARTIARTL", "exchange": "NSE"},   # Bharti Airtel
    
    # --- Paints ---
    {"symbol": "ASIANPAINT", "exchange": "NSE"},   # Asian Paints
]

# Legacy support - keep primary symbol for backward compatibility
SYMBOL_NSE = "TATASTEEL"      # Primary symbol (backward compatibility)
EXCHANGE = "NSE"              # Primary exchange
TIMEFRAME_RANGE = 15          # Use 15-minute candle to define range (9:15-9:30)
TIMEFRAME_ENTRY = 5           # Use 5-minute candle for entry confirmation

# ===== OPTIMIZED STRATEGY: VWAP + BUFFER FILTER =====
# STEP 1 (RANGE): Define High & Low from 09:15-09:30 (15-min candle)
#   - Calculate VWAP (Volume Weighted Average Price)
#
# STEP 2 (BUFFER): Add safety margin to High/Low
#   - BUFFER_AMOUNT = ₹0.10
#   - Long Trigger = High + Buffer (filters out wick touches)
#   - Short Trigger = Low - Buffer (avoids false breakouts)
#
# STEP 3 (CONFIRMATION): Switch to 5-minute candles for entry
#   - Buy only if: 5-min candle CLOSES above (High + Buffer) AND Price > VWAP
#   - Sell only if: 5-min candle CLOSES below (Low - Buffer) AND Price < VWAP
#   - This filters out 70% of false breakouts
#
# STEP 4 (RISK MANAGEMENT): Use VWAP as Stop Loss
#   - Stop Loss = VWAP level (tighter than High/Low)

BUFFER_AMOUNT = 0.10          # Buffer in ₹ (DEPRECATED - now dynamic via ATR)
TRIGGER_BUFFER = BUFFER_AMOUNT  # Alias for watchlist endpoint

# ===== PHASE 1: CRITICAL FIXES =====
# 1. Smart Limit Orders
USE_LIMIT_ORDERS = True        # Use stop-limit instead of market orders
LIMIT_ORDER_BUFFER = 0.20      # Limit = Trigger + 0.20 (prevents slippage)
LIMIT_ORDER_TIMEOUT = 30       # Cancel and convert to market after 30 sec

# 2. Dynamic Volatility Buffer (ATR)
USE_DYNAMIC_ATR_BUFFER = True  # Use ATR-based buffer instead of fixed
ATR_PERIOD = 10               # ATR lookback period (10 candles)
ATR_MULTIPLIER = 0.2          # Buffer = 0.2 × ATR(10)
ATR_TIMEFRAME = "5minute"     # Calculate ATR on 5-min candles

# 2a. Opening Range Quality Filter
USE_RANGE_FILTER = True        # Skip ranges that are too small/large
RANGE_MIN_PCT = 0.1            # Min opening range as % of price
RANGE_MAX_PCT = 2.5            # Max opening range as % of price

# 2b. Retest Entry Confirmation
USE_RETEST_ENTRY = True        # Require breakout + retest confirmation
RETEST_MAX_CANDLES = 3         # Max 5-min candles to wait for retest

# 2c. Liquidity & Spread Filter
USE_LIQUIDITY_FILTER = False   # DISABLED to reduce API calls (causes rate limits)
MIN_DAILY_VOLUME = 500000      # Minimum daily volume (shares)
MAX_SPREAD_PCT = 0.2           # Max spread % of last price

# 3. Volume Confirmation
USE_VOLUME_FILTER = True       # Require volume confirmation before entry
VOLUME_MULTIPLIER = 1.2        # Base volume multiplier (was 1.5x, now 1.2x for more signals)
VOLUME_LOOKBACK_CANDLES = 10   # Rolling lookback candles (was 20, now 10 for less API calls)
USE_TIME_OF_DAY_VOLUME = True # Adjust volume threshold by time-of-day
VOLUME_EARLY_MULT = 1.2       # 9:15-10:15 higher expected volume
VOLUME_MID_MULT = 1.0         # 10:15-12:30 baseline
VOLUME_LATE_MULT = 0.8        # 12:30-14:30 lower expected volume
VOLUME_CLOSE_MULT = 0.9       # 14:30-15:30 pickup into close

# ===== PHASE 2: STRATEGY LOGIC =====
# 4. Extended & Adaptive Window
PRIMARY_ENTRY_START = 930      # 9:30 AM (primary window opens)
PRIMARY_ENTRY_END = 1015       # 10:15 AM (primary window closes)
SOFT_CUTOFF_START = 1015       # 10:15 AM (soft cutoff starts)
SOFT_CUTOFF_END = 1045         # 10:45 AM (soft cutoff ends)
NO_ENTRY_AFTER = 1045          # 10:45 AM (hard stop, no more entries)

# During soft cutoff (10:15-10:45): Take signal ONLY if:
# - Volatility expanding (ATR > avg ATR) OR
# - Volume 2x average
SOFT_CUTOFF_VOL_MULTIPLIER = 2.0

# 5. Smart Multi-Trade Logic
MAX_TRADES_PER_DAY = 999       # Unlimited trades per day
ALLOW_RECOVERY_TRADE = True    # Allow 2nd trade after 1st loss
RECOVERY_TRADE_TIMEOUT = 1045  # Stop recovery trades after 10:45 AM

# 6. Index Trend Alignment
USE_NIFTY_FILTER = True        # Check NIFTY trend before trading
NIFTY_SYMBOL = "NIFTY 50"      # Index to monitor
NIFTY_CHECK_INTERVAL = 300     # Check NIFTY every 5 minutes

# 6b. NIFTY Soft Bias Filter
USE_NIFTY_SOFT_BIAS = True     # Soft filter instead of hard block
NIFTY_STRONG_THRESHOLD_PCT = 0.25  # Strong bias threshold (percent)

# 6a. Higher Timeframe Trend Alignment
USE_TREND_FILTER = True        # Require higher timeframe trend alignment
TREND_METHOD = "VWAP"          # Options: VWAP (default)
TREND_TIMEFRAME = "15minute"  # Higher timeframe for trend check
TREND_REFRESH_SEC = 300        # Refresh trend cache (seconds)

# ===== PHASE 3: RISK & EXIT =====
# 7. Dynamic Stop Loss
USE_DYNAMIC_SL = True          # Use min(VWAP, Candle Low/High) as SL
DYNAMIC_SL_BUFFER = 0.05       # Small buffer below candle low for SL

# 7a. ATR Trailing Exit
USE_ATR_TRAILING_EXIT = True   # Trail stop using ATR
ATR_TRAIL_MULTIPLIER = 1.2     # ATR multiple for trailing stop
ATR_TRAIL_REFRESH_SEC = 60     # Refresh ATR for trailing (seconds)
ATR_TRAIL_START_R = 1.5        # Start trailing after this R multiple

# 8a. Retest Zone
RETEST_ZONE_PCT = 0.08         # Retest zone width around trigger (percent)

# 5a. Dynamic Trade Caps
MAX_TRADES_PER_SYMBOL = 999    # Unlimited trades per symbol per day
MAX_TRADES_PER_DAY_PORTFOLIO = 999  # Unlimited total trades per day

# 8. Optimized Partial Booking - LET WINNERS RUN STRATEGY
USE_PARTIAL_BOOKING = True     # Enable advanced exit logic
# RUNNER-OPTIMIZED STRATEGY:
# At 0.5R: Sell 25% of holdings (take quick profit, covers commissions)
# At 1R: Sell 20% more (lock profit, move SL to breakeven → remaining 55% is FREE)
# At 2R+: Let remaining 55% trail with ATR (capture big runners)
# Key insight: After 1R, the remaining 55% is a risk-free trade. Let it run.
PARTIAL_BOOKING_1R_ACTION = "breakeven"  # Move SL to entry at 1R

# FIRST TARGET: 0.5R (Quick Profit - SELL 25%)
PARTIAL_BOOKING_FIRST_CLOSE_PCT = 0.25   # Close 25% at 0.5R (quick profit)
PARTIAL_BOOKING_FIRST_TARGET_R = 0.5     # First target at 0.5R

# SECOND TARGET: 1R (Lock Profit - SELL 20%, SL moves to entry)
PARTIAL_BOOKING_SECOND_CLOSE_PCT = 0.20  # Close 20% at 1R (was 50% - now keep more riding)
PARTIAL_BOOKING_SECOND_TARGET_R = 1.0    # Second target at 1R

# RUNNER: Trail remaining 55% with ATR, exit at 2R+ or 3:25 PM
PARTIAL_BOOKING_EOD_CLOSE_PCT = 0.55     # Exit remaining 55% at target or 3:25 PM (was 25%)
PARTIAL_BOOKING_EOD_TIME = "15:25"       # Market close time (3:25 PM IST)

# TIGHTER STOP LOSS
STOPLOSS_DISTANCE_FACTOR = 0.5           # SL at 50% of calculated risk distance (tighter stops)
# Example: If Entry=100, normal SL=90 (risk=10)
#          With this factor: New SL=95 (risk=5, which is 50% of original)

PARTIAL_BOOKING_TRAIL_FROM = 1.5        # Trail remaining from 1.5R level (was 3.0)

# 9. Daily Loss Limit
USE_DAILY_LOSS_LIMIT = True    # Hard stop at daily loss threshold
DAILY_LOSS_LIMIT_PCT = 0.02    # 2% of capital = hard stop
AUTO_SHUTDOWN_ON_LOSS_LIMIT = True  # Auto-stop bot at 2% loss

# ===== AUTOMATED PROFIT TAKING =====
PROFIT_TARGET_TYPE = "ratio"   # "ratio", "percent", or "fixed"
PROFIT_TARGET_RATIO = 2.0      # Keep 1:2 risk:reward ratio (final target)
                              # But book profits in 3 stages:
                              # 50% at 0.5R, 25% at 1R, 25% at market close
PROFIT_TARGET_PERCENT = 1.0    # 1% profit target (alternative)
PROFIT_TARGET_FIXED = 300      # ₹300 fixed profit target (alternative)

# ===== KITE API DOCUMENTATION REFERENCE =====
# Product Type Values (product_type parameter):
#   "MIS" = Margin Intraday Square-off (intraday with leverage, MUST close by market close)
#   "CNC" = Cash & Carry (delivery-based, no leverage)
#   "NRML" = Normal (margin carry forward)
#
# Order Type Values (order_type parameter):
#   "REGULAR" = Regular order
#   "BRACKET" = Bracket order with predefined profit/loss
#   "COVER" = Cover order with trailing stoploss
#   "BO" = Bracket Order (same as BRACKET)
#   "CO" = Cover Order (same as COVER)
#
# Price Type Values (price_type parameter):
#   "MKT" = Market order
#   "LIMIT" = Limit order
#   "SL" = Stop Loss (triggers market order)
#   "SL-M" = Stop Loss Market
#   "SL-L" = Stop Loss Limit
#
# Validity Values (validity parameter):
#   "DAY" = Day order (expires at end of session)
#   "IOC" = Immediate or Cancel
#   "GTC" = Good Till Cancelled
#
# Direction Values (transaction_type parameter):
#   "BUY" = Buy order
#   "SELL" = Sell order
#
# Quote Response Fields (from quote API):
#   "last_price" = Last traded price
#   "high" = Day high
#   "low" = Day low
#   "open" = Day open
#   "close" = Previous close
#   "volume" = Total volume traded
#   "last_quantity" = Quantity of last trade
#   "bid_quantity" = Bid quantity
#   "ask_quantity" = Ask quantity

# ===== TRADE TYPE =====
TRADE_TYPE = "MIS"            # Product type for API
TRADE_TYPE_DISPLAY = "Intraday (MIS)"

# ===== AUTOMATIC MARKET TIMINGS (IST) =====
# Trading starts: 9:15 AM (market opens)
# Opening candle closes: 9:30 AM (bot starts trading)
# Trading ends: 3:15 PM IST (bot auto-exits)
# NOTE: All MIS positions MUST be closed by 3:30 PM IST (market close)