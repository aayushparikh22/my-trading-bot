"""
Pre-Session ORB Stock Scanner
===============================
Runs before each trading session to dynamically pick the best stocks for ORB.

Uses Kite API to fetch the last 30 trading days of 5-min + 15-min data
for all NIFTY 50 stocks, then scores them on ORB-specific metrics:
  - Recent volatility (ATR%)
  - Volume trend (rising = better)
  - Clean breakout ratio
  - Gap quality
  - Recent ORB simulated win rate
  - Average R-multiple
  - Trend clarity

Called automatically by bot_kite.py before each daily session.
Can also be run standalone: python -m app_files.pre_session_scanner
"""

import os
import sys
import json
import logging
import time
from datetime import datetime, timedelta
from collections import defaultdict
import pytz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app_files import config

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

# Scanner configuration
LOOKBACK_DAYS = 30        # Analyze last 30 trading days
RECENT_WEIGHT_DAYS = 10   # Extra weight on last 10 days
TOP_N_PICKS = 10          # Pick top N stocks
MAX_PER_SECTOR = 2        # Max stocks per sector for diversification
MIN_SCORE = 40.0          # Minimum composite score to qualify

# Sector mapping for diversification
SECTORS = {
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking",
    "KOTAKBANK": "Banking", "AXISBANK": "Banking", "INDUSINDBK": "Banking",
    "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "SHRIRAMFIN": "Finance",
    "HDFCLIFE": "Insurance", "SBILIFE": "Insurance",
    "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT",
    "TECHM": "IT", "LTIM": "IT",
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy",
    "NTPC": "Power", "POWERGRID": "Power", "COALINDIA": "Mining",
    "ADANIPORTS": "Infra", "ADANIENT": "Conglomerate",
    "TATAMOTORS": "Auto", "MARUTI": "Auto", "M&M": "Auto",
    "BAJAJ-AUTO": "Auto", "EICHERMOT": "Auto", "HEROMOTOCO": "Auto",
    "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "HINDALCO": "Metals",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "TATACONSUM": "FMCG", "TITAN": "Consumer",
    "TRENT": "Retail",
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "APOLLOHOSP": "Healthcare",
    "LT": "Infra", "ULTRACEMCO": "Cement", "GRASIM": "Cement",
    "BHARTIARTL": "Telecom", "ASIANPAINT": "Paints",
}


def calculate_vwap(candles):
    """Calculate VWAP from candle data"""
    cum_tp_vol = 0.0
    cum_vol = 0
    for c in candles:
        tp = (c["high"] + c["low"] + c["close"]) / 3.0
        cum_tp_vol += tp * c["volume"]
        cum_vol += c["volume"]
    return cum_tp_vol / cum_vol if cum_vol > 0 else None


def score_stock_for_orb(symbol, candles_5min, candles_15min):
    """
    Score a single stock's ORB readiness based on recent candle data.
    
    Args:
        symbol: Stock symbol
        candles_5min: List of 5-min candle dicts (last ~30 days)
        candles_15min: List of 15-min candle dicts (last ~30 days)
    
    Returns:
        Dict with scores and metrics, or None if insufficient data
    """
    if not candles_5min or not candles_15min:
        return None

    # Group candles by date
    by_date_5 = defaultdict(list)
    by_date_15 = defaultdict(list)
    for c in candles_5min:
        dt = c["date"] if isinstance(c["date"], datetime) else datetime.fromisoformat(str(c["date"]))
        by_date_5[dt.date()].append(c)
    for c in candles_15min:
        dt = c["date"] if isinstance(c["date"], datetime) else datetime.fromisoformat(str(c["date"]))
        by_date_15[dt.date()].append(c)

    all_days = sorted(by_date_5.keys())
    if len(all_days) < 5:
        return None

    recent_days = all_days[-LOOKBACK_DAYS:] if len(all_days) >= LOOKBACK_DAYS else all_days

    # Track metrics
    daily_atr_pcts = []
    daily_volumes = []
    daily_gaps = []
    daily_ranges_pct = []
    orb_results = []
    clean_breakout_days = 0
    total_signal_days = 0
    prev_close = None

    for day in recent_days:
        c5 = by_date_5.get(day, [])
        c15 = by_date_15.get(day, [])
        if not c5 or not c15:
            continue

        # Get opening 15-min candle
        opening_15 = None
        for c in c15:
            dt = c["date"] if isinstance(c["date"], datetime) else datetime.fromisoformat(str(c["date"]))
            if dt.hour == 9 and dt.minute == 15:
                opening_15 = c
                break
        if not opening_15:
            opening_15 = c15[0]

        o = opening_15["open"]
        h = opening_15["high"]
        l = opening_15["low"]

        if h <= 0 or l <= 0 or h <= l:
            prev_close = c5[-1]["close"] if c5 else None
            continue

        price = (h + l) / 2
        range_pct = (h - l) / price * 100
        daily_ranges_pct.append(range_pct)

        # Daily volume
        day_vol = sum(c["volume"] for c in c5)
        daily_volumes.append(day_vol)

        # Gap from previous close
        if prev_close and prev_close > 0:
            gap_pct = (o - prev_close) / prev_close * 100
            daily_gaps.append(gap_pct)

        # ATR from intraday candles
        tr_values = []
        for i in range(1, len(c5)):
            tr = max(
                c5[i]["high"] - c5[i]["low"],
                abs(c5[i]["high"] - c5[i-1]["close"]),
                abs(c5[i]["low"] - c5[i-1]["close"])
            )
            tr_values.append(tr)
        if tr_values:
            atr = sum(tr_values[-10:]) / min(10, len(tr_values[-10:]))
            atr_pct = atr / price * 100
            daily_atr_pcts.append(atr_pct)

        # --- Simulate ORB for this day ---
        vwap_candles = [c for c in c5
                        if (c["date"] if isinstance(c["date"], datetime) else datetime.fromisoformat(str(c["date"]))).hour == 9
                        and (c["date"] if isinstance(c["date"], datetime) else datetime.fromisoformat(str(c["date"]))).minute < 35]
        vwap = calculate_vwap(vwap_candles) if vwap_candles else None
        if not vwap:
            prev_close = c5[-1]["close"] if c5 else None
            continue

        # ATR buffer
        pre = [c for c in c5
               if (c["date"] if isinstance(c["date"], datetime) else datetime.fromisoformat(str(c["date"]))).hour == 9
               and (c["date"] if isinstance(c["date"], datetime) else datetime.fromisoformat(str(c["date"]))).minute <= 30]
        if len(pre) > 2:
            pre_trs = []
            for i in range(1, len(pre)):
                tr = max(pre[i]["high"] - pre[i]["low"],
                         abs(pre[i]["high"] - pre[i-1]["close"]),
                         abs(pre[i]["low"] - pre[i-1]["close"]))
                pre_trs.append(tr)
            atr_buf = sum(pre_trs) / len(pre_trs) if pre_trs else 0
            buffer = config.ATR_MULTIPLIER * atr_buf
        else:
            buffer = config.BUFFER_AMOUNT

        long_trigger = h + buffer
        short_trigger = l - buffer

        # Scan 9:30-10:30 for signals
        entry_side = None
        entry_price = None
        entry_idx = None
        cur_vwap = vwap

        for idx, candle in enumerate(c5):
            ct = candle["date"] if isinstance(candle["date"], datetime) else datetime.fromisoformat(str(candle["date"]))
            hhmm = ct.hour * 100 + ct.minute
            if hhmm < 930:
                continue
            if hhmm > 1030:
                break

            cc = candle["close"]
            rv = calculate_vwap(c5[:idx + 1])
            if rv:
                cur_vwap = rv

            if cc > long_trigger and cc > cur_vwap:
                entry_side = "BUY"
                entry_price = cc
                entry_idx = idx
                break
            elif cc < short_trigger and cc < cur_vwap:
                entry_side = "SELL"
                entry_price = cc
                entry_idx = idx
                break

        if entry_side and entry_price and entry_idx is not None:
            total_signal_days += 1

            if entry_side == "BUY":
                raw_sl = min(vwap, c5[entry_idx]["low"])
                risk = entry_price - raw_sl
                sl = entry_price - risk * config.STOPLOSS_DISTANCE_FACTOR
            else:
                raw_sl = max(vwap, c5[entry_idx]["high"])
                risk = raw_sl - entry_price
                sl = entry_price + risk * config.STOPLOSS_DISTANCE_FACTOR

            if risk <= 0:
                prev_close = c5[-1]["close"] if c5 else None
                continue

            max_favorable = 0
            exit_price = entry_price

            for candle in c5[entry_idx + 1:]:
                ct = candle["date"] if isinstance(candle["date"], datetime) else datetime.fromisoformat(str(candle["date"]))
                if ct.hour == 15 and ct.minute >= 25:
                    exit_price = candle["close"]
                    break

                if entry_side == "BUY":
                    favorable = candle["high"] - entry_price
                    if candle["low"] <= sl:
                        exit_price = sl
                        break
                else:
                    favorable = entry_price - candle["low"]
                    if candle["high"] >= sl:
                        exit_price = sl
                        break

                max_favorable = max(max_favorable, favorable)
                exit_price = candle["close"]

            pnl = (exit_price - entry_price) if entry_side == "BUY" else (entry_price - exit_price)
            r_multiple = pnl / risk if risk > 0 else 0
            max_r = max_favorable / risk if risk > 0 else 0

            orb_results.append({"pnl_r": r_multiple, "max_r": max_r})
            if max_r >= 0.5:
                clean_breakout_days += 1

        prev_close = c5[-1]["close"] if c5 else None

    # --- Calculate Scores ---
    if not daily_atr_pcts or not orb_results:
        return None

    recent_atr = daily_atr_pcts[-RECENT_WEIGHT_DAYS:] if len(daily_atr_pcts) >= RECENT_WEIGHT_DAYS else daily_atr_pcts
    avg_atr_pct = sum(recent_atr) / len(recent_atr)

    # 1. Volatility Score
    if avg_atr_pct < 0.15:
        vol_score = 10
    elif avg_atr_pct < 0.3:
        vol_score = 30 + (avg_atr_pct - 0.15) / 0.15 * 30
    elif avg_atr_pct <= 1.2:
        vol_score = 60 + (avg_atr_pct - 0.3) / 0.9 * 40
    else:
        vol_score = max(50, 100 - (avg_atr_pct - 1.2) * 20)

    # 2. Volume Trend Score
    if len(daily_volumes) >= 10:
        first_half = daily_volumes[:len(daily_volumes) // 2]
        second_half = daily_volumes[len(daily_volumes) // 2:]
        avg_first = sum(first_half) / len(first_half) if first_half else 1
        avg_second = sum(second_half) / len(second_half) if second_half else 1
        vol_trend = avg_second / avg_first if avg_first > 0 else 1
        volume_score = min(100, max(0, 50 + (vol_trend - 1) * 100))
    else:
        volume_score = 50

    # 3. Clean Breakout Ratio
    breakout_ratio = clean_breakout_days / total_signal_days * 100 if total_signal_days > 0 else 0
    breakout_score = min(100, breakout_ratio * 1.2)

    # 4. Gap Quality
    if daily_gaps:
        abs_gaps = [abs(g) for g in daily_gaps[-RECENT_WEIGHT_DAYS:]]
        avg_abs_gap = sum(abs_gaps) / len(abs_gaps)
        if 0.2 <= avg_abs_gap <= 1.5:
            gap_score = 80 + min(20, (avg_abs_gap - 0.2) * 15)
        elif avg_abs_gap < 0.2:
            gap_score = 30 + avg_abs_gap / 0.2 * 50
        else:
            gap_score = max(30, 100 - (avg_abs_gap - 1.5) * 20)
    else:
        gap_score = 40

    # 5. Recent ORB Win Rate (HEAVILY WEIGHTED)
    recent_orb = orb_results[-RECENT_WEIGHT_DAYS:] if len(orb_results) >= RECENT_WEIGHT_DAYS else orb_results
    wins = [r for r in recent_orb if r["pnl_r"] > 0]
    recent_wr = len(wins) / len(recent_orb) * 100 if recent_orb else 0
    wr_score = min(100, recent_wr * 1.1)

    # 6. R-Multiple Quality
    avg_r = sum(r["pnl_r"] for r in recent_orb) / len(recent_orb) if recent_orb else 0
    r_score = min(100, max(0, 50 + avg_r * 50))

    # 7. Trend Clarity
    recent_closes = []
    for d in recent_days[-RECENT_WEIGHT_DAYS:]:
        c5 = by_date_5.get(d, [])
        if c5:
            recent_closes.append(c5[-1]["close"])
    if len(recent_closes) > 5:
        sma = sum(recent_closes) / len(recent_closes)
        above = sum(1 for c in recent_closes if c > sma)
        ratio = above / len(recent_closes)
        trend_score = abs(ratio - 0.5) * 2 * 100
    else:
        trend_score = 50

    # 8. Range Quality
    if daily_ranges_pct:
        recent_ranges = daily_ranges_pct[-RECENT_WEIGHT_DAYS:]
        avg_range = sum(recent_ranges) / len(recent_ranges)
        if 0.3 <= avg_range <= 1.5:
            range_score = 90
        elif avg_range < 0.3:
            range_score = 30 + avg_range / 0.3 * 50
        else:
            range_score = max(30, 90 - (avg_range - 1.5) * 30)
    else:
        range_score = 50

    # Composite Score
    composite = (
        vol_score * 0.15 +
        volume_score * 0.10 +
        breakout_score * 0.15 +
        gap_score * 0.05 +
        wr_score * 0.25 +
        r_score * 0.15 +
        trend_score * 0.10 +
        range_score * 0.05
    )

    # Full period stats
    all_wr = sum(1 for r in orb_results if r["pnl_r"] > 0) / len(orb_results) * 100 if orb_results else 0
    gross_win = sum(r["pnl_r"] for r in orb_results if r["pnl_r"] > 0)
    gross_loss = abs(sum(r["pnl_r"] for r in orb_results if r["pnl_r"] < 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 99.0

    return {
        "symbol": symbol,
        "sector": SECTORS.get(symbol, "Unknown"),
        "composite_score": round(composite, 1),
        "recent_wr": round(recent_wr, 1),
        "full_wr": round(all_wr, 1),
        "avg_r": round(avg_r, 2),
        "profit_factor": round(min(pf, 99), 2),
        "avg_atr_pct": round(avg_atr_pct, 3),
        "total_signals": total_signal_days,
        "total_days": len(recent_days),
    }


def run_pre_session_scan(kite_service, top_n=TOP_N_PICKS):
    """
    Run the pre-session scanner using live Kite API data.
    
    Args:
        kite_service: Initialized KiteService instance
        top_n: Number of stocks to pick
    
    Returns:
        List of symbol strings (the top picks for today)
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info("🎯 PRE-SESSION ORB SCANNER — Picking today's best stocks")
    logger.info(f"   Analyzing last {LOOKBACK_DAYS} trading days for all NIFTY 50 stocks")
    logger.info("=" * 70)

    # Get all symbols from config
    all_symbols = config.SYMBOLS_TO_MONITOR

    # Date range: last 45 calendar days (covers ~30 trading days)
    now = datetime.now(IST)
    to_date = now.strftime("%Y-%m-%d")
    from_date = (now - timedelta(days=50)).strftime("%Y-%m-%d")

    results = []
    scanned = 0
    failed = 0

    for sym_config in all_symbols:
        symbol = sym_config["symbol"]
        exchange = sym_config["exchange"]

        try:
            # Find instrument token
            token = kite_service.find_instrument_token(exchange, symbol)
            if not token:
                logger.debug(f"  ✗ {symbol}: No token found, skipping")
                failed += 1
                continue

            # Fetch 5-min candles
            candles_5 = kite_service.get_historical_data(token, from_date, to_date, "5minute")
            time.sleep(0.35)  # Rate limiting

            # Fetch 15-min candles
            candles_15 = kite_service.get_historical_data(token, from_date, to_date, "15minute")
            time.sleep(0.35)  # Rate limiting

            if not candles_5 or not candles_15:
                logger.debug(f"  ✗ {symbol}: No candle data, skipping")
                failed += 1
                continue

            # Normalize candle format (Kite returns different format)
            norm_5 = _normalize_candles(candles_5)
            norm_15 = _normalize_candles(candles_15)

            # Score this stock
            result = score_stock_for_orb(symbol, norm_5, norm_15)
            if result:
                results.append(result)
                scanned += 1
                logger.info(f"  ✓ {symbol:12s} Score: {result['composite_score']:5.1f} | "
                           f"WR: {result['recent_wr']:5.1f}% | PF: {result['profit_factor']:5.2f}")
            else:
                logger.debug(f"  ⚠ {symbol}: Insufficient signals")
                failed += 1

        except Exception as e:
            logger.warning(f"  ✗ {symbol}: Error — {str(e)[:60]}")
            failed += 1
            continue

    logger.info(f"\n  Scanned: {scanned} | Failed: {failed}")

    if not results:
        logger.warning("❌ Scanner returned no results — falling back to config FOCUS_SYMBOLS")
        return getattr(config, 'FOCUS_SYMBOLS', [])

    # Sort by composite score
    results.sort(key=lambda x: x["composite_score"], reverse=True)

    # Pick top N with sector diversification
    picked = []
    for r in results:
        sector = r["sector"]
        if sum(1 for p in picked if p["sector"] == sector) >= MAX_PER_SECTOR:
            continue
        if r["composite_score"] < MIN_SCORE:
            continue
        picked.append(r)
        if len(picked) >= top_n:
            break

    # If we don't have enough, relax sector constraint
    if len(picked) < 5:
        for r in results:
            if r["symbol"] not in [p["symbol"] for p in picked]:
                if r["composite_score"] >= MIN_SCORE:
                    picked.append(r)
                    if len(picked) >= top_n:
                        break

    # Log results
    logger.info("")
    logger.info("🏆 TODAY'S ORB PICKS (Auto-Selected)")
    logger.info("-" * 60)
    for i, r in enumerate(picked):
        logger.info(f"  {i+1:2d}. {r['symbol']:12s} ({r['sector']:10s}) — "
                    f"Score {r['composite_score']:5.1f} | WR {r['recent_wr']:5.1f}% | "
                    f"PF {r['profit_factor']:.2f}")

    # Compare with previous config
    old_focus = getattr(config, 'FOCUS_SYMBOLS', [])
    new_focus = [r["symbol"] for r in picked]
    added = set(new_focus) - set(old_focus)
    removed = set(old_focus) - set(new_focus)
    if added:
        logger.info(f"  ➕ Added:   {', '.join(sorted(added))}")
    if removed:
        logger.info(f"  ➖ Removed: {', '.join(sorted(removed))}")
    logger.info("")

    # Save scan results to file for reference
    _save_scan_results(results, picked)

    return new_focus


def run_pre_session_scan_from_files(top_n=TOP_N_PICKS):
    """
    Run the pre-session scanner using local backtest data files.
    Fallback when Kite API is not available (e.g., before market hours).
    
    Returns:
        List of symbol strings (the top picks)
    """
    from backtest.orb_readiness_scanner import analyze_stock, SECTORS as SCAN_SECTORS

    logger.info("")
    logger.info("=" * 70)
    logger.info("🎯 PRE-SESSION ORB SCANNER (from local data)")
    logger.info(f"   Analyzing last {LOOKBACK_DAYS} trading days")
    logger.info("=" * 70)

    data_dir = os.path.join(os.path.dirname(__file__), '..', 'backtest', 'data')
    all_symbols = set()
    for f in os.listdir(data_dir):
        if f.endswith("_5min.json") and f not in ("NIFTY50_5min.json", "NIFTYBEES_5min.json"):
            all_symbols.add(f.replace("_5min.json", ""))

    results = []
    for sym in sorted(all_symbols):
        r = analyze_stock(sym, LOOKBACK_DAYS)
        if r:
            results.append(r)

    if not results:
        logger.warning("❌ Scanner returned no results — falling back to config FOCUS_SYMBOLS")
        return getattr(config, 'FOCUS_SYMBOLS', [])

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    picked = []
    for r in results:
        sector = SCAN_SECTORS.get(r["symbol"], "Unknown")
        if sum(1 for p in picked if SCAN_SECTORS.get(p["symbol"], "") == sector) >= MAX_PER_SECTOR:
            continue
        if r["composite_score"] < MIN_SCORE:
            continue
        picked.append(r)
        if len(picked) >= top_n:
            break

    if len(picked) < 5:
        for r in results:
            if r["symbol"] not in [p["symbol"] for p in picked]:
                if r["composite_score"] >= MIN_SCORE:
                    picked.append(r)
                    if len(picked) >= top_n:
                        break

    new_focus = [r["symbol"] for r in picked]

    logger.info("🏆 TODAY'S ORB PICKS (from local data)")
    logger.info("-" * 60)
    for i, r in enumerate(picked):
        sector = SCAN_SECTORS.get(r["symbol"], "?")
        logger.info(f"  {i+1:2d}. {r['symbol']:12s} ({sector:10s}) — "
                    f"Score {r['composite_score']:5.1f} | WR {r['recent_wr']:5.1f}%")
    logger.info("")

    return new_focus


def _normalize_candles(candles):
    """Normalize Kite historical data to standard format"""
    normalized = []
    for c in candles:
        if isinstance(c, dict):
            # Already dict format
            nc = {
                "date": c.get("date", ""),
                "open": c.get("open", 0),
                "high": c.get("high", 0),
                "low": c.get("low", 0),
                "close": c.get("close", 0),
                "volume": c.get("volume", 0),
            }
        else:
            # Kite sometimes returns list format: [date, o, h, l, c, v]
            nc = {
                "date": c[0] if len(c) > 0 else "",
                "open": c[1] if len(c) > 1 else 0,
                "high": c[2] if len(c) > 2 else 0,
                "low": c[3] if len(c) > 3 else 0,
                "close": c[4] if len(c) > 4 else 0,
                "volume": c[5] if len(c) > 5 else 0,
            }
        # Ensure date is datetime
        if isinstance(nc["date"], str) and nc["date"]:
            nc["date"] = datetime.fromisoformat(nc["date"])
        if isinstance(nc["date"], datetime) and nc["date"].tzinfo is None:
            nc["date"] = IST.localize(nc["date"])
        normalized.append(nc)
    return normalized


def _save_scan_results(all_results, picked):
    """Save scan results to JSON for reference"""
    try:
        results_dir = os.path.join(os.path.dirname(__file__), '..', 'backtest', 'results')
        os.makedirs(results_dir, exist_ok=True)
        output = {
            "scan_date": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "scanner": "pre_session_auto",
            "top_picks": [r["symbol"] for r in picked],
            "top_picks_detail": picked,
            "all_ranked": all_results,
        }
        with open(os.path.join(results_dir, "pre_session_scan.json"), 'w') as f:
            json.dump(output, f, indent=2, default=str)
    except Exception as e:
        logger.debug(f"Could not save scan results: {e}")


# Standalone runner
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    # Use local file mode when run standalone
    top_picks = run_pre_session_scan_from_files()
    print(f"\nFOCUS_SYMBOLS = {json.dumps(top_picks, indent=4)}")
