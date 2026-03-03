"""
Historical Data Downloader for Backtesting
===========================================
Downloads 5-minute and 15-minute intraday candle data from Kite Connect
for the top 10 NIFTY 50 stocks, covering the last 3 months.

Usage:
    python download_data.py

Prerequisites:
    - Valid Kite session (run kite_login.py first, or have KITE_AUTO_LOGIN=true)
    - pip install kiteconnect pytz python-dotenv

Output:
    backtest/data/
        HDFCBANK_5min.json
        HDFCBANK_15min.json
        RELIANCE_5min.json
        ...
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
import pytz

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

# ===== CONFIGURATION =====

# Top 10 NIFTY 50 stocks by liquidity/volume
STOCKS = [
    {"symbol": "HDFCBANK",   "exchange": "NSE"},
    {"symbol": "RELIANCE",   "exchange": "NSE"},
    {"symbol": "ICICIBANK",  "exchange": "NSE"},
    {"symbol": "SBIN",       "exchange": "NSE"},
    {"symbol": "TATASTEEL",  "exchange": "NSE"},
    {"symbol": "INFY",       "exchange": "NSE"},
    {"symbol": "TCS",        "exchange": "NSE"},
    {"symbol": "AXISBANK",   "exchange": "NSE"},
    {"symbol": "BAJFINANCE", "exchange": "NSE"},
    {"symbol": "ITC",        "exchange": "NSE"},
]

# How far back to download (Kite allows ~2 years for 5-min data)
MONTHS_BACK = 3

# Intervals to download
INTERVALS = ["5minute", "15minute"]

# Kite API limits: max 2000 candles per request for intraday
# 5-min: ~75 candles/day × 30 days ≈ 2250 → need to chunk by ~25 days
# 15-min: ~25 candles/day × 60 days ≈ 1500 → can do bigger chunks
MAX_CANDLES_PER_REQUEST = 2000
CANDLES_PER_DAY = {"5minute": 75, "15minute": 25, "minute": 375}

# Rate limiting
DELAY_BETWEEN_REQUESTS = 0.5  # seconds

# Output directory
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def get_kite_client():
    """Get authenticated Kite client via session manager"""
    try:
        from app_files.kite_session import get_kite_session
        kite, token = get_kite_session()
        profile = kite.profile()
        logger.info(f"✅ Connected as: {profile.get('user_name', 'N/A')} ({profile.get('user_id', '')})")
        return kite
    except Exception as e:
        logger.error(f"❌ Could not get Kite session: {e}")
        logger.error("   Make sure you have valid credentials in .env")
        logger.error("   Try running: python app_files/kite_login.py")
        sys.exit(1)


def find_instrument_token(kite, exchange, symbol):
    """Look up the instrument token for a symbol"""
    try:
        instruments = kite.instruments(exchange)
        for inst in instruments:
            if inst['tradingsymbol'] == symbol:
                return inst['instrument_token']
        logger.warning(f"⚠️  Token not found for {exchange}:{symbol}")
        return None
    except Exception as e:
        logger.error(f"Error fetching instruments: {e}")
        return None


def download_historical(kite, token, symbol, interval, from_date, to_date):
    """
    Download historical data in chunks to respect API limits.
    
    Kite's historical_data API returns max 2000 candles per request.
    For 5-min data: ~75 candles/day → chunk by ~25 trading days
    For 15-min data: ~25 candles/day → chunk by ~60 trading days
    """
    cpd = CANDLES_PER_DAY.get(interval, 75)
    max_days_per_chunk = max(1, MAX_CANDLES_PER_REQUEST // cpd)
    
    all_candles = []
    chunk_start = from_date
    chunk_num = 0
    
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=max_days_per_chunk), to_date)
        chunk_num += 1
        
        try:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            data = kite.historical_data(
                token,
                chunk_start,
                chunk_end,
                interval
            )
            
            if data:
                all_candles.extend(data)
                logger.info(f"   Chunk {chunk_num}: {chunk_start.strftime('%Y-%m-%d')} → {chunk_end.strftime('%Y-%m-%d')} | {len(data)} candles")
            else:
                logger.warning(f"   Chunk {chunk_num}: No data for {chunk_start.strftime('%Y-%m-%d')} → {chunk_end.strftime('%Y-%m-%d')}")
                
        except Exception as e:
            err_str = str(e)
            if "Too many requests" in err_str:
                logger.warning(f"   Rate limited — waiting 15 seconds...")
                time.sleep(15)
                # Retry this chunk
                continue
            else:
                logger.error(f"   Error downloading chunk {chunk_num}: {e}")
        
        chunk_start = chunk_end + timedelta(days=1)
    
    return all_candles


def serialize_candles(candles):
    """Convert candle data to JSON-serializable format"""
    serialized = []
    for c in candles:
        serialized.append({
            "date": c["date"].isoformat() if hasattr(c["date"], 'isoformat') else str(c["date"]),
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
            "volume": int(c["volume"]),
        })
    return serialized


def main():
    print("=" * 70)
    print("📊 HISTORICAL DATA DOWNLOADER FOR BACKTESTING")
    print("=" * 70)
    print()
    
    # Create output directory
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Connect to Kite
    kite = get_kite_client()
    
    # Calculate date range
    # Override: set specific date range via environment or use MONTHS_BACK
    # To download full year 2025: set BACKTEST_FROM and BACKTEST_TO env vars
    env_from = os.environ.get("BACKTEST_FROM")
    env_to = os.environ.get("BACKTEST_TO")
    if env_from and env_to:
        from_date = IST.localize(datetime.strptime(env_from, "%Y-%m-%d").replace(hour=9, minute=15))
        to_date = IST.localize(datetime.strptime(env_to, "%Y-%m-%d").replace(hour=15, minute=30))
    else:
        to_date = datetime.now(IST).replace(hour=15, minute=30, second=0, microsecond=0)
        from_date = to_date - timedelta(days=MONTHS_BACK * 30)
    
    print(f"📅 Date range: {from_date.strftime('%Y-%m-%d')} → {to_date.strftime('%Y-%m-%d')}")
    print(f"📈 Stocks: {', '.join(s['symbol'] for s in STOCKS)}")
    print(f"🕐 Intervals: {', '.join(INTERVALS)}")
    print(f"📁 Output: {DATA_DIR}")
    print()
    
    # Fetch instrument tokens (one API call for all NSE instruments)
    logger.info("Fetching NSE instrument list...")
    try:
        time.sleep(DELAY_BETWEEN_REQUESTS)
        instruments = kite.instruments("NSE")
        token_map = {}
        for inst in instruments:
            key = inst['tradingsymbol']
            if key in [s['symbol'] for s in STOCKS]:
                token_map[key] = inst['instrument_token']
        logger.info(f"✅ Found tokens for {len(token_map)}/{len(STOCKS)} stocks")
    except Exception as e:
        logger.error(f"❌ Failed to fetch instruments: {e}")
        sys.exit(1)
    
    # Also get NIFTY 50 index token for index data
    try:
        nse_indices = kite.instruments("NSE")
        for inst in nse_indices:
            if inst['tradingsymbol'] == 'NIFTY 50' or inst['name'] == 'NIFTY 50':
                token_map['NIFTY50'] = inst['instrument_token']
                logger.info(f"✅ Found NIFTY 50 index token: {inst['instrument_token']}")
                break
    except:
        logger.warning("⚠️  Could not find NIFTY 50 index token (backtest will skip NIFTY filter)")
    
    # Download data
    total_files = 0
    total_candles = 0
    
    # Add NIFTY 50 to download list if we found it
    download_list = list(STOCKS)
    if 'NIFTY50' in token_map:
        download_list.append({"symbol": "NIFTY50", "exchange": "NSE"})
    
    for stock in download_list:
        symbol = stock['symbol']
        token = token_map.get(symbol)
        
        if not token:
            logger.warning(f"⚠️  Skipping {symbol} — no instrument token found")
            continue
        
        print(f"\n{'='*50}")
        print(f"📥 Downloading {symbol}...")
        print(f"{'='*50}")
        
        for interval in INTERVALS:
            logger.info(f"  ⏳ {symbol} @ {interval}...")
            
            candles = download_historical(
                kite, token, symbol, interval,
                from_date, to_date
            )
            
            if not candles:
                logger.warning(f"  ⚠️  No data returned for {symbol} @ {interval}")
                continue
            
            # Serialize and save
            serialized = serialize_candles(candles)
            
            filename = f"{symbol}_{interval.replace('minute', 'min')}.json"
            filepath = os.path.join(DATA_DIR, filename)
            
            with open(filepath, 'w') as f:
                json.dump({
                    "symbol": symbol,
                    "exchange": stock['exchange'],
                    "interval": interval,
                    "from_date": from_date.strftime('%Y-%m-%d'),
                    "to_date": to_date.strftime('%Y-%m-%d'),
                    "total_candles": len(serialized),
                    "downloaded_at": datetime.now(IST).isoformat(),
                    "candles": serialized
                }, f, indent=2)
            
            total_files += 1
            total_candles += len(serialized)
            
            logger.info(f"  ✅ {symbol} @ {interval}: {len(serialized)} candles → {filename}")
    
    # Summary
    print("\n" + "=" * 70)
    print("✅ DOWNLOAD COMPLETE!")
    print("=" * 70)
    print(f"   📁 Files saved: {total_files}")
    print(f"   📊 Total candles: {total_candles:,}")
    print(f"   📂 Location: {os.path.abspath(DATA_DIR)}")
    print()
    print("Next step: Run the backtester:")
    print("   python backtest/run_backtest.py")
    print()
    
    # Save a manifest file
    manifest = {
        "downloaded_at": datetime.now(IST).isoformat(),
        "date_range": {
            "from": from_date.strftime('%Y-%m-%d'),
            "to": to_date.strftime('%Y-%m-%d'),
            "months": MONTHS_BACK
        },
        "stocks": [s['symbol'] for s in STOCKS],
        "intervals": INTERVALS,
        "total_files": total_files,
        "total_candles": total_candles,
        "files": [f for f in os.listdir(DATA_DIR) if f.endswith('.json') and f != 'manifest.json']
    }
    
    with open(os.path.join(DATA_DIR, "manifest.json"), 'w') as f:
        json.dump(manifest, f, indent=2)
    
    logger.info(f"📋 Manifest saved to {os.path.join(DATA_DIR, 'manifest.json')}")


if __name__ == "__main__":
    main()
