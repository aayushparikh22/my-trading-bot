"""
Parameter Sensitivity & Optimization Analysis
================================================
Tests multiple parameter combinations to find the highest-profit configuration.
Runs fast by reusing loaded data and varying only config params.
"""
import os, sys, json, copy, itertools
from datetime import datetime, timedelta
from collections import defaultdict
import pytz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app_files import config

# Import backtester components
from run_backtest import (
    load_candle_data, group_candles_by_date, calculate_vwap, calculate_atr,
    get_volume_ratio, get_time_of_day_volume_factor, check_range_quality,
    Trade, _get_nifty_price_at, DATA_DIR
)

IST = pytz.timezone('Asia/Kolkata')


def run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, params):
    """Fast backtester with configurable params dict overlay"""
    capital = 20000 * 5 * 0.80  # 80K
    all_trades = []
    daily_pnl = {}

    all_days = set()
    for sym_days in data_5min.values():
        all_days.update(sym_days.keys())
    all_days = sorted(all_days)

    for day in all_days:
        symbols_setup = {}
        for sym in symbols:
            candles_5 = data_5min.get(sym, {}).get(day, [])
            candles_15 = data_15min.get(sym, {}).get(day, [])
            if not candles_5 or not candles_15:
                continue

            opening_15 = None
            for c in candles_15:
                if c["date"].hour == 9 and c["date"].minute == 15:
                    opening_15 = c
                    break
            if not opening_15:
                opening_15 = candles_15[0] if candles_15 else None
            if not opening_15:
                continue

            o, h, l, cl = opening_15["open"], opening_15["high"], opening_15["low"], opening_15["close"]
            if h <= 0 or l <= 0 or h <= l:
                continue

            vwap_candles = [c for c in candles_5 if c["date"].hour == 9 and c["date"].minute < 35]
            if not vwap_candles:
                vwap_candles = candles_5[:3]
            vwap = calculate_vwap(vwap_candles) if vwap_candles else None
            if not vwap:
                continue

            if not check_range_quality(h, l, vwap):
                continue

            pre_candles = [c for c in candles_5 if c["date"].hour == 9 and c["date"].minute <= 30]
            if len(pre_candles) < 3:
                pre_candles = candles_5[:5]
            atr_val = calculate_atr(pre_candles, min(10, len(pre_candles) - 1)) if len(pre_candles) > 2 else None

            if atr_val:
                buffer = params.get("atr_multiplier", 0.2) * atr_val
            else:
                buffer = 0.10

            long_trigger = h + buffer
            short_trigger = l - buffer

            # Gap
            gap_pct = 0.0
            prev_day_candles = data_15min.get(sym, {})
            prev_days = sorted([d for d in prev_day_candles.keys() if d < day])
            if prev_days:
                prev_last = prev_day_candles[prev_days[-1]]
                if prev_last:
                    prev_close = prev_last[-1]["close"]
                    if prev_close > 0:
                        gap_pct = ((o - prev_close) / prev_close) * 100

            # Open bias
            candle_range = h - l
            open_position = (o - l) / candle_range if candle_range > 0 else 0.5
            strong_zone = 0.25
            if open_position >= (1 - strong_zone):
                open_bias = "SHORT"
            elif open_position <= strong_zone:
                open_bias = "LONG"
            else:
                open_bias = "NEUTRAL"

            symbols_setup[sym] = {
                "open": o, "high": h, "low": l, "close": cl,
                "vwap": vwap, "long_trigger": long_trigger, "short_trigger": short_trigger,
                "buffer": buffer, "gap_pct": gap_pct, "open_bias": open_bias,
                "candles_5": candles_5, "atr_initial": atr_val,
            }

        if not symbols_setup:
            daily_pnl[day] = 0
            continue

        # NIFTY
        nifty_candles = nifty_by_date.get(day, [])
        nifty_vwap = None
        if nifty_candles:
            nifty_open_candles = [c for c in nifty_candles if c["date"].hour == 9]
            if nifty_open_candles:
                nifty_vwap = calculate_vwap(nifty_open_candles)

        active_trades = []
        entry_found_symbols = set()
        no_entry_after = params.get("no_entry_after", 1015)
        soft_cutoff = params.get("soft_cutoff_start", 1000)
        max_positions = params.get("max_positions", 5)
        sl_factor = params.get("sl_factor", 0.75)
        skip_open_bias_short = params.get("skip_open_bias_short", True)
        short_needs_nifty = params.get("short_needs_nifty", True)
        allow_shorts = params.get("allow_shorts", True)
        use_gap_filter = params.get("use_gap_filter", True)
        vol_multiplier = params.get("vol_multiplier", 1.2)
        reentry = params.get("allow_reentry", False)
        min_risk_pct = params.get("min_risk_pct", 0.0)  # min risk as % of price
        
        # Partial booking params
        first_target_r = params.get("first_target_r", 0.75)
        second_target_r = params.get("second_target_r", 1.0)
        final_target_r = params.get("final_target_r", 2.0)
        first_pct = params.get("first_pct", 0.25)
        second_pct = params.get("second_pct", 0.20)
        eod_pct = params.get("eod_pct", 0.55)

        for sym, setup in symbols_setup.items():
            candles_5 = setup["candles_5"]
            for idx, candle in enumerate(candles_5):
                ctime = candle["date"]
                hhmm = ctime.hour * 100 + ctime.minute
                if hhmm < 930:
                    continue
                if hhmm > no_entry_after:
                    break

                if not reentry and sym in entry_found_symbols:
                    continue

                open_count = sum(1 for t in active_trades if t.status == "OPEN")
                if open_count >= max_positions:
                    continue

                c5 = candle["close"]
                vwap = setup["vwap"]
                long_trigger = setup["long_trigger"]
                short_trigger = setup["short_trigger"]

                vwap_candles_so_far = candles_5[:idx + 1]
                rolling_vwap = calculate_vwap(vwap_candles_so_far)
                if rolling_vwap:
                    vwap = rolling_vwap

                if skip_open_bias_short and setup["open_bias"] == "SHORT":
                    continue

                entry_side = None

                # LONG
                if c5 > long_trigger and c5 > vwap:
                    if hhmm >= soft_cutoff:
                        vol_ratio = get_volume_ratio(candles_5, idx, 10)
                        if vol_ratio < 2.0:
                            continue
                    vol_ratio = get_volume_ratio(candles_5, idx, 10)
                    time_factor = get_time_of_day_volume_factor(ctime)
                    if vol_ratio < vol_multiplier * time_factor:
                        continue
                    if use_gap_filter and setup["gap_pct"] < -0.3:
                        continue
                    entry_side = "BUY"

                # SHORT
                elif allow_shorts and c5 < short_trigger and c5 < vwap:
                    if short_needs_nifty and nifty_vwap and nifty_candles:
                        nifty_price = _get_nifty_price_at(nifty_candles, ctime)
                        if nifty_price and nifty_vwap and nifty_price >= nifty_vwap:
                            continue
                    if hhmm >= soft_cutoff:
                        vol_ratio = get_volume_ratio(candles_5, idx, 10)
                        if vol_ratio < 2.0:
                            continue
                    vol_ratio = get_volume_ratio(candles_5, idx, 10)
                    time_factor = get_time_of_day_volume_factor(ctime)
                    if vol_ratio < vol_multiplier * time_factor:
                        continue
                    if use_gap_filter and setup["gap_pct"] > 0.3:
                        continue
                    entry_side = "SELL"

                if entry_side:
                    if entry_side == "BUY":
                        raw_sl = min(vwap, candle["low"])
                        risk = c5 - raw_sl
                        sl_price = c5 - (risk * sl_factor)
                    else:
                        raw_sl = max(vwap, candle["high"])
                        risk = raw_sl - c5
                        sl_price = c5 + (risk * sl_factor)

                    if risk <= 0:
                        continue
                    
                    # Min risk filter
                    if min_risk_pct > 0 and (risk / c5 * 100) < min_risk_pct:
                        continue

                    per_position = capital / max_positions
                    quantity = max(1, int(per_position * 0.85 / c5))

                    # Override Trade targets with params
                    trade = Trade(
                        symbol=sym, side=entry_side, entry_price=c5,
                        sl_price=sl_price, quantity=quantity,
                        entry_time=ctime, gap_pct=setup["gap_pct"],
                        open_bias=setup["open_bias"]
                    )
                    # Override targets
                    r = abs(c5 - sl_price)
                    if entry_side == "BUY":
                        trade.target1 = c5 + r * first_target_r
                        trade.target2 = c5 + r * second_target_r
                        trade.target3 = c5 + r * final_target_r
                    else:
                        trade.target1 = c5 - r * first_target_r
                        trade.target2 = c5 - r * second_target_r
                        trade.target3 = c5 - r * final_target_r

                    active_trades.append(trade)
                    entry_found_symbols.add(sym)

        # Process exits
        for trade in active_trades:
            if trade.status == "CLOSED":
                continue
            sym = trade.symbol
            candles_5 = symbols_setup[sym]["candles_5"]
            for idx, candle in enumerate(candles_5):
                if candle["date"] <= trade.entry_time:
                    continue
                start_idx = max(0, idx - 11)
                atr_val = calculate_atr(candles_5[start_idx:idx + 1], 10)
                closed = trade.process_candle(candle, atr_val)
                if closed:
                    break
            if trade.status == "OPEN":
                last_candle = candles_5[-1] if candles_5 else None
                if last_candle:
                    trade._close_remaining(last_candle["close"], "FORCE_EOD", last_candle["date"])

        day_pnl = sum(t.total_pnl for t in active_trades)
        daily_pnl[day] = day_pnl
        all_trades.extend(active_trades)

    total_pnl = sum(t.total_pnl for t in all_trades)
    total_trades = len(all_trades)
    winners = sum(1 for t in all_trades if t.total_pnl > 0)
    wr = winners / total_trades * 100 if total_trades else 0

    # Max drawdown
    cum = 0
    peak = 0
    max_dd = 0
    for d in sorted(daily_pnl):
        cum += daily_pnl[d]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    return {
        "pnl": round(total_pnl, 1),
        "pnl_pct": round(total_pnl / capital * 100, 2),
        "trades": total_trades,
        "win_rate": round(wr, 1),
        "max_dd": round(max_dd, 1),
        "pf": round(sum(t.total_pnl for t in all_trades if t.total_pnl > 0) / max(1, abs(sum(t.total_pnl for t in all_trades if t.total_pnl < 0))), 2) if any(t.total_pnl < 0 for t in all_trades) else 999,
        "avg_win": round(sum(t.total_pnl for t in all_trades if t.total_pnl > 0) / max(1, winners), 1),
        "avg_loss": round(sum(t.total_pnl for t in all_trades if t.total_pnl < 0) / max(1, total_trades - winners), 1),
    }


def load_all_data(symbols_list):
    """Load and cache all data"""
    data_5min = {}
    data_15min = {}
    for sym in symbols_list:
        d5 = load_candle_data(sym, "5min")
        d15 = load_candle_data(sym, "15min")
        if d5:
            data_5min[sym] = group_candles_by_date(d5)
        if d15:
            data_15min[sym] = group_candles_by_date(d15)
    nifty_5min = load_candle_data("NIFTY50", "5min")
    nifty_by_date = group_candles_by_date(nifty_5min) if nifty_5min else {}
    return data_5min, data_15min, nifty_by_date


def main():
    print("=" * 90)
    print("PARAMETER SENSITIVITY & OPTIMIZATION ANALYSIS")
    print("=" * 90)

    # Load data once
    files = [f for f in os.listdir(DATA_DIR) if f.endswith("_5min.json")]
    all_symbols = [f.replace("_5min.json", "") for f in files if "NIFTY50" not in f]
    print(f"All available symbols: {all_symbols}")

    data_5min, data_15min, nifty_by_date = load_all_data(all_symbols)
    print(f"Data loaded. Running optimization sweeps...\n")

    # ========= TEST 1: Stock Selection =========
    print("=" * 90)
    print("TEST 1: SYMBOL SELECTION (which stocks to include?)")
    print("=" * 90)
    
    base_params = {
        "sl_factor": 0.75, "no_entry_after": 1015, "soft_cutoff_start": 1000,
        "max_positions": 5, "skip_open_bias_short": True, "short_needs_nifty": True,
        "allow_shorts": True, "use_gap_filter": True, "vol_multiplier": 1.2,
        "first_target_r": 0.75, "second_target_r": 1.0, "final_target_r": 2.0,
        "atr_multiplier": 0.2,
    }

    symbol_sets = {
        "All 10": all_symbols,
        "Top 8 (no ITC/TATA)": [s for s in all_symbols if s not in ["ITC", "TATASTEEL"]],
        "Top 5 (INFY,REL,TCS,HDFC,BAJ)": ["INFY", "RELIANCE", "TCS", "HDFCBANK", "BAJFINANCE"],
        "Top 3 (INFY,REL,HDFC)": ["INFY", "RELIANCE", "HDFCBANK"],
        "Top 6 (+SBIN,AXIS)": ["INFY", "RELIANCE", "TCS", "HDFCBANK", "BAJFINANCE", "SBIN"],
    }

    for name, syms in symbol_sets.items():
        r = run_single_backtest(syms, data_5min, data_15min, nifty_by_date, base_params)
        print(f"  {name:35s} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 2: SL Distance Factor =========
    print(f"\n{'='*90}")
    print("TEST 2: STOP LOSS DISTANCE FACTOR")
    print("=" * 90)
    symbols = [s for s in all_symbols if s not in ["ITC", "TATASTEEL"]]
    for sl in [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0]:
        p = {**base_params, "sl_factor": sl}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  SL={sl:.2f} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | AvgW:{r['avg_win']:+.0f} AvgL:{r['avg_loss']:+.0f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 3: Entry Window =========
    print(f"\n{'='*90}")
    print("TEST 3: ENTRY WINDOW (no_entry_after)")
    print("=" * 90)
    for window in [945, 1000, 1015, 1030, 1045, 1100]:
        p = {**base_params, "no_entry_after": window, "soft_cutoff_start": max(945, window - 15)}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  Window to {window} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 4: Max Positions =========
    print(f"\n{'='*90}")
    print("TEST 4: MAX POSITIONS")
    print("=" * 90)
    for mp in [1, 2, 3, 5, 8, 10]:
        p = {**base_params, "max_positions": mp}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  MaxPos={mp:2d} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 5: Target Ratios =========
    print(f"\n{'='*90}")
    print("TEST 5: PROFIT TARGET (final target R)")
    print("=" * 90)
    for target in [1.5, 2.0, 2.5, 3.0, 4.0]:
        p = {**base_params, "final_target_r": target}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  Target={target:.1f}R | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 6: Volume Multiplier =========
    print(f"\n{'='*90}")
    print("TEST 6: VOLUME MULTIPLIER")
    print("=" * 90)
    for vm in [0.8, 1.0, 1.2, 1.5, 2.0]:
        p = {**base_params, "vol_multiplier": vm}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  VolMult={vm:.1f} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 7: ATR Buffer Multiplier =========
    print(f"\n{'='*90}")
    print("TEST 7: ATR BUFFER MULTIPLIER (breakout confirmation)")
    print("=" * 90)
    for am in [0.1, 0.15, 0.2, 0.3, 0.5, 0.7]:
        p = {**base_params, "atr_multiplier": am}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  ATRmult={am:.2f} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 8: Short Side Toggle =========
    print(f"\n{'='*90}")
    print("TEST 8: SHORT SIDE OPTIONS")
    print("=" * 90)
    for label, shorts, nifty_req in [("No shorts", False, False), ("Shorts + NIFTY req", True, True), ("Shorts free", True, False)]:
        p = {**base_params, "allow_shorts": shorts, "short_needs_nifty": nifty_req}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  {label:20s} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 9: First Target R =========
    print(f"\n{'='*90}")
    print("TEST 9: FIRST PARTIAL TARGET")
    print("=" * 90)
    for ft in [0.5, 0.75, 1.0, 1.25]:
        p = {**base_params, "first_target_r": ft}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  1st Target={ft:.2f}R | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 10: Gap Filter Toggle =========
    print(f"\n{'='*90}")
    print("TEST 10: GAP FILTER")
    print("=" * 90)
    for gf in [True, False]:
        p = {**base_params, "use_gap_filter": gf}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  GapFilter={str(gf):5s} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= TEST 11: OpenBias SHORT skip toggle =========
    print(f"\n{'='*90}")
    print("TEST 11: SKIP OPEN BIAS SHORT")
    print("=" * 90)
    for sb in [True, False]:
        p = {**base_params, "skip_open_bias_short": sb}
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        print(f"  SkipBiasShort={str(sb):5s} | PnL: {r['pnl']:+8,.1f} ({r['pnl_pct']:+5.2f}%) | {r['trades']:3d} trades | WR:{r['win_rate']:.0f}% | PF:{r['pf']:.2f} | DD:{r['max_dd']:.0f}")

    # ========= MEGA TEST: Top Combinations =========
    print(f"\n{'='*90}")
    print("MEGA TEST: BEST COMBINATIONS")
    print("=" * 90)

    best_results = []
    combos = list(itertools.product(
        [0.7, 0.75, 0.8, 0.9, 1.0],     # sl_factor
        [1000, 1015, 1030],                # no_entry_after
        [2.0, 2.5, 3.0],                  # final_target_r
        [0.75, 1.0],                       # first_target_r
        [0.15, 0.2, 0.3],                 # atr_multiplier
        [3, 5, 8],                         # max_positions
    ))
    
    print(f"Testing {len(combos)} parameter combinations...")
    
    for i, (sl, window, target, ft, am, mp) in enumerate(combos):
        p = {
            **base_params,
            "sl_factor": sl,
            "no_entry_after": window,
            "soft_cutoff_start": max(945, window - 15),
            "final_target_r": target,
            "first_target_r": ft,
            "atr_multiplier": am,
            "max_positions": mp,
        }
        r = run_single_backtest(symbols, data_5min, data_15min, nifty_by_date, p)
        best_results.append((r["pnl"], r, p))
        
        if (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(combos)} tested")

    # Sort by PnL
    best_results.sort(key=lambda x: x[0], reverse=True)

    print(f"\nTOP 15 PARAMETER COMBINATIONS:")
    print(f"{'Rank':>4} | {'PnL':>10} | {'PnL%':>7} | {'Trades':>6} | {'WR':>5} | {'PF':>5} | {'DD':>7} | SL   | Window | Target | 1stT | ATR  | MaxP")
    print("-" * 110)
    for rank, (pnl, r, p) in enumerate(best_results[:15], 1):
        print(f"  {rank:2d} | {r['pnl']:+8,.1f} | {r['pnl_pct']:+5.2f}% | {r['trades']:5d} | {r['win_rate']:4.0f}% | {r['pf']:4.2f} | {r['max_dd']:6.0f} | {p['sl_factor']:.2f} | {p['no_entry_after']:>6} | {p['final_target_r']:5.1f}R | {p['first_target_r']:.2f} | {p['atr_multiplier']:.2f} | {p['max_positions']:2d}")

    # Also show worst 5
    print(f"\nBOTTOM 5 (worst):")
    for rank, (pnl, r, p) in enumerate(best_results[-5:], 1):
        print(f"  {rank:2d} | {r['pnl']:+8,.1f} | {r['pnl_pct']:+5.2f}% | {r['trades']:5d} | {r['win_rate']:4.0f}% | {r['pf']:4.2f} | SL={p['sl_factor']:.2f} W={p['no_entry_after']} T={p['final_target_r']:.1f}R")

    print(f"\n{'=' * 90}")
    print("DONE. Use the top parameters in config.py for best performance.")
    print(f"{'=' * 90}")


if __name__ == "__main__":
    main()
