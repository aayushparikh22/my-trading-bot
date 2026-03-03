"""
ORB Strategy Backtester
========================
Simulates the exact trading algorithm from bot_kite.py on historical data.

Replicates:
- Opening range breakout (15-min candle high/low)
- VWAP confirmation
- Dynamic ATR buffer
- Volume confirmation (time-of-day adjusted)
- Gap alignment filter (Enhancement 2)
- Open position bias filter (Enhancement 3)
- 3-stage partial booking exit (25/20/55)
- ATR trailing stop loss
- Tighter SL (50% of risk)
- Entry window (09:30-10:45 with soft cutoff at 10:15)
- Range quality filter
- Daily loss limit (2%)

Usage:
    python backtest/run_backtest.py

Reads data from:
    backtest/data/*.json (output of download_data.py)
"""

import os
import sys
import json
import math
import logging
from datetime import datetime, timedelta, time as dtime
from collections import defaultdict
import pytz

# Add parent to path for config import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app_files import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


# ===================================================================
# DATA LOADING
# ===================================================================

def load_candle_data(symbol, interval_label):
    """Load candle data from JSON file. interval_label e.g. '5min', '15min'"""
    filename = f"{symbol}_{interval_label}.json"
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        data = json.load(f)
    candles = data.get("candles", [])
    # Parse dates
    for c in candles:
        c["date"] = datetime.fromisoformat(c["date"])
        if c["date"].tzinfo is None:
            c["date"] = IST.localize(c["date"])
    return candles


def group_candles_by_date(candles):
    """Group candles by trading date"""
    by_date = defaultdict(list)
    for c in candles:
        day = c["date"].date()
        by_date[day].append(c)
    return dict(by_date)


# ===================================================================
# INDICATOR CALCULATIONS
# ===================================================================

def calculate_vwap(candles_5min):
    """Calculate VWAP from a list of 5-min candles"""
    cumulative_tp_vol = 0.0
    cumulative_vol = 0
    for c in candles_5min:
        tp = (c["high"] + c["low"] + c["close"]) / 3.0
        cumulative_tp_vol += tp * c["volume"]
        cumulative_vol += c["volume"]
    if cumulative_vol == 0:
        return None
    return cumulative_tp_vol / cumulative_vol


def calculate_atr(candles, period=10):
    """Calculate Average True Range from candles"""
    if len(candles) < period + 1:
        return None
    tr_values = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)
    if len(tr_values) < period:
        return None
    return sum(tr_values[-period:]) / period


def get_volume_ratio(candles_5min, current_idx, lookback=10):
    """Calculate volume ratio: current / avg of last N candles"""
    if current_idx < 1:
        return 1.0
    start = max(0, current_idx - lookback)
    past = candles_5min[start:current_idx]
    if not past:
        return 1.0
    avg_vol = sum(c["volume"] for c in past) / len(past)
    if avg_vol == 0:
        return 1.0
    return candles_5min[current_idx]["volume"] / avg_vol


def get_time_of_day_volume_factor(candle_time):
    """Get time-of-day volume multiplier"""
    if not config.USE_TIME_OF_DAY_VOLUME:
        return 1.0
    hhmm = candle_time.hour * 100 + candle_time.minute
    if hhmm < 1015:
        return config.VOLUME_EARLY_MULT
    elif hhmm < 1230:
        return config.VOLUME_MID_MULT
    elif hhmm < 1430:
        return config.VOLUME_LATE_MULT
    else:
        return config.VOLUME_CLOSE_MULT


def check_range_quality(high, low, vwap):
    """Check if opening range is within acceptable bounds"""
    if not config.USE_RANGE_FILTER or not vwap or vwap <= 0:
        return True
    range_pct = ((high - low) / vwap) * 100
    return config.RANGE_MIN_PCT <= range_pct <= config.RANGE_MAX_PCT


# ===================================================================
# TRADE SIMULATION
# ===================================================================

class Trade:
    """Represents a single simulated trade with 3-stage exit"""

    def __init__(self, symbol, side, entry_price, sl_price, quantity, entry_time, gap_pct=0, open_bias="NEUTRAL"):
        self.symbol = symbol
        self.side = side  # "BUY" or "SELL"
        self.entry_price = entry_price
        self.sl_price = sl_price
        self.original_sl = sl_price
        self.quantity = quantity
        self.remaining_qty = quantity
        self.entry_time = entry_time
        self.exit_time = None
        self.gap_pct = gap_pct
        self.open_bias = open_bias

        self.realized_pnl = 0.0
        self.status = "OPEN"  # OPEN, CLOSED

        # Partial booking state
        self.stage1_done = False
        self.stage2_done = False
        self.stage3_done = False
        self.sl_at_breakeven = False

        # Calculate targets
        risk = abs(entry_price - sl_price)
        self.risk = risk
        if side == "BUY":
            self.target1 = entry_price + risk * config.PARTIAL_BOOKING_FIRST_TARGET_R
            self.target2 = entry_price + risk * config.PARTIAL_BOOKING_SECOND_TARGET_R
            self.target3 = entry_price + risk * config.PROFIT_TARGET_RATIO
        else:
            self.target1 = entry_price - risk * config.PARTIAL_BOOKING_FIRST_TARGET_R
            self.target2 = entry_price - risk * config.PARTIAL_BOOKING_SECOND_TARGET_R
            self.target3 = entry_price - risk * config.PROFIT_TARGET_RATIO

        # Calculate stage quantities (25/20/55)
        self.qty1 = int(quantity * config.PARTIAL_BOOKING_FIRST_CLOSE_PCT)
        self.qty2 = int(quantity * config.PARTIAL_BOOKING_SECOND_CLOSE_PCT)
        self.qty3 = int(quantity * config.PARTIAL_BOOKING_EOD_CLOSE_PCT)
        remainder = quantity - (self.qty1 + self.qty2 + self.qty3)
        if remainder > 0:
            self.qty3 += remainder  # Distribute to runner

        # Small quantity handling
        if quantity == 1:
            self.qty1, self.qty2, self.qty3 = 1, 0, 0
        elif quantity == 2:
            self.qty1, self.qty2, self.qty3 = 1, 1, 0
        elif quantity == 3:
            self.qty1, self.qty2, self.qty3 = 1, 1, 1
        else:
            if self.qty1 == 0:
                self.qty1 = 1
            if self.qty2 == 0:
                self.qty2 = 1

        # Exit reason tracking
        self.exit_parts = []  # list of (qty, price, reason, pnl)

    def pnl_at(self, price, qty):
        """Calculate P&L for a given price and quantity"""
        if self.side == "BUY":
            return (price - self.entry_price) * qty
        else:
            return (self.entry_price - price) * qty

    def check_sl_hit(self, candle):
        """Check if stop loss was hit during this candle"""
        if self.side == "BUY":
            return candle["low"] <= self.sl_price
        else:
            return candle["high"] >= self.sl_price

    def process_candle(self, candle, atr_value=None):
        """
        Process a single 5-min candle against this trade.
        Returns True if trade is fully closed after this candle.
        """
        if self.status == "CLOSED":
            return True

        price = candle["close"]
        ctime = candle["date"]

        # Auto-exit at 3:25 PM
        if ctime.hour == 15 and ctime.minute >= 25:
            self._close_remaining(price, "EOD_AUTO_EXIT", ctime)
            return True

        # Check SL hit (use low/high of candle for realism)
        if self.check_sl_hit(candle):
            sl_exit_price = self.sl_price  # Exit at SL price, not candle close
            self._close_remaining(sl_exit_price, "STOPLOSS", ctime)
            return True

        # ATR trailing stop (after 1.5R profit)
        if config.USE_ATR_TRAILING_EXIT and self.stage2_done and atr_value and atr_value > 0:
            profit = price - self.entry_price if self.side == "BUY" else self.entry_price - price
            if profit >= self.risk * config.ATR_TRAIL_START_R:
                trail_dist = atr_value * config.ATR_TRAIL_MULTIPLIER
                if self.side == "BUY":
                    new_sl = price - trail_dist
                    if new_sl > self.sl_price:
                        self.sl_price = new_sl
                else:
                    new_sl = price + trail_dist
                    if new_sl < self.sl_price:
                        self.sl_price = new_sl

        # Stage 1: 0.5R target → close 25%
        if not self.stage1_done and self.qty1 > 0 and self.remaining_qty > 0:
            hit = (self.side == "BUY" and price >= self.target1) or \
                  (self.side == "SELL" and price <= self.target1)
            if hit:
                close_qty = min(self.qty1, max(self.remaining_qty - 1, 1))
                pnl = self.pnl_at(price, close_qty)
                self.realized_pnl += pnl
                self.remaining_qty -= close_qty
                self.stage1_done = True
                self.exit_parts.append((close_qty, price, "STAGE1_0.5R", pnl))

        # Stage 2: 1.0R target → close 20% + SL to breakeven
        if self.stage1_done and not self.stage2_done and self.qty2 > 0 and self.remaining_qty > 0:
            hit = (self.side == "BUY" and price >= self.target2) or \
                  (self.side == "SELL" and price <= self.target2)
            if hit:
                close_qty = min(self.qty2, max(self.remaining_qty - 1, 1))
                if close_qty < 1:
                    close_qty = self.remaining_qty
                pnl = self.pnl_at(price, close_qty)
                self.realized_pnl += pnl
                self.remaining_qty -= close_qty
                self.stage2_done = True
                self.sl_price = self.entry_price  # Move SL to breakeven
                self.sl_at_breakeven = True
                self.exit_parts.append((close_qty, price, "STAGE2_1R", pnl))

        # Stage 3: 2.0R target → close remaining 55%
        if self.stage2_done and not self.stage3_done and self.remaining_qty > 0:
            hit = (self.side == "BUY" and price >= self.target3) or \
                  (self.side == "SELL" and price <= self.target3)
            # Also check for approaching EOD (3:20 PM)
            eod = ctime.hour == 15 and ctime.minute >= 20
            if hit or eod:
                reason = "STAGE3_2R" if hit else "STAGE3_EOD"
                pnl = self.pnl_at(price, self.remaining_qty)
                self.realized_pnl += pnl
                self.exit_parts.append((self.remaining_qty, price, reason, pnl))
                self.remaining_qty = 0
                self.stage3_done = True
                self.status = "CLOSED"
                self.exit_time = ctime
                return True

        # If all qty gone
        if self.remaining_qty <= 0:
            self.status = "CLOSED"
            self.exit_time = ctime
            return True

        return False

    def _close_remaining(self, price, reason, ctime):
        """Close all remaining shares"""
        if self.remaining_qty <= 0:
            return
        pnl = self.pnl_at(price, self.remaining_qty)
        self.realized_pnl += pnl
        self.exit_parts.append((self.remaining_qty, price, reason, pnl))
        self.remaining_qty = 0
        self.status = "CLOSED"
        self.exit_time = ctime

    @property
    def total_pnl(self):
        return self.realized_pnl

    def summary(self):
        """One-line trade summary"""
        duration = ""
        if self.entry_time and self.exit_time:
            delta = self.exit_time - self.entry_time
            duration = f"{delta.seconds // 60}min"
        exits = " → ".join(f"{qty}@₹{p:.1f}({r})" for qty, p, r, _ in self.exit_parts)
        return (
            f"{self.symbol} {self.side} | Entry:₹{self.entry_price:.1f} SL:₹{self.original_sl:.1f} "
            f"Qty:{self.quantity} | P&L:₹{self.total_pnl:+,.1f} | {duration} | {exits}"
        )


# ===================================================================
# BACKTESTER ENGINE
# ===================================================================

class Backtester:
    """Simulates one trading day at a time, replicating bot_kite.py logic"""

    def __init__(self, symbols):
        self.symbols = symbols  # List of symbol strings
        self.all_trades = []
        self.daily_pnl = {}
        self.skipped_days = {}
        self.capital = config.STARTING_CAPITAL * config.LEVERAGE * config.HARDSTOP_UTILIZATION

    def run(self):
        """Run backtest across all available trading days"""
        # Load all data
        data_5min = {}
        data_15min = {}
        for sym in self.symbols:
            d5 = load_candle_data(sym, "5min")
            d15 = load_candle_data(sym, "15min")
            if d5:
                data_5min[sym] = group_candles_by_date(d5)
            if d15:
                data_15min[sym] = group_candles_by_date(d15)

        if not data_5min:
            logger.error("No 5-min data found! Run download_data.py first.")
            return

        # Load NIFTY 50 data if available
        nifty_5min = load_candle_data("NIFTY50", "5min")
        nifty_by_date = group_candles_by_date(nifty_5min) if nifty_5min else {}

        # Get all trading days (union of all symbols)
        all_days = set()
        for sym_days in data_5min.values():
            all_days.update(sym_days.keys())
        all_days = sorted(all_days)

        logger.info(f"📊 Backtesting {len(self.symbols)} symbols across {len(all_days)} trading days")
        logger.info(f"💰 Starting capital: ₹{self.capital:,.0f}")
        logger.info(f"📅 Period: {all_days[0]} → {all_days[-1]}")
        print()

        for day in all_days:
            self._simulate_day(day, data_5min, data_15min, nifty_by_date)

        return self.all_trades, self.daily_pnl

    def _simulate_day(self, day, data_5min, data_15min, nifty_by_date):
        """Simulate one full trading day"""
        daily_trades = []
        daily_loss = 0.0

        # --- PHASE 1: SETUP (using 15-min + 5-min candles) ---
        symbols_setup = {}

        for sym in self.symbols:
            candles_5 = data_5min.get(sym, {}).get(day, [])
            candles_15 = data_15min.get(sym, {}).get(day, [])

            if not candles_5 or not candles_15:
                continue

            # Get opening 15-min candle (09:15-09:30)
            opening_15 = None
            for c in candles_15:
                if c["date"].hour == 9 and c["date"].minute == 15:
                    opening_15 = c
                    break

            if not opening_15:
                # Try first 15-min candle of the day
                if candles_15:
                    opening_15 = candles_15[0]
                else:
                    continue

            o = opening_15["open"]
            h = opening_15["high"]
            l = opening_15["low"]
            cl = opening_15["close"]

            if h <= 0 or l <= 0 or h <= l:
                continue

            # Calculate VWAP from first few 5-min candles (09:15-09:30)
            vwap_candles = [c for c in candles_5 if c["date"].hour == 9 and c["date"].minute < 35]
            if not vwap_candles:
                vwap_candles = candles_5[:3]  # fallback
            vwap = calculate_vwap(vwap_candles) if vwap_candles else None

            if not vwap:
                continue

            # Range quality filter
            if not check_range_quality(h, l, vwap):
                continue

            # ATR buffer from preceding 5-min candles
            pre_candles = [c for c in candles_5 if c["date"].hour == 9 and c["date"].minute <= 30]
            if len(pre_candles) < 3:
                pre_candles = candles_5[:5]
            atr_val = calculate_atr(pre_candles, min(config.ATR_PERIOD, len(pre_candles) - 1)) if len(pre_candles) > 2 else None

            if config.USE_DYNAMIC_ATR_BUFFER and atr_val:
                buffer = config.ATR_MULTIPLIER * atr_val
            else:
                buffer = config.BUFFER_AMOUNT

            long_trigger = h + buffer
            short_trigger = l - buffer

            # Enhancement 2: Gap % (use previous day close from 15-min data)
            gap_pct = 0.0
            # Get previous close from yesterday's last candle
            prev_day_candles = data_15min.get(sym, {})
            prev_days = sorted([d for d in prev_day_candles.keys() if d < day])
            if prev_days:
                prev_last = prev_day_candles[prev_days[-1]]
                if prev_last:
                    prev_close = prev_last[-1]["close"]
                    if prev_close > 0:
                        gap_pct = ((o - prev_close) / prev_close) * 100

            # Enhancement 3: Open position in range
            candle_range = h - l
            if candle_range > 0:
                open_position = (o - l) / candle_range
            else:
                open_position = 0.5

            strong_zone = getattr(config, 'OPEN_POSITION_STRONG_ZONE', 0.25)
            if open_position >= (1 - strong_zone):
                open_bias = "SHORT"
            elif open_position <= strong_zone:
                open_bias = "LONG"
            else:
                open_bias = "NEUTRAL"

            symbols_setup[sym] = {
                "open": o, "high": h, "low": l, "close": cl,
                "vwap": vwap,
                "long_trigger": long_trigger,
                "short_trigger": short_trigger,
                "buffer": buffer,
                "gap_pct": gap_pct,
                "open_bias": open_bias,
                "candles_5": candles_5,
                "atr_initial": atr_val,
            }

        if not symbols_setup:
            return

        # --- NIFTY bias for the day ---
        nifty_candles = nifty_by_date.get(day, [])
        nifty_bias = "NEUTRAL"
        nifty_vwap = None
        if nifty_candles:
            nifty_open_candles = [c for c in nifty_candles if c["date"].hour == 9]
            if nifty_open_candles:
                nifty_vwap = calculate_vwap(nifty_open_candles)

        # --- PHASE 2: SIGNAL SCANNING (09:30 → 10:45) ---
        active_trades = []  # Trades opened today
        entry_found_symbols = set()

        for sym, setup in symbols_setup.items():
            candles_5 = setup["candles_5"]

            for idx, candle in enumerate(candles_5):
                ctime = candle["date"]

                # Only scan during entry window (09:30 to NO_ENTRY_AFTER)
                hhmm = ctime.hour * 100 + ctime.minute
                if hhmm < 930:
                    continue
                if hhmm > getattr(config, 'NO_ENTRY_AFTER', 1015):
                    break  # Past hard stop

                # Check daily loss limit
                if config.USE_DAILY_LOSS_LIMIT:
                    loss_limit = self.capital * config.DAILY_LOSS_LIMIT_PCT
                    if daily_loss <= -loss_limit:
                        break

                # Already have a trade in this symbol
                if sym in entry_found_symbols:
                    continue

                # Max positions check
                open_count = sum(1 for t in active_trades if t.status == "OPEN")
                if open_count >= config.MAX_POSITIONS:
                    continue

                c5 = candle["close"]
                vwap = setup["vwap"]
                long_trigger = setup["long_trigger"]
                short_trigger = setup["short_trigger"]

                # Update rolling VWAP using all candles up to now
                vwap_candles_so_far = candles_5[:idx + 1]
                rolling_vwap = calculate_vwap(vwap_candles_so_far)
                if rolling_vwap:
                    vwap = rolling_vwap

                entry_side = None
                entry_price = None

                # --- Skip OpenBias=SHORT entirely (backtest optimization) ---
                if getattr(config, 'SKIP_OPEN_BIAS_SHORT', False) and setup["open_bias"] == "SHORT":
                    continue

                # --- LONG SIGNAL ---
                if c5 > long_trigger and c5 > vwap:
                    # Soft cutoff: need extra volume confirmation
                    if hhmm >= getattr(config, 'SOFT_CUTOFF_START', 1000):
                        vol_ratio = get_volume_ratio(candles_5, idx, config.VOLUME_LOOKBACK_CANDLES)
                        if vol_ratio < config.SOFT_CUTOFF_VOL_MULTIPLIER:
                            continue

                    # Volume filter
                    if config.USE_VOLUME_FILTER:
                        vol_ratio = get_volume_ratio(candles_5, idx, config.VOLUME_LOOKBACK_CANDLES)
                        time_factor = get_time_of_day_volume_factor(ctime)
                        if vol_ratio < config.VOLUME_MULTIPLIER * time_factor:
                            continue

                    # Gap filter
                    if getattr(config, 'USE_GAP_FILTER', False) and getattr(config, 'GAP_CONTRADICTION_SKIP', False):
                        if setup["gap_pct"] < -config.GAP_ALIGNMENT_MIN_PCT:
                            continue

                    # Open position bias filter
                    if getattr(config, 'USE_OPEN_POSITION_FILTER', False) and getattr(config, 'OPEN_POSITION_SKIP_CONTRADICTION', False):
                        if setup["open_bias"] == "SHORT":
                            continue

                    # NIFTY filter
                    if config.USE_NIFTY_FILTER and nifty_vwap and nifty_candles:
                        # Find closest NIFTY candle
                        nifty_price = _get_nifty_price_at(nifty_candles, ctime)
                        if nifty_price and nifty_vwap and nifty_price < nifty_vwap:
                            if not getattr(config, 'USE_NIFTY_SOFT_BIAS', False):
                                continue  # Hard block

                    entry_side = "BUY"
                    entry_price = c5

                # --- SHORT SIGNAL ---
                elif c5 < short_trigger and c5 < vwap:
                    # SHORT requires NIFTY below VWAP (hard block)
                    if getattr(config, 'SHORT_REQUIRES_NIFTY_BELOW_VWAP', False) and nifty_vwap and nifty_candles:
                        nifty_price = _get_nifty_price_at(nifty_candles, ctime)
                        if nifty_price and nifty_vwap and nifty_price >= nifty_vwap:
                            continue  # NIFTY above VWAP = skip short

                    if hhmm >= getattr(config, 'SOFT_CUTOFF_START', 1000):
                        vol_ratio = get_volume_ratio(candles_5, idx, config.VOLUME_LOOKBACK_CANDLES)
                        if vol_ratio < config.SOFT_CUTOFF_VOL_MULTIPLIER:
                            continue

                    if config.USE_VOLUME_FILTER:
                        vol_ratio = get_volume_ratio(candles_5, idx, config.VOLUME_LOOKBACK_CANDLES)
                        time_factor = get_time_of_day_volume_factor(ctime)
                        if vol_ratio < config.VOLUME_MULTIPLIER * time_factor:
                            continue

                    if getattr(config, 'USE_GAP_FILTER', False) and getattr(config, 'GAP_CONTRADICTION_SKIP', False):
                        if setup["gap_pct"] > config.GAP_ALIGNMENT_MIN_PCT:
                            continue

                    if getattr(config, 'USE_OPEN_POSITION_FILTER', False) and getattr(config, 'OPEN_POSITION_SKIP_CONTRADICTION', False):
                        if setup["open_bias"] == "LONG":
                            continue

                    if config.USE_NIFTY_FILTER and nifty_vwap and nifty_candles:
                        nifty_price = _get_nifty_price_at(nifty_candles, ctime)
                        if nifty_price and nifty_vwap and nifty_price > nifty_vwap:
                            if not getattr(config, 'USE_NIFTY_SOFT_BIAS', False):
                                continue

                    entry_side = "SELL"
                    entry_price = c5

                # --- EXECUTE TRADE ---
                if entry_side:
                    # Calculate stop loss (dynamic: tighter by STOPLOSS_DISTANCE_FACTOR)
                    if entry_side == "BUY":
                        raw_sl = min(vwap, candle["low"])
                        risk = entry_price - raw_sl
                        sl_price = entry_price - (risk * config.STOPLOSS_DISTANCE_FACTOR)
                    else:
                        raw_sl = max(vwap, candle["high"])
                        risk = raw_sl - entry_price
                        sl_price = entry_price + (risk * config.STOPLOSS_DISTANCE_FACTOR)

                    if risk <= 0:
                        continue  # Invalid risk

                    # Position sizing
                    per_position = self.capital / config.MAX_POSITIONS
                    quantity = max(1, int(per_position * config.MARGIN_UTILIZATION / entry_price))

                    trade = Trade(
                        symbol=sym,
                        side=entry_side,
                        entry_price=entry_price,
                        sl_price=sl_price,
                        quantity=quantity,
                        entry_time=ctime,
                        gap_pct=setup["gap_pct"],
                        open_bias=setup["open_bias"]
                    )

                    active_trades.append(trade)
                    entry_found_symbols.add(sym)

        # --- PHASE 3: EXIT MONITORING ---
        # Process remaining candles for each active trade
        for trade in active_trades:
            if trade.status == "CLOSED":
                continue

            sym = trade.symbol
            candles_5 = symbols_setup[sym]["candles_5"]

            # Find candles after entry
            for idx, candle in enumerate(candles_5):
                if candle["date"] <= trade.entry_time:
                    continue

                # Calculate running ATR for trailing
                start_idx = max(0, idx - config.ATR_PERIOD - 1)
                atr_val = calculate_atr(candles_5[start_idx:idx + 1], config.ATR_PERIOD)

                closed = trade.process_candle(candle, atr_val)
                if closed:
                    break

            # Force close if still open (shouldn't happen with EOD logic)
            if trade.status == "OPEN":
                last_candle = candles_5[-1] if candles_5 else None
                if last_candle:
                    trade._close_remaining(last_candle["close"], "FORCE_EOD", last_candle["date"])

        # --- Record results ---
        day_pnl = sum(t.total_pnl for t in active_trades)
        self.daily_pnl[day] = day_pnl
        self.all_trades.extend(active_trades)

        # Log day result
        if active_trades:
            icon = "🟢" if day_pnl >= 0 else "🔴"
            logger.info(f"{icon} {day} | {len(active_trades)} trades | P&L: ₹{day_pnl:+,.1f}")
            for t in active_trades:
                logger.info(f"   {t.summary()}")


def _get_nifty_price_at(nifty_candles, target_time):
    """Get NIFTY close price closest to target time"""
    best = None
    best_diff = timedelta(hours=24)
    for c in nifty_candles:
        diff = abs(c["date"] - target_time)
        if diff < best_diff:
            best_diff = diff
            best = c["close"]
    return best


# ===================================================================
# RESULTS ANALYSIS
# ===================================================================

def analyze_results(trades, daily_pnl, capital):
    """Generate comprehensive backtest report"""
    if not trades:
        print("\n❌ No trades executed. Check your data files.")
        return {}

    os.makedirs(RESULTS_DIR, exist_ok=True)

    total_trades = len(trades)
    winners = [t for t in trades if t.total_pnl > 0]
    losers = [t for t in trades if t.total_pnl < 0]
    breakeven = [t for t in trades if t.total_pnl == 0]
    longs = [t for t in trades if t.side == "BUY"]
    shorts = [t for t in trades if t.side == "SELL"]

    total_pnl = sum(t.total_pnl for t in trades)
    gross_profit = sum(t.total_pnl for t in winners)
    gross_loss = sum(t.total_pnl for t in losers)
    win_rate = len(winners) / total_trades * 100 if total_trades else 0

    avg_win = gross_profit / len(winners) if winners else 0
    avg_loss = gross_loss / len(losers) if losers else 0
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')
    expectancy = total_pnl / total_trades if total_trades else 0

    # Max drawdown
    cumulative = 0
    peak = 0
    max_dd = 0
    for day in sorted(daily_pnl.keys()):
        cumulative += daily_pnl[day]
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    # Streak analysis
    streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    for t in trades:
        if t.total_pnl > 0:
            if streak > 0:
                streak += 1
            else:
                streak = 1
            max_win_streak = max(max_win_streak, streak)
        elif t.total_pnl < 0:
            if streak < 0:
                streak -= 1
            else:
                streak = -1
            max_loss_streak = max(max_loss_streak, abs(streak))
        else:
            streak = 0

    # Exit stage analysis
    stage_pnl = {"STAGE1_0.5R": 0, "STAGE2_1R": 0, "STAGE3_2R": 0, "STAGE3_EOD": 0, "STOPLOSS": 0, "EOD_AUTO_EXIT": 0}
    stage_count = defaultdict(int)
    for t in trades:
        for qty, price, reason, pnl in t.exit_parts:
            key = reason
            if key not in stage_pnl:
                stage_pnl[key] = 0
            stage_pnl[key] += pnl
            stage_count[key] += 1

    # Per-symbol performance
    sym_pnl = defaultdict(float)
    sym_count = defaultdict(int)
    sym_wins = defaultdict(int)
    for t in trades:
        sym_pnl[t.symbol] += t.total_pnl
        sym_count[t.symbol] += 1
        if t.total_pnl > 0:
            sym_wins[t.symbol] += 1

    # Print report
    print("\n" + "=" * 80)
    print("📊 BACKTEST RESULTS — ORB STRATEGY")
    print("=" * 80)

    print(f"\n📅 Period: {min(daily_pnl.keys())} → {max(daily_pnl.keys())}")
    print(f"   Trading days: {len(daily_pnl)}")
    print(f"   Days with trades: {sum(1 for v in daily_pnl.values() if v != 0)}")
    print(f"   Capital: ₹{capital:,.0f}")

    print(f"\n💰 OVERALL PERFORMANCE")
    print(f"   Total P&L:       ₹{total_pnl:+,.1f} ({total_pnl / capital * 100:+.2f}%)")
    print(f"   Total Trades:     {total_trades}")
    print(f"   Winners:          {len(winners)} ({win_rate:.1f}%)")
    print(f"   Losers:           {len(losers)} ({100 - win_rate:.1f}%)")
    print(f"   Breakeven:        {len(breakeven)}")
    print(f"   Avg Win:          ₹{avg_win:+,.1f}")
    print(f"   Avg Loss:         ₹{avg_loss:+,.1f}")
    print(f"   Profit Factor:    {profit_factor:.2f}")
    print(f"   Expectancy:       ₹{expectancy:+,.1f} per trade")
    print(f"   Max Drawdown:     ₹{max_dd:,.1f} ({max_dd / capital * 100:.2f}%)")
    print(f"   Max Win Streak:   {max_win_streak}")
    print(f"   Max Loss Streak:  {max_loss_streak}")

    print(f"\n📈 LONG vs SHORT")
    long_pnl = sum(t.total_pnl for t in longs)
    short_pnl = sum(t.total_pnl for t in shorts)
    long_wr = sum(1 for t in longs if t.total_pnl > 0) / len(longs) * 100 if longs else 0
    short_wr = sum(1 for t in shorts if t.total_pnl > 0) / len(shorts) * 100 if shorts else 0
    print(f"   LONG:  {len(longs)} trades | P&L: ₹{long_pnl:+,.1f} | WR: {long_wr:.1f}%")
    print(f"   SHORT: {len(shorts)} trades | P&L: ₹{short_pnl:+,.1f} | WR: {short_wr:.1f}%")

    print(f"\n🎯 EXIT STAGE ANALYSIS")
    for stage, pnl in sorted(stage_pnl.items()):
        cnt = stage_count.get(stage, 0)
        print(f"   {stage:20s}: {cnt:4d} exits | P&L: ₹{pnl:+,.1f}")

    print(f"\n📊 PER-SYMBOL PERFORMANCE")
    sym_sorted = sorted(sym_pnl.items(), key=lambda x: x[1], reverse=True)
    for sym, pnl in sym_sorted:
        cnt = sym_count[sym]
        wr = sym_wins[sym] / cnt * 100 if cnt else 0
        print(f"   {sym:12s}: {cnt:3d} trades | P&L: ₹{pnl:+,.1f} | WR: {wr:.0f}%")

    print(f"\n📊 DAILY P&L DISTRIBUTION")
    daily_sorted = sorted(daily_pnl.items())
    green_days = sum(1 for _, v in daily_sorted if v > 0)
    red_days = sum(1 for _, v in daily_sorted if v < 0)
    flat_days = sum(1 for _, v in daily_sorted if v == 0)
    daily_values = [v for _, v in daily_sorted if v != 0]
    if daily_values:
        best_day_val = max(daily_values)
        worst_day_val = min(daily_values)
        best_day = [d for d, v in daily_sorted if v == best_day_val][0]
        worst_day = [d for d, v in daily_sorted if v == worst_day_val][0]
        avg_daily = sum(daily_values) / len(daily_values) if daily_values else 0
        print(f"   Green days:  {green_days}")
        print(f"   Red days:    {red_days}")
        print(f"   Flat days:   {flat_days}")
        print(f"   Best day:    {best_day} → ₹{best_day_val:+,.1f}")
        print(f"   Worst day:   {worst_day} → ₹{worst_day_val:+,.1f}")
        print(f"   Avg daily:   ₹{avg_daily:+,.1f}")

    print("\n" + "=" * 80)

    # Save results to JSON
    results = {
        "period": {
            "from": str(min(daily_pnl.keys())),
            "to": str(max(daily_pnl.keys())),
            "trading_days": len(daily_pnl),
        },
        "capital": capital,
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / capital * 100, 2),
        "total_trades": total_trades,
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(win_rate, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 999,
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd / capital * 100, 2),
        "long_trades": len(longs),
        "long_pnl": round(long_pnl, 2),
        "short_trades": len(shorts),
        "short_pnl": round(short_pnl, 2),
        "per_symbol": {sym: {"trades": sym_count[sym], "pnl": round(pnl, 2),
                              "win_rate": round(sym_wins[sym] / sym_count[sym] * 100, 1) if sym_count[sym] else 0}
                       for sym, pnl in sym_sorted},
        "exit_stages": {k: {"count": stage_count[k], "pnl": round(v, 2)} for k, v in stage_pnl.items()},
        "daily_pnl": {str(k): round(v, 2) for k, v in daily_sorted},
        "trades": [
            {
                "symbol": t.symbol,
                "side": t.side,
                "entry_price": t.entry_price,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "quantity": t.quantity,
                "pnl": round(t.total_pnl, 2),
                "gap_pct": round(t.gap_pct, 2),
                "open_bias": t.open_bias,
                "exit_parts": [(qty, round(p, 2), r, round(pnl, 2)) for qty, p, r, pnl in t.exit_parts],
            }
            for t in trades
        ],
    }

    results_path = os.path.join(RESULTS_DIR, "backtest_results.json")
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"\n💾 Full results saved to {results_path}")

    # Save trade log CSV
    csv_path = os.path.join(RESULTS_DIR, "trades.csv")
    with open(csv_path, 'w') as f:
        f.write("Date,Symbol,Side,EntryPrice,SLPrice,Qty,PnL,GapPct,OpenBias,ExitReason,Duration\n")
        for t in trades:
            exit_reasons = "+".join(r for _, _, r, _ in t.exit_parts)
            duration = ""
            if t.entry_time and t.exit_time:
                duration = f"{(t.exit_time - t.entry_time).seconds // 60}min"
            f.write(f"{t.entry_time.date()},{t.symbol},{t.side},{t.entry_price:.2f},"
                    f"{t.original_sl:.2f},{t.quantity},{t.total_pnl:.2f},"
                    f"{t.gap_pct:.2f},{t.open_bias},{exit_reasons},{duration}\n")
    logger.info(f"📋 Trade log saved to {csv_path}")

    # Save equity curve CSV
    equity_path = os.path.join(RESULTS_DIR, "equity_curve.csv")
    cumulative = 0
    with open(equity_path, 'w') as f:
        f.write("Date,DailyPnL,CumulativePnL,Equity\n")
        for day, pnl in sorted(daily_pnl.items()):
            cumulative += pnl
            f.write(f"{day},{pnl:.2f},{cumulative:.2f},{capital + cumulative:.2f}\n")
    logger.info(f"📈 Equity curve saved to {equity_path}")

    return results


# ===================================================================
# MAIN
# ===================================================================

def main():
    print("=" * 80)
    print("🧪 ORB STRATEGY BACKTESTER")
    print("=" * 80)
    print()

    # Check for data
    if not os.path.exists(DATA_DIR):
        print("❌ No data directory found!")
        print("   Run the downloader first: python backtest/download_data.py")
        return

    # Discover available symbols from data files
    files = [f for f in os.listdir(DATA_DIR) if f.endswith("_5min.json")]
    symbols = [f.replace("_5min.json", "") for f in files]
    # Exclude NIFTY50 from trading (it's used as index filter only)
    symbols = [s for s in symbols if s != "NIFTY50"]

    # Apply symbol focus (if configured, ONLY trade these symbols)
    focus = getattr(config, 'FOCUS_SYMBOLS', [])
    if focus:
        symbols = [s for s in symbols if s in focus]
        print(f"🎯 Focused on {len(symbols)} symbols: {', '.join(symbols)}")
    else:
        # Apply symbol exclusion from config
        excluded = getattr(config, 'EXCLUDED_SYMBOLS', [])
        if excluded:
            before = len(symbols)
            symbols = [s for s in symbols if s not in excluded]
            print(f"⛔ Excluded {before - len(symbols)} symbols: {', '.join(excluded)}")

    if not symbols:
        print("❌ No 5-min data files found in backtest/data/")
        print("   Run: python backtest/download_data.py")
        return

    print(f"📈 Found data for {len(symbols)} symbols: {', '.join(symbols)}")
    print()

    # Print active config
    print("⚙️  STRATEGY CONFIG:")
    print(f"   Partial Booking:    {config.PARTIAL_BOOKING_FIRST_CLOSE_PCT*100:.0f}% / "
          f"{config.PARTIAL_BOOKING_SECOND_CLOSE_PCT*100:.0f}% / "
          f"{config.PARTIAL_BOOKING_EOD_CLOSE_PCT*100:.0f}%")
    print(f"   SL Distance Factor: {config.STOPLOSS_DISTANCE_FACTOR}")
    print(f"   Stage 1 Target:     {config.PARTIAL_BOOKING_FIRST_TARGET_R}R")
    print(f"   Volume Filter:      {config.USE_VOLUME_FILTER} (mult: {config.VOLUME_MULTIPLIER})")
    print(f"   Gap Filter:         {getattr(config, 'USE_GAP_FILTER', False)}")
    print(f"   Open Bias Filter:   {getattr(config, 'USE_OPEN_POSITION_FILTER', False)}")
    print(f"   Skip OpenBias=SHORT:{getattr(config, 'SKIP_OPEN_BIAS_SHORT', False)}")
    print(f"   NIFTY Filter:       {config.USE_NIFTY_FILTER}")
    print(f"   SHORT needs NIFTY:  {getattr(config, 'SHORT_REQUIRES_NIFTY_BELOW_VWAP', False)}")
    print(f"   ATR Trailing:       {config.USE_ATR_TRAILING_EXIT}")
    print(f"   Max Positions:      {config.MAX_POSITIONS}")
    print(f"   Entry Window:       09:30-{getattr(config, 'NO_ENTRY_AFTER', 1015)} (soft cutoff {getattr(config, 'SOFT_CUTOFF_START', 1000)})")
    print(f"   Excluded Symbols:   {getattr(config, 'EXCLUDED_SYMBOLS', [])}")
    print(f"   Focus Symbols:      {getattr(config, 'FOCUS_SYMBOLS', [])}")
    print(f"   Final Target:       {config.PROFIT_TARGET_RATIO}R")
    print()

    # Run backtest
    bt = Backtester(symbols)
    trades, daily_pnl = bt.run()

    # Analyze
    print()
    results = analyze_results(trades, daily_pnl, bt.capital)


if __name__ == "__main__":
    main()
