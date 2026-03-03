"""
Deep analysis of backtest results to diagnose strategy weaknesses
"""
import json
from datetime import datetime
from collections import Counter, defaultdict

with open("backtest/results/backtest_results.json") as f:
    r = json.load(f)

trades = r["trades"]

# === TRADE OUTCOME BREAKDOWN ===
sl_trades = [t for t in trades if any("STOPLOSS" in p[2] for p in t["exit_parts"]) and not any("STAGE" in p[2] for p in t["exit_parts"])]
partial_then_sl = [t for t in trades if any("STAGE" in p[2] for p in t["exit_parts"]) and any("STOPLOSS" in p[2] for p in t["exit_parts"])]
full_winners = [t for t in trades if not any("STOPLOSS" in p[2] for p in t["exit_parts"])]

print("=" * 70)
print("DEEP STRATEGY ANALYSIS")
print("=" * 70)

print("\n=== TRADE OUTCOME BREAKDOWN ===")
print(f"  Pure SL (no partial): {len(sl_trades)} trades, PnL: {sum(t['pnl'] for t in sl_trades):+,.1f}")
print(f"  Partial + SL:         {len(partial_then_sl)} trades, PnL: {sum(t['pnl'] for t in partial_then_sl):+,.1f}")
print(f"  Full winners (no SL): {len(full_winners)} trades, PnL: {sum(t['pnl'] for t in full_winners):+,.1f}")
print(f"  Pure SL %:            {len(sl_trades)/len(trades)*100:.1f}%")

# === ENTRY HOUR ANALYSIS ===
hours = Counter()
hour_pnl = defaultdict(float)
hour_wins = defaultdict(int)
for t in trades:
    h = t["entry_time"].split("T")[1][:2]
    hours[h] += 1
    hour_pnl[h] += t["pnl"]
    if t["pnl"] > 0:
        hour_wins[h] += 1

print("\n=== ENTRY HOUR ANALYSIS ===")
for h in sorted(hours):
    wr = hour_wins[h] / hours[h] * 100 if hours[h] else 0
    print(f"  {h}:00 -> {hours[h]:3d} trades | PnL: {hour_pnl[h]:+8,.1f} | Avg: {hour_pnl[h]/hours[h]:+6,.1f} | WR: {wr:.0f}%")

# === GAP + DIRECTION ANALYSIS ===
print("\n=== GAP + DIRECTION ANALYSIS ===")
combos = [
    ("LONG + gap up (aligned)", [t for t in trades if t["side"] == "BUY" and t["gap_pct"] > 0.3]),
    ("LONG + neutral gap",      [t for t in trades if t["side"] == "BUY" and -0.3 <= t["gap_pct"] <= 0.3]),
    ("LONG + gap down (contra)", [t for t in trades if t["side"] == "BUY" and t["gap_pct"] < -0.3]),
    ("SHORT + gap down (aligned)", [t for t in trades if t["side"] == "SELL" and t["gap_pct"] < -0.3]),
    ("SHORT + neutral gap",     [t for t in trades if t["side"] == "SELL" and -0.3 <= t["gap_pct"] <= 0.3]),
    ("SHORT + gap up (contra)", [t for t in trades if t["side"] == "SELL" and t["gap_pct"] > 0.3]),
]
for label, subset in combos:
    if subset:
        wr = sum(1 for t in subset if t["pnl"] > 0) / len(subset) * 100
        print(f"  {label:30s}: {len(subset):3d} trades | PnL: {sum(t['pnl'] for t in subset):+8,.1f} | WR: {wr:.0f}%")

# === OPEN BIAS ANALYSIS ===
print("\n=== OPEN BIAS ANALYSIS ===")
for bias in ["LONG", "SHORT", "NEUTRAL"]:
    sub = [t for t in trades if t["open_bias"] == bias]
    if sub:
        wr = sum(1 for t in sub if t["pnl"] > 0) / len(sub) * 100
        print(f"  OpenBias={bias:8s}: {len(sub):3d} trades | PnL: {sum(t['pnl'] for t in sub):+8,.1f} | WR: {wr:.0f}%")

# Aligned vs contradicting open bias
print("\n=== OPEN BIAS ALIGNMENT ===")
aligned = [t for t in trades if (t["side"] == "BUY" and t["open_bias"] == "LONG") or (t["side"] == "SELL" and t["open_bias"] == "SHORT")]
contra = [t for t in trades if (t["side"] == "BUY" and t["open_bias"] == "SHORT") or (t["side"] == "SELL" and t["open_bias"] == "LONG")]
neutral_bias = [t for t in trades if t["open_bias"] == "NEUTRAL"]

for label, subset in [("Aligned (bias matches)", aligned), ("Contradicting (bias opposes)", contra), ("Neutral open bias", neutral_bias)]:
    if subset:
        wr = sum(1 for t in subset if t["pnl"] > 0) / len(subset) * 100
        print(f"  {label:30s}: {len(subset):3d} trades | PnL: {sum(t['pnl'] for t in subset):+8,.1f} | WR: {wr:.0f}%")

# === HOLDING TIME ===
print("\n=== HOLDING TIME ===")
w_dur = []
l_dur = []
for t in trades:
    if t["entry_time"] and t.get("exit_time"):
        et = datetime.fromisoformat(t["entry_time"])
        xt = datetime.fromisoformat(t["exit_time"])
        d = (xt - et).seconds / 60
        if t["pnl"] > 0:
            w_dur.append(d)
        else:
            l_dur.append(d)
all_dur = w_dur + l_dur
if all_dur:
    print(f"  Avg:     {sum(all_dur)/len(all_dur):.0f} min")
    print(f"  Median:  {sorted(all_dur)[len(all_dur)//2]:.0f} min")
if w_dur:
    print(f"  Winners: {sum(w_dur)/len(w_dur):.0f} min avg")
if l_dur:
    print(f"  Losers:  {sum(l_dur)/len(l_dur):.0f} min avg")

# === MONTHLY BREAKDOWN ===
print("\n=== MONTHLY P&L ===")
monthly = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
for t in trades:
    m = t["entry_time"][:7]  # YYYY-MM
    monthly[m]["trades"] += 1
    monthly[m]["pnl"] += t["pnl"]
    if t["pnl"] > 0:
        monthly[m]["wins"] += 1

for m in sorted(monthly):
    d = monthly[m]
    wr = d["wins"] / d["trades"] * 100 if d["trades"] else 0
    print(f"  {m}: {d['trades']:3d} trades | PnL: {d['pnl']:+8,.1f} | WR: {wr:.0f}%")

# === CONSECUTIVE LOSS STREAKS ===
print("\n=== LOSS STREAK ANALYSIS ===")
streak = 0
streaks = []
for t in trades:
    if t["pnl"] < 0:
        streak += 1
    else:
        if streak > 0:
            streaks.append(streak)
        streak = 0
if streak > 0:
    streaks.append(streak)

from collections import Counter as C2
sc = C2(streaks)
for length in sorted(sc):
    if length >= 3:
        print(f"  {length}-trade losing streaks: {sc[length]} times")

# === RISK per trade ===
print("\n=== POSITION SIZE / RISK ANALYSIS ===")
pnl_abs = [abs(t["pnl"]) for t in trades]
print(f"  Avg absolute P&L:    {sum(pnl_abs)/len(pnl_abs):.1f}")
print(f"  Avg winner:          {sum(t['pnl'] for t in trades if t['pnl']>0)/max(1,sum(1 for t in trades if t['pnl']>0)):.1f}")
print(f"  Avg loser:           {sum(t['pnl'] for t in trades if t['pnl']<0)/max(1,sum(1 for t in trades if t['pnl']<0)):.1f}")
print(f"  Win/Loss ratio:      {abs(sum(t['pnl'] for t in trades if t['pnl']>0)/max(1,sum(1 for t in trades if t['pnl']>0))) / abs(sum(t['pnl'] for t in trades if t['pnl']<0)/max(1,sum(1 for t in trades if t['pnl']<0))):.2f}x")

# === FILTER EFFECTIVENESS ===
print("\n=== WHAT-IF: REMOVING WORST PERFORMERS ===")
# Without ITC and TATASTEEL
filtered = [t for t in trades if t["symbol"] not in ["ITC", "TATASTEEL"]]
f_pnl = sum(t["pnl"] for t in filtered)
f_wr = sum(1 for t in filtered if t["pnl"] > 0) / len(filtered) * 100
print(f"  Without ITC+TATASTEEL: {len(filtered)} trades | PnL: {f_pnl:+,.1f} | WR: {f_wr:.1f}%")

# Only best 5 symbols
best5 = ["INFY", "RELIANCE", "TCS", "HDFCBANK", "BAJFINANCE"]
filtered5 = [t for t in trades if t["symbol"] in best5]
f5_pnl = sum(t["pnl"] for t in filtered5)
f5_wr = sum(1 for t in filtered5 if t["pnl"] > 0) / len(filtered5) * 100
print(f"  Only top 5 symbols:    {len(filtered5)} trades | PnL: {f5_pnl:+,.1f} | WR: {f5_wr:.1f}%")

# Only 09:30 entries
early = [t for t in trades if t["entry_time"].split("T")[1][:2] == "09"]
e_pnl = sum(t["pnl"] for t in early)
e_wr = sum(1 for t in early if t["pnl"] > 0) / len(early) * 100 if early else 0
print(f"  Only 9:XX entries:     {len(early)} trades | PnL: {e_pnl:+,.1f} | WR: {e_wr:.1f}%")

# Only 10:XX entries
late = [t for t in trades if t["entry_time"].split("T")[1][:2] == "10"]
l_pnl = sum(t["pnl"] for t in late)
l_wr = sum(1 for t in late if t["pnl"] > 0) / len(late) * 100 if late else 0
print(f"  Only 10:XX entries:    {len(late)} trades | PnL: {l_pnl:+,.1f} | WR: {l_wr:.1f}%")

# Gap-aligned only
gap_aligned = [t for t in trades if 
    (t["side"] == "BUY" and t["gap_pct"] > 0.3) or 
    (t["side"] == "SELL" and t["gap_pct"] < -0.3)]
if gap_aligned:
    ga_pnl = sum(t["pnl"] for t in gap_aligned)
    ga_wr = sum(1 for t in gap_aligned if t["pnl"] > 0) / len(gap_aligned) * 100
    print(f"  Gap-aligned only:      {len(gap_aligned)} trades | PnL: {ga_pnl:+,.1f} | WR: {ga_wr:.1f}%")

print("\n" + "=" * 70)
