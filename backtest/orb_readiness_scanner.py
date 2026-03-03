"""
ORB Readiness Scanner — Picks the BEST stocks for ORB strategy TODAY
=====================================================================
Unlike the historical backtester, this analyzes RECENT market behavior
to find stocks that are currently in the best condition for ORB trading.

Metrics scored:
1. Recent Volatility (ATR% of price) — ORB needs volatility to trigger breakouts
2. Volume Trend — Rising volume = more conviction in breakouts
3. Clean Breakout Ratio — How often recent days had clean ORB triggers (not choppy)
4. Gap Behavior — Moderate gaps (0.3-1.5%) are ideal for ORB
5. Trend Clarity — Stocks in a clear trend (up or down) give better ORB signals
6. Recent ORB Win Rate — Simulated ORB performance in last 20-30 trading days
7. Average R-Multiple — How far winners run (higher = more profit potential)

Output: Ranked list of stocks best suited for ORB trading RIGHT NOW
"""

import os
import sys
import json
import math
from datetime import datetime, timedelta, date as dt_date
from collections import defaultdict
import pytz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app_files import config

IST = pytz.timezone('Asia/Kolkata')
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# How many recent trading days to analyze
RECENT_DAYS = 30  # ~1.5 months of trading
VERY_RECENT_DAYS = 10  # Last 2 weeks (heavier weight)


def load_data(symbol, interval):
    filepath = os.path.join(DATA_DIR, f"{symbol}_{interval}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        data = json.load(f)
    candles = data.get("candles", [])
    for c in candles:
        c["date"] = datetime.fromisoformat(c["date"])
        if c["date"].tzinfo is None:
            c["date"] = IST.localize(c["date"])
    return candles


def group_by_date(candles):
    by_date = defaultdict(list)
    for c in candles:
        by_date[c["date"].date()].append(c)
    return dict(by_date)


def calculate_vwap(candles):
    cum_tp_vol = 0.0
    cum_vol = 0
    for c in candles:
        tp = (c["high"] + c["low"] + c["close"]) / 3.0
        cum_tp_vol += tp * c["volume"]
        cum_vol += c["volume"]
    return cum_tp_vol / cum_vol if cum_vol > 0 else None


def analyze_stock(symbol, recent_n=RECENT_DAYS):
    """Analyze a single stock's ORB readiness using recent data"""
    candles_5 = load_data(symbol, "5min")
    candles_15 = load_data(symbol, "15min")
    if not candles_5 or not candles_15:
        return None

    by_date_5 = group_by_date(candles_5)
    by_date_15 = group_by_date(candles_15)

    all_days = sorted(by_date_5.keys())
    if len(all_days) < recent_n + 5:
        recent_days = all_days
    else:
        recent_days = all_days[-recent_n:]

    if len(recent_days) < 5:
        return None

    # Track metrics across recent days
    daily_atr_pcts = []
    daily_volumes = []
    daily_gaps = []
    daily_ranges_pct = []
    orb_results = []  # (day, side, entry, exit_price, pnl_r)
    clean_breakout_days = 0
    total_signal_days = 0
    breakout_magnitudes = []  # How far past trigger price went (in R)

    prev_close = None

    for day in recent_days:
        c5 = by_date_5.get(day, [])
        c15 = by_date_15.get(day, [])
        if not c5 or not c15:
            continue

        # Get opening 15-min candle
        opening_15 = None
        for c in c15:
            if c["date"].hour == 9 and c["date"].minute == 15:
                opening_15 = c
                break
        if not opening_15:
            opening_15 = c15[0]

        o = opening_15["open"]
        h = opening_15["high"]
        l = opening_15["low"]
        cl = opening_15["close"]

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

        # ---- Simulate ORB for this day ----
        vwap_candles = [c for c in c5 if c["date"].hour == 9 and c["date"].minute < 35]
        vwap = calculate_vwap(vwap_candles) if vwap_candles else None
        if not vwap:
            prev_close = c5[-1]["close"] if c5 else None
            continue

        # ATR buffer
        pre = [c for c in c5 if c["date"].hour == 9 and c["date"].minute <= 30]
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

        for idx, candle in enumerate(c5):
            ct = candle["date"]
            hhmm = ct.hour * 100 + ct.minute
            if hhmm < 930:
                continue
            if hhmm > 1030:
                break

            cc = candle["close"]
            # Rolling VWAP
            rv = calculate_vwap(c5[:idx+1])
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

            # Calculate SL
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

            # Track how the trade played out
            max_favorable = 0
            max_adverse = 0
            exit_price = entry_price
            exit_reason = "EOD"

            for candle in c5[entry_idx+1:]:
                ct = candle["date"]
                if ct.hour == 15 and ct.minute >= 25:
                    exit_price = candle["close"]
                    exit_reason = "EOD"
                    break

                if entry_side == "BUY":
                    favorable = candle["high"] - entry_price
                    adverse = entry_price - candle["low"]
                    if candle["low"] <= sl:
                        exit_price = sl
                        exit_reason = "SL"
                        break
                else:
                    favorable = entry_price - candle["low"]
                    adverse = candle["high"] - entry_price
                    if candle["high"] >= sl:
                        exit_price = sl
                        exit_reason = "SL"
                        break

                max_favorable = max(max_favorable, favorable)
                max_adverse = max(max_adverse, adverse)
                exit_price = candle["close"]

            # Calculate R-multiple
            if entry_side == "BUY":
                pnl = exit_price - entry_price
            else:
                pnl = entry_price - exit_price

            r_multiple = pnl / risk if risk > 0 else 0
            max_r = max_favorable / risk if risk > 0 else 0

            orb_results.append({
                "day": day,
                "side": entry_side,
                "entry": entry_price,
                "exit": exit_price,
                "pnl_r": r_multiple,
                "max_r": max_r,
                "exit_reason": exit_reason,
            })

            if max_r >= 0.5:
                clean_breakout_days += 1
            breakout_magnitudes.append(max_r)

        prev_close = c5[-1]["close"] if c5 else None

    # ---- Calculate Scores ----
    if not daily_atr_pcts or not orb_results:
        return None

    # 1. Volatility Score (0-100): Higher ATR% = better for ORB
    avg_atr_pct = sum(daily_atr_pcts[-VERY_RECENT_DAYS:]) / len(daily_atr_pcts[-VERY_RECENT_DAYS:])
    # Ideal ATR% range for ORB: 0.3% - 1.5%
    if avg_atr_pct < 0.15:
        vol_score = 10
    elif avg_atr_pct < 0.3:
        vol_score = 30 + (avg_atr_pct - 0.15) / 0.15 * 30
    elif avg_atr_pct <= 1.2:
        vol_score = 60 + (avg_atr_pct - 0.3) / 0.9 * 40
    else:
        vol_score = max(50, 100 - (avg_atr_pct - 1.2) * 20)  # Too volatile = worse

    # 2. Volume Trend Score (0-100): Rising volume is better
    if len(daily_volumes) >= 10:
        first_half = daily_volumes[:len(daily_volumes)//2]
        second_half = daily_volumes[len(daily_volumes)//2:]
        avg_first = sum(first_half) / len(first_half) if first_half else 1
        avg_second = sum(second_half) / len(second_half) if second_half else 1
        vol_trend_ratio = avg_second / avg_first if avg_first > 0 else 1
        volume_score = min(100, max(0, 50 + (vol_trend_ratio - 1) * 100))
    else:
        volume_score = 50

    # 3. Clean Breakout Ratio (0-100)
    breakout_ratio = clean_breakout_days / total_signal_days * 100 if total_signal_days > 0 else 0
    breakout_score = min(100, breakout_ratio * 1.2)

    # 4. Gap Behavior Score (0-100): Moderate gaps are ideal
    if daily_gaps:
        abs_gaps = [abs(g) for g in daily_gaps[-VERY_RECENT_DAYS:]]
        avg_abs_gap = sum(abs_gaps) / len(abs_gaps)
        # Ideal gap: 0.3-1.5%
        if 0.2 <= avg_abs_gap <= 1.5:
            gap_score = 80 + min(20, (avg_abs_gap - 0.2) * 15)
        elif avg_abs_gap < 0.2:
            gap_score = 30 + avg_abs_gap / 0.2 * 50
        else:
            gap_score = max(30, 100 - (avg_abs_gap - 1.5) * 20)
    else:
        gap_score = 40

    # 5. Recent ORB Win Rate (0-100) — HEAVILY WEIGHTED
    recent_orb = orb_results[-VERY_RECENT_DAYS:] if len(orb_results) >= VERY_RECENT_DAYS else orb_results
    wins = [r for r in recent_orb if r["pnl_r"] > 0]
    recent_wr = len(wins) / len(recent_orb) * 100 if recent_orb else 0
    wr_score = min(100, recent_wr * 1.1)

    # 6. Average R-Multiple (0-100)
    avg_r = sum(r["pnl_r"] for r in recent_orb) / len(recent_orb) if recent_orb else 0
    r_score = min(100, max(0, 50 + avg_r * 50))

    # 7. Trend Clarity (0-100): Price consistently above/below VWAP
    # Use recent closes vs simple moving average
    recent_closes = [c5[-1]["close"] for c5 in [by_date_5.get(d, []) for d in recent_days[-VERY_RECENT_DAYS:]] if c5]
    if len(recent_closes) > 5:
        sma = sum(recent_closes) / len(recent_closes)
        above = sum(1 for c in recent_closes if c > sma)
        ratio = above / len(recent_closes)
        # Closer to 0 or 1 = clearer trend
        trend_clarity = abs(ratio - 0.5) * 2  # 0 to 1
        trend_score = trend_clarity * 100
    else:
        trend_score = 50

    # 8. Range Quality Score — opening ranges not too tight or too wide
    if daily_ranges_pct:
        recent_ranges = daily_ranges_pct[-VERY_RECENT_DAYS:]
        avg_range = sum(recent_ranges) / len(recent_ranges)
        if 0.3 <= avg_range <= 1.5:
            range_score = 90
        elif avg_range < 0.3:
            range_score = 30 + avg_range / 0.3 * 50
        else:
            range_score = max(30, 90 - (avg_range - 1.5) * 30)
    else:
        range_score = 50

    # ---- COMPOSITE SCORE ----
    # Weight recent ORB performance and volatility highest
    composite = (
        vol_score * 0.15 +        # Volatility
        volume_score * 0.10 +     # Volume trend
        breakout_score * 0.15 +   # Clean breakouts
        gap_score * 0.05 +        # Gap quality
        wr_score * 0.25 +         # Recent win rate (HIGHEST)
        r_score * 0.15 +          # R-multiple quality
        trend_score * 0.10 +      # Trend clarity
        range_score * 0.05        # Range quality
    )

    # Full period stats
    all_wins = [r for r in orb_results if r["pnl_r"] > 0]
    all_wr = len(all_wins) / len(orb_results) * 100 if orb_results else 0
    all_avg_r = sum(r["pnl_r"] for r in orb_results) / len(orb_results) if orb_results else 0
    total_r = sum(r["pnl_r"] for r in orb_results)

    # Profit factor
    gross_win_r = sum(r["pnl_r"] for r in orb_results if r["pnl_r"] > 0)
    gross_loss_r = abs(sum(r["pnl_r"] for r in orb_results if r["pnl_r"] < 0))
    pf = gross_win_r / gross_loss_r if gross_loss_r > 0 else 99.0

    # Recent momentum (last 10 days vs prior, extra boost/penalty)
    if len(orb_results) >= 10:
        recent_10_r = sum(r["pnl_r"] for r in orb_results[-10:])
        prior_r = sum(r["pnl_r"] for r in orb_results[:-10]) / max(1, len(orb_results) - 10) * 10
        momentum = recent_10_r - prior_r
    else:
        momentum = 0
        recent_10_r = sum(r["pnl_r"] for r in orb_results)

    return {
        "symbol": symbol,
        "composite_score": round(composite, 1),
        "total_signals": total_signal_days,
        "full_wr": round(all_wr, 1),
        "recent_wr": round(recent_wr, 1),
        "avg_r": round(all_avg_r, 2),
        "total_r": round(total_r, 2),
        "profit_factor": round(pf, 2),
        "avg_atr_pct": round(avg_atr_pct, 3),
        "avg_gap_pct": round(sum(abs(g) for g in daily_gaps[-10:]) / max(1, len(daily_gaps[-10:])), 2) if daily_gaps else 0,
        "vol_score": round(vol_score, 0),
        "volume_score": round(volume_score, 0),
        "breakout_score": round(breakout_score, 0),
        "wr_score": round(wr_score, 0),
        "r_score": round(r_score, 0),
        "trend_score": round(trend_score, 0),
        "range_score": round(range_score, 0),
        "momentum": round(momentum, 2),
        "recent_10d_r": round(recent_10_r, 2),
        "clean_breakouts": clean_breakout_days,
        "last_date": str(recent_days[-1]),
    }


# Sector mapping
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


def main():
    # Get all NIFTY 50 symbols from data files
    all_symbols = set()
    for f in os.listdir(DATA_DIR):
        if f.endswith("_5min.json") and f != "NIFTY50_5min.json" and f != "NIFTYBEES_5min.json":
            sym = f.replace("_5min.json", "")
            all_symbols.add(sym)

    print("=" * 100)
    print("🎯 ORB READINESS SCANNER — Best Stocks for TODAY's ORB Strategy")
    print(f"   Analyzing last {RECENT_DAYS} trading days | Extra weight on last {VERY_RECENT_DAYS} days")
    print("=" * 100)

    results = []
    for sym in sorted(all_symbols):
        r = analyze_stock(sym, RECENT_DAYS)
        if r:
            results.append(r)
            print(f"  ✓ {sym:12s} scanned → Score: {r['composite_score']:5.1f} | WR: {r['recent_wr']:5.1f}% | Signals: {r['total_signals']:2d}")

    if not results:
        print("\n❌ No results. Check data files.")
        return

    # Sort by composite score
    results.sort(key=lambda x: x["composite_score"], reverse=True)

    print("\n" + "=" * 100)
    print("📊 RANKED: Best Stocks for ORB Strategy RIGHT NOW")
    print("=" * 100)
    print(f"{'#':>3} {'Symbol':12s} {'Sector':10s} {'Score':>6} {'RecentWR':>9} {'FullWR':>7} {'AvgR':>6} {'TotalR':>7} {'PF':>6} {'ATR%':>6} {'Signals':>8} {'Momentum':>9} {'Last10dR':>9}")
    print("-" * 100)

    for i, r in enumerate(results):
        sector = SECTORS.get(r["symbol"], "?")
        marker = " ★" if r["composite_score"] >= 65 else "  " if r["composite_score"] >= 50 else " ✗"
        print(f"{i+1:3d} {r['symbol']:12s} {sector:10s} {r['composite_score']:6.1f} {r['recent_wr']:8.1f}% {r['full_wr']:6.1f}% {r['avg_r']:+6.2f} {r['total_r']:+7.2f} {r['profit_factor']:6.2f} {r['avg_atr_pct']:5.3f}% {r['total_signals']:7d} {r['momentum']:+9.2f} {r['recent_10d_r']:+9.2f}{marker}")

    # Top picks with sector diversification
    print("\n" + "=" * 100)
    print("🏆 TOP PICKS FOR TODAY (Sector-Diversified)")
    print("=" * 100)

    picked = []
    sectors_used = set()
    for r in results:
        sector = SECTORS.get(r["symbol"], "Unknown")
        # Allow max 2 per sector
        if sum(1 for s in picked if SECTORS.get(s["symbol"], "") == sector) >= 2:
            continue
        if r["composite_score"] < 40:
            continue
        picked.append(r)
        sectors_used.add(sector)
        if len(picked) >= 12:
            break

    print(f"\n{'#':>3} {'Symbol':12s} {'Sector':10s} {'Score':>6} {'Why This Stock':50s}")
    print("-" * 90)
    for i, r in enumerate(picked):
        sector = SECTORS.get(r["symbol"], "?")
        reasons = []
        if r["recent_wr"] >= 60:
            reasons.append(f"Hot WR {r['recent_wr']:.0f}%")
        if r["momentum"] > 1:
            reasons.append(f"Momentum +{r['momentum']:.1f}R")
        if r["avg_atr_pct"] >= 0.4:
            reasons.append(f"High ATR {r['avg_atr_pct']:.2f}%")
        if r["profit_factor"] >= 1.5:
            reasons.append(f"Strong PF {r['profit_factor']:.1f}")
        if r["recent_10d_r"] > 0:
            reasons.append(f"Last 10d: +{r['recent_10d_r']:.1f}R")
        if r["trend_score"] >= 70:
            reasons.append("Clear trend")
        if not reasons:
            reasons.append(f"WR {r['recent_wr']:.0f}%, PF {r['profit_factor']:.1f}")
        print(f"{i+1:3d} {r['symbol']:12s} {sector:10s} {r['composite_score']:6.1f}  {' | '.join(reasons)}")

    # Score breakdown for top 5
    print(f"\n📈 SCORE BREAKDOWN (Top 5)")
    print(f"{'Symbol':12s} {'Volatility':>10} {'Volume':>8} {'Breakout':>9} {'WinRate':>8} {'R-Qual':>7} {'Trend':>7} {'Range':>7}")
    print("-" * 75)
    for r in picked[:5]:
        print(f"{r['symbol']:12s} {r['vol_score']:9.0f} {r['volume_score']:7.0f} {r['breakout_score']:8.0f} {r['wr_score']:7.0f} {r['r_score']:6.0f} {r['trend_score']:6.0f} {r['range_score']:6.0f}")

    # Compare with current FOCUS_SYMBOLS
    print(f"\n📋 CURRENT FOCUS_SYMBOLS STATUS")
    print("-" * 60)
    current_focus = config.FOCUS_SYMBOLS
    for sym in current_focus:
        match = next((r for r in results if r["symbol"] == sym), None)
        if match:
            rank = results.index(match) + 1
            status = "✅ TOP" if rank <= 12 else "⚠️  MID" if rank <= 25 else "❌ LOW"
            print(f"  {sym:12s} Rank #{rank:2d} | Score {match['composite_score']:5.1f} | RecentWR {match['recent_wr']:5.1f}% | {status}")
        else:
            print(f"  {sym:12s} — No data available")

    # Suggested changes
    print(f"\n💡 SUGGESTED FOCUS_SYMBOLS for TODAY")
    print("-" * 60)
    suggested = [r["symbol"] for r in picked[:10]]
    current_set = set(current_focus)
    suggested_set = set(suggested)
    added = suggested_set - current_set
    removed = current_set - suggested_set
    kept = current_set & suggested_set

    print(f"  KEEP:   {', '.join(sorted(kept)) if kept else 'None'}")
    print(f"  ADD:    {', '.join(sorted(added)) if added else 'None'}")
    print(f"  DROP:   {', '.join(sorted(removed)) if removed else 'None'}")
    print(f"\n  Suggested list:")
    print(f"  FOCUS_SYMBOLS = {json.dumps(suggested, indent=4)}")

    # Save results
    output = {
        "scan_date": str(datetime.now(IST).date()),
        "analysis_window_days": RECENT_DAYS,
        "all_ranked": results,
        "top_picks": [r for r in picked],
        "suggested_focus": suggested,
    }
    outpath = os.path.join(os.path.dirname(__file__), "results", "orb_readiness_scan.json")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✅ Full results saved to backtest/results/orb_readiness_scan.json")


if __name__ == "__main__":
    main()
