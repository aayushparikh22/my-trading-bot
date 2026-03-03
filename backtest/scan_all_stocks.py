"""
Scan all NIFTY 50 stocks individually with ORB strategy
to find best performers for FOCUS_SYMBOLS selection.
"""
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app_files import config
# Disable NIFTY filter so each stock is judged on its own merit
config.USE_NIFTY_FILTER = False
config.FOCUS_SYMBOLS = []
config.EXCLUDED_SYMBOLS = []
config.MAX_POSITIONS = 1

from backtest.run_backtest import Backtester
import logging
logging.disable(logging.INFO)

data_dir = os.path.join(os.path.dirname(__file__), "data")
all_stocks = sorted(set(
    f.replace('_5min.json', '')
    for f in os.listdir(data_dir)
    if f.endswith('_5min.json') and not f.startswith('NIFTY')
))

# Sectors mapping
sectors = {
    'HDFCBANK': 'Banking', 'ICICIBANK': 'Banking', 'SBIN': 'Banking', 'KOTAKBANK': 'Banking',
    'AXISBANK': 'Banking', 'INDUSINDBK': 'Banking',
    'BAJFINANCE': 'Finance', 'BAJAJFINSV': 'Finance', 'HDFCLIFE': 'Insurance',
    'SBILIFE': 'Insurance', 'SHRIRAMFIN': 'Finance',
    'TCS': 'IT', 'INFY': 'IT', 'HCLTECH': 'IT', 'WIPRO': 'IT', 'TECHM': 'IT', 'LTIM': 'IT',
    'RELIANCE': 'Energy', 'ONGC': 'Energy', 'BPCL': 'Energy', 'NTPC': 'Power',
    'POWERGRID': 'Power', 'COALINDIA': 'Mining', 'ADANIPORTS': 'Infra', 'ADANIENT': 'Conglomerate',
    'TATAMOTORS': 'Auto', 'MARUTI': 'Auto', 'M&M': 'Auto', 'BAJAJ-AUTO': 'Auto',
    'EICHERMOT': 'Auto', 'HEROMOTOCO': 'Auto',
    'TATASTEEL': 'Metals', 'JSWSTEEL': 'Metals', 'HINDALCO': 'Metals',
    'HINDUNILVR': 'FMCG', 'ITC': 'FMCG', 'NESTLEIND': 'FMCG', 'BRITANNIA': 'FMCG',
    'TATACONSUM': 'FMCG', 'TITAN': 'Consumer', 'TRENT': 'Consumer',
    'SUNPHARMA': 'Pharma', 'DRREDDY': 'Pharma', 'CIPLA': 'Pharma', 'APOLLOHOSP': 'Healthcare',
    'LT': 'Infra', 'ULTRACEMCO': 'Cement', 'GRASIM': 'Cement',
    'BHARTIARTL': 'Telecom', 'ASIANPAINT': 'Paints',
    'LTIM': 'IT',
}

results = []
for sym in all_stocks:
    try:
        bt = Backtester([sym])
        trades, daily_pnl = bt.run()
        if not trades:
            results.append({
                'symbol': sym, 'sector': sectors.get(sym, '?'),
                'trades': 0, 'pnl': 0, 'win_rate': 0, 'avg_pnl': 0, 'profit_factor': 0,
            })
            continue
        total_pnl = sum(t.total_pnl for t in trades)
        winners = sum(1 for t in trades if t.total_pnl > 0)
        wr = winners / len(trades) * 100 if trades else 0
        avg_pnl = total_pnl / len(trades) if trades else 0

        gross_profit = sum(t.total_pnl for t in trades if t.total_pnl > 0)
        gross_loss = sum(t.total_pnl for t in trades if t.total_pnl < 0)
        pf = abs(gross_profit / gross_loss) if gross_loss != 0 else 999

        results.append({
            'symbol': sym,
            'sector': sectors.get(sym, '?'),
            'trades': len(trades),
            'pnl': round(total_pnl, 1),
            'win_rate': round(wr, 1),
            'avg_pnl': round(avg_pnl, 1),
            'profit_factor': round(pf, 2),
        })
    except Exception as e:
        print(f"ERROR {sym}: {e}")

# Sort by PnL descending
results.sort(key=lambda x: x['pnl'], reverse=True)

print()
print("=" * 80)
print("ORB STRATEGY — ALL NIFTY 50 STOCKS RANKED (2025-2026 Data)")
print("=" * 80)
header = f"{'#':<4} {'Symbol':<14} {'Sector':<12} {'Trades':>6} {'P&L':>10} {'WR%':>6} {'AvgPnL':>8} {'PF':>6}"
print(header)
print("-" * 80)
for i, r in enumerate(results, 1):
    marker = " *" if r['pnl'] > 0 else ""
    print(f"{i:<4} {r['symbol']:<14} {r['sector']:<12} {r['trades']:>6} {r['pnl']:>+10.1f} {r['win_rate']:>6.1f} {r['avg_pnl']:>+8.1f} {r['profit_factor']:>6.2f}{marker}")

profitable = [r for r in results if r['pnl'] > 0]
losing = [r for r in results if r['pnl'] <= 0]

print()
print(f"Profitable stocks: {len(profitable)} / {len(results)}")
print(f"Losing stocks:     {len(losing)} / {len(results)}")

# Sector distribution of top performers 
print()
print("=" * 80)
print("TOP PICKS BY SECTOR (profitable stocks only)")
print("=" * 80)
from collections import defaultdict
sector_best = defaultdict(list)
for r in profitable:
    sector_best[r['sector']].append(r)

for sector in sorted(sector_best.keys()):
    stocks = sector_best[sector]
    stocks.sort(key=lambda x: x['pnl'], reverse=True)
    names = ", ".join(f"{s['symbol']}(+{s['pnl']:.0f})" for s in stocks)
    print(f"  {sector:<14}: {names}")

# Save results
with open(os.path.join(os.path.dirname(__file__), 'results', 'stock_scan_results.json'), 'w') as f:
    json.dump(results, f, indent=2)
print()
print("Results saved to backtest/results/stock_scan_results.json")
