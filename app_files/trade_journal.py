"""
📓 PERSISTENT TRADE JOURNAL
Appends detailed trade records to a JSON-Lines file (one JSON object per line).
Each record captures every filter, score, and config value the bot used so you
can replay / optimise decisions later.

File location: <project_root>/trade_journal.jsonl
Format: Each line is a self-contained JSON object — easy to load with pandas:
    import pandas as pd
    df = pd.read_json("trade_journal.jsonl", lines=True)
"""

import json
import os
import datetime
import logging
from app_files import config

logger = logging.getLogger(__name__)

# Journal lives at project root (next to tradingbot.db)
JOURNAL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trade_journal.jsonl")


def _now_ist_str():
    """UTC → IST string"""
    utc = datetime.datetime.utcnow()
    ist = utc + datetime.timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d %H:%M:%S")


def _now_ist_date():
    utc = datetime.datetime.utcnow()
    ist = utc + datetime.timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d")


def _safe(val, decimals=4):
    """Round floats safely; pass through non-floats."""
    if isinstance(val, float):
        return round(val, decimals)
    return val


def _snapshot_config():
    """Capture all strategy-relevant config values at the moment of the trade."""
    return {
        # Capital
        "DYNAMIC_CAPITAL": config.DYNAMIC_CAPITAL,
        "CAPITAL_UTILIZATION": config.CAPITAL_UTILIZATION,
        "LEVERAGE": config.LEVERAGE,
        "MARGIN_UTILIZATION": config.MARGIN_UTILIZATION,
        "USE_LEVERAGE_IN_SIZING": config.USE_LEVERAGE_IN_SIZING,
        "USE_HARDSTOP_LIMIT": getattr(config, "USE_HARDSTOP_LIMIT", False),
        "HARDSTOP_EFFECTIVE_MAX": getattr(config, "HARDSTOP_EFFECTIVE_MAX", None),
        # Multi-stock
        "MULTI_STOCK_MODE": config.MULTI_STOCK_MODE,
        "MAX_POSITIONS": config.MAX_POSITIONS,
        "MIN_ALLOCATION_PCT": config.MIN_ALLOCATION_PCT,
        "MAX_ALLOCATION_PCT": config.MAX_ALLOCATION_PCT,
        "MIN_CONFIDENCE_SCORE": config.MIN_CONFIDENCE_SCORE,
        # Entry
        "USE_LIMIT_ORDERS": config.USE_LIMIT_ORDERS,
        "LIMIT_ORDER_BUFFER": config.LIMIT_ORDER_BUFFER,
        "USE_DYNAMIC_ATR_BUFFER": config.USE_DYNAMIC_ATR_BUFFER,
        "ATR_PERIOD": config.ATR_PERIOD,
        "ATR_MULTIPLIER": config.ATR_MULTIPLIER,
        "USE_RANGE_FILTER": config.USE_RANGE_FILTER,
        "RANGE_MIN_PCT": config.RANGE_MIN_PCT,
        "RANGE_MAX_PCT": config.RANGE_MAX_PCT,
        "USE_RETEST_ENTRY": config.USE_RETEST_ENTRY,
        "RETEST_MAX_CANDLES": config.RETEST_MAX_CANDLES,
        "USE_LIQUIDITY_FILTER": config.USE_LIQUIDITY_FILTER,
        "USE_VOLUME_FILTER": config.USE_VOLUME_FILTER,
        "VOLUME_MULTIPLIER": config.VOLUME_MULTIPLIER,
        "VOLUME_LOOKBACK_CANDLES": config.VOLUME_LOOKBACK_CANDLES,
        # Window
        "PRIMARY_ENTRY_START": config.PRIMARY_ENTRY_START,
        "NO_ENTRY_AFTER": getattr(config, "NO_ENTRY_AFTER", 1030),
        "SOFT_CUTOFF_START": getattr(config, "SOFT_CUTOFF_START", 1015),
        # Filters
        "USE_GAP_FILTER": getattr(config, "USE_GAP_FILTER", False),
        "GAP_ALIGNMENT_MIN_PCT": getattr(config, "GAP_ALIGNMENT_MIN_PCT", 0),
        "GAP_STRONG_PCT": getattr(config, "GAP_STRONG_PCT", 0),
        "GAP_CONTRADICTION_SKIP": getattr(config, "GAP_CONTRADICTION_SKIP", False),
        "USE_OPEN_POSITION_FILTER": getattr(config, "USE_OPEN_POSITION_FILTER", False),
        "OPEN_POSITION_SKIP_CONTRADICTION": getattr(config, "OPEN_POSITION_SKIP_CONTRADICTION", False),
        "SKIP_OPEN_BIAS_SHORT": getattr(config, "SKIP_OPEN_BIAS_SHORT", False),
        "USE_NIFTY_FILTER": config.USE_NIFTY_FILTER,
        "USE_TREND_FILTER": config.USE_TREND_FILTER,
        "TREND_METHOD": config.TREND_METHOD,
        "TREND_TIMEFRAME": config.TREND_TIMEFRAME,
        # Risk / exit
        "USE_DYNAMIC_SL": config.USE_DYNAMIC_SL,
        "DYNAMIC_SL_BUFFER": config.DYNAMIC_SL_BUFFER,
        "STOPLOSS_DISTANCE_FACTOR": config.STOPLOSS_DISTANCE_FACTOR,
        "USE_ATR_TRAILING_EXIT": config.USE_ATR_TRAILING_EXIT,
        "ATR_TRAIL_MULTIPLIER": config.ATR_TRAIL_MULTIPLIER,
        "ATR_TRAIL_START_R": config.ATR_TRAIL_START_R,
        "USE_PARTIAL_BOOKING": config.USE_PARTIAL_BOOKING,
        "PARTIAL_BOOKING_FIRST_CLOSE_PCT": config.PARTIAL_BOOKING_FIRST_CLOSE_PCT,
        "PARTIAL_BOOKING_FIRST_TARGET_R": config.PARTIAL_BOOKING_FIRST_TARGET_R,
        "PARTIAL_BOOKING_SECOND_CLOSE_PCT": config.PARTIAL_BOOKING_SECOND_CLOSE_PCT,
        "PARTIAL_BOOKING_SECOND_TARGET_R": config.PARTIAL_BOOKING_SECOND_TARGET_R,
        "PARTIAL_BOOKING_EOD_CLOSE_PCT": getattr(config, "PARTIAL_BOOKING_EOD_CLOSE_PCT", 0.55),
        "PARTIAL_BOOKING_EOD_TIME": getattr(config, "PARTIAL_BOOKING_EOD_TIME", "15:25"),
        "PROFIT_TARGET_TYPE": config.PROFIT_TARGET_TYPE,
        "PROFIT_TARGET_RATIO": config.PROFIT_TARGET_RATIO,
        "USE_DAILY_LOSS_LIMIT": config.USE_DAILY_LOSS_LIMIT,
        "DAILY_LOSS_LIMIT_PCT": config.DAILY_LOSS_LIMIT_PCT,
        # Confidence weights
        "CONFIDENCE_WEIGHT_VOLUME": config.CONFIDENCE_WEIGHT_VOLUME,
        "CONFIDENCE_WEIGHT_BREAKOUT": config.CONFIDENCE_WEIGHT_BREAKOUT,
        "CONFIDENCE_WEIGHT_NIFTY": config.CONFIDENCE_WEIGHT_NIFTY,
        "CONFIDENCE_WEIGHT_TREND": config.CONFIDENCE_WEIGHT_TREND,
        "CONFIDENCE_WEIGHT_VOLATILITY": config.CONFIDENCE_WEIGHT_VOLATILITY,
        "CONFIDENCE_WEIGHT_GAP": getattr(config, "CONFIDENCE_WEIGHT_GAP", 0),
        "CONFIDENCE_WEIGHT_OPEN_BIAS": getattr(config, "CONFIDENCE_WEIGHT_OPEN_BIAS", 0),
        # Auto-scan
        "AUTO_SCAN_SYMBOLS": getattr(config, "AUTO_SCAN_SYMBOLS", False),
        "AUTO_SCAN_TOP_N": getattr(config, "AUTO_SCAN_TOP_N", 10),
        "AUTO_SCAN_MIN_SCORE": getattr(config, "AUTO_SCAN_MIN_SCORE", 40),
        # Trade type
        "TRADE_TYPE": config.TRADE_TYPE,
    }


def _append(record: dict):
    """Append a single JSON record to the journal file."""
    try:
        with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:
        logger.error(f"Trade journal write failed: {e}")


# ─────────────────────── PUBLIC API ───────────────────────


def log_entry(
    symbol: str,
    entry_side: str,
    entry_price: float,
    sl_price: float,
    quantity: int,
    confidence: float,
    confidence_breakdown: dict,
    volume_ratio: float,
    breakout_strength: float,
    allocation_pct: float,
    capital_allocated: float,
    symbol_data: dict,
    nifty_bias: str = None,
    entry_window_state: str = None,
    account_balance: float = None,
    active_positions_count: int = 0,
    filters_passed: dict = None,
):
    """
    Call this right after a successful entry order.
    Captures every decision detail for post-session analysis.
    """
    risk_per_share = abs(entry_price - sl_price)
    target_price = (
        entry_price + risk_per_share * config.PROFIT_TARGET_RATIO
        if entry_side == "BUY"
        else entry_price - risk_per_share * config.PROFIT_TARGET_RATIO
    )
    range_size = symbol_data.get("high", 0) - symbol_data.get("low", 0)
    range_pct = (range_size / symbol_data.get("low", 1)) * 100 if symbol_data.get("low", 0) > 0 else 0

    record = {
        "event": "ENTRY",
        "date": _now_ist_date(),
        "timestamp": _now_ist_str(),
        "symbol": symbol,
        "exchange": symbol_data.get("exchange", "NSE"),
        "side": entry_side,
        "entry_price": _safe(entry_price),
        "sl_price": _safe(sl_price),
        "target_price": _safe(target_price),
        "risk_per_share": _safe(risk_per_share),
        "risk_reward_ratio": _safe(config.PROFIT_TARGET_RATIO),
        "quantity": quantity,
        "capital_allocated": _safe(capital_allocated),
        "allocation_pct": _safe(allocation_pct),
        # Opening range
        "opening_range": {
            "open": _safe(symbol_data.get("open")),
            "high": _safe(symbol_data.get("high")),
            "low": _safe(symbol_data.get("low")),
            "close": _safe(symbol_data.get("close")),
            "range_size": _safe(range_size),
            "range_pct": _safe(range_pct),
            "vwap": _safe(symbol_data.get("vwap")),
            "long_trigger": _safe(symbol_data.get("long_trigger")),
            "short_trigger": _safe(symbol_data.get("short_trigger")),
            "buffer": _safe(symbol_data.get("buffer")),
        },
        # Market context
        "gap_pct": _safe(symbol_data.get("gap_pct", 0)),
        "prev_close": _safe(symbol_data.get("prev_close", 0)),
        "open_bias": symbol_data.get("open_bias", "UNKNOWN"),
        "open_position_in_range": _safe(symbol_data.get("open_position_in_range")),
        "nifty_bias": nifty_bias,
        "entry_window_state": entry_window_state,
        # Scoring
        "confidence_score": _safe(confidence),
        "confidence_breakdown": {k: _safe(v) for k, v in (confidence_breakdown or {}).items()},
        "volume_ratio": _safe(volume_ratio),
        "breakout_strength": _safe(breakout_strength),
        # Filters (True = passed / not blocked)
        "filters_passed": filters_passed or {},
        # Account state
        "account_balance": _safe(account_balance),
        "active_positions": active_positions_count,
        # Config snapshot
        "config": _snapshot_config(),
    }

    _append(record)
    logger.info(f"📓 Trade journal: ENTRY logged for {symbol}")


def log_partial_exit(
    symbol: str,
    side: str,
    exit_price: float,
    quantity_exited: int,
    reason: str,
    entry_price: float,
    sl_price: float,
    r_multiple: float,
    realized_pnl: float,
    remaining_quantity: int,
    sl_moved_to_breakeven: bool = False,
):
    """Call after each partial booking (0.5R, 1R targets)."""
    pnl_this_exit = (
        (exit_price - entry_price) * quantity_exited
        if side == "BUY"
        else (entry_price - exit_price) * quantity_exited
    )

    record = {
        "event": "PARTIAL_EXIT",
        "date": _now_ist_date(),
        "timestamp": _now_ist_str(),
        "symbol": symbol,
        "side": side,
        "exit_price": _safe(exit_price),
        "quantity_exited": quantity_exited,
        "remaining_quantity": remaining_quantity,
        "reason": reason,
        "r_multiple_at_exit": _safe(r_multiple),
        "pnl_this_exit": _safe(pnl_this_exit),
        "cumulative_realized_pnl": _safe(realized_pnl),
        "entry_price": _safe(entry_price),
        "sl_price": _safe(sl_price),
        "sl_moved_to_breakeven": sl_moved_to_breakeven,
    }

    _append(record)
    logger.info(f"📓 Trade journal: PARTIAL_EXIT logged for {symbol} ({reason})")


def log_full_exit(
    symbol: str,
    side: str,
    exit_price: float,
    quantity_exited: int,
    reason: str,
    entry_price: float,
    sl_price: float,
    realized_pnl_from_partials: float,
    final_exit_pnl: float,
    total_pnl: float,
    entry_time: str = None,
    position_data: dict = None,
):
    """Call when a position is fully closed (SL, target, or EOD)."""
    hold_duration = None
    if entry_time:
        try:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
            if isinstance(entry_time, str):
                et = datetime.datetime.strptime(entry_time, "%Y-%m-%d %H:%M:%S")
            else:
                et = entry_time
            hold_duration = str(now - et)
        except Exception:
            pass

    pos = position_data or {}

    record = {
        "event": "FULL_EXIT",
        "date": _now_ist_date(),
        "timestamp": _now_ist_str(),
        "symbol": symbol,
        "side": side,
        "entry_price": _safe(entry_price),
        "exit_price": _safe(exit_price),
        "quantity_exited": quantity_exited,
        "reason": reason,
        "pnl_from_partials": _safe(realized_pnl_from_partials),
        "pnl_final_exit": _safe(final_exit_pnl),
        "total_pnl": _safe(total_pnl),
        "sl_price_at_exit": _safe(pos.get("sl_price")),
        "sl_was_at_breakeven": pos.get("sl_at_breakeven", False),
        "partial_booked_1": pos.get("partial_booked_1", False),
        "partial_booked_2": pos.get("partial_booked_2", False),
        "confidence_at_entry": _safe(pos.get("confidence")),
        "capital_allocated": _safe(pos.get("capital_allocated")),
        "hold_duration": hold_duration,
        "entry_time": str(entry_time) if entry_time else None,
    }

    _append(record)
    logger.info(f"📓 Trade journal: FULL_EXIT logged for {symbol} ({reason}) P&L ₹{total_pnl:,.2f}")


def log_session_summary(
    date: str,
    symbols_scanned: list,
    symbols_traded: list,
    total_pnl: float,
    account_balance: float,
    positions_entered: int,
    positions_closed: int,
    position_pnls: dict = None,
):
    """Call at end of trading day — one-liner summary."""
    record = {
        "event": "SESSION_SUMMARY",
        "date": date or _now_ist_date(),
        "timestamp": _now_ist_str(),
        "symbols_scanned": symbols_scanned,
        "symbols_traded": symbols_traded,
        "positions_entered": positions_entered,
        "positions_closed": positions_closed,
        "total_pnl": _safe(total_pnl),
        "per_symbol_pnl": {k: _safe(v) for k, v in (position_pnls or {}).items()},
        "account_balance": _safe(account_balance),
        "config_snapshot": _snapshot_config(),
    }

    _append(record)
    logger.info(f"📓 Trade journal: SESSION_SUMMARY logged — P&L ₹{total_pnl:,.2f}")
