"""
Kite API Service Wrapper - Handles all Kite Connect API calls
"""

import logging
import time
from datetime import datetime, timedelta
import pytz
from kiteconnect import KiteConnect
from app_files import config

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

# Rate limiting constants
API_RATE_LIMIT_DELAY = 1.0  # 1 second between API calls (safe for backtesting)
RATE_LIMIT_BACKOFF = 10.0   # Wait 10 seconds on rate limit error
QUOTE_CACHE_TTL = 5.0       # Cache quotes for 5 seconds


class KiteService:
    """Wrapper around KiteConnect SDK for easier API interaction"""
    
    def __init__(self, api_key, access_token):
        """
        Initialize Kite API service
        
        Args:
            api_key: Kite API key from app
            access_token: Access token obtained after OAuth login
        """
        self.api_key = api_key
        self.access_token = access_token
        self.kite = KiteConnect(api_key=api_key, debug=config.KITE_DEBUG)
        self.kite.set_access_token(access_token)
        self.session_start_time = None
        self.last_api_call = None
        self.failed_api_attempts = 0
        self.max_failed_attempts = 3
        
        # Rate limiting
        self._last_request_time = 0
        self._rate_limit_until = 0
        
        # Quote cache
        self._quote_cache = {}
        self._quote_cache_time = {}
        
        # Instrument cache to avoid repeated lookups
        self._instruments_cache = {}  # exchange -> list of instruments
        self._instrument_tokens = {}  # "exchange:symbol" -> token
        self._instruments_cache_time = 0
        self.INSTRUMENTS_CACHE_TTL = 3600  # Cache for 1 hour
    
    def _rate_limit(self):
        """Apply rate limiting between API calls"""
        now = time.time()
        
        # Check if we're in rate limit backoff
        if now < self._rate_limit_until:
            sleep_time = self._rate_limit_until - now
            logger.warning(f"Rate limit backoff: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        
        # Apply minimum delay between requests
        elapsed = now - self._last_request_time
        if elapsed < API_RATE_LIMIT_DELAY:
            time.sleep(API_RATE_LIMIT_DELAY - elapsed)
        
        self._last_request_time = time.time()
    
    def _handle_rate_limit(self):
        """Handle rate limit error with backoff"""
        self._rate_limit_until = time.time() + RATE_LIMIT_BACKOFF
        logger.warning(f"Rate limit hit - backing off for {RATE_LIMIT_BACKOFF}s")
    
    def get_profile(self):
        """Get user profile information"""
        try:
            self._rate_limit()
            profile = self.kite.profile()
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return profile
        except Exception as e:
            if "Too many requests" in str(e):
                self._handle_rate_limit()
            logger.error(f"Error fetching profile: {e}")
            self._handle_api_failure()
            return None
    
    def get_quote(self, exchange, symbol):
        """
        Get current quote for a symbol (with caching)
        
        Args:
            exchange: NSE, BSE, MCX, NCDEX
            symbol: Symbol name (e.g., "TATASTEEL")
        
        Returns:
            Quote dict with last_price, high, low, etc.
        """
        try:
            instrument_key = f"{exchange}:{symbol}"
            
            # Check cache first
            now = time.time()
            if instrument_key in self._quote_cache:
                cache_age = now - self._quote_cache_time.get(instrument_key, 0)
                if cache_age < QUOTE_CACHE_TTL:
                    return self._quote_cache[instrument_key]
            
            self._rate_limit()
            quote = self.kite.quote([instrument_key])
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            
            # Cache the result
            if instrument_key in quote:
                self._quote_cache[instrument_key] = quote[instrument_key]
                self._quote_cache_time[instrument_key] = now
                return quote[instrument_key]
            return None
        except Exception as e:
            if "Too many requests" in str(e):
                self._handle_rate_limit()
            logger.error(f"Error fetching quote for {symbol}: {e}")
            self._handle_api_failure()
            return None
    
    def get_quotes_batch(self, instruments):
        """
        Get quotes for multiple instruments in a SINGLE API call (max 500)
        
        Args:
            instruments: List of "EXCHANGE:SYMBOL" strings, e.g., ["NSE:TATASTEEL", "NSE:HDFCBANK"]
        
        Returns:
            Dict of instrument_key -> quote data
        """
        try:
            if not instruments:
                return {}
            
            # Kite allows max 500 instruments per quote call
            instruments = instruments[:500]
            
            self._rate_limit()
            quotes = self.kite.quote(instruments)
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            
            # Cache all results
            now = time.time()
            for key, quote in quotes.items():
                self._quote_cache[key] = quote
                self._quote_cache_time[key] = now
            
            return quotes
        except Exception as e:
            if "Too many requests" in str(e):
                self._handle_rate_limit()
            logger.error(f"Error fetching batch quotes: {e}")
            self._handle_api_failure()
            return {}
    
    def get_historical_data(self, instrument_token, from_date, to_date, interval):
        """
        Get historical candle data
        
        Args:
            instrument_token: Token for the instrument
            from_date: Start date (datetime or string 'YYYY-MM-DD')
            to_date: End date (datetime or string 'YYYY-MM-DD')
            interval: "minute", "5minute", "15minute", "30minute", "60minute", "day"
        
        Returns:
            List of candle data dicts
        """
        try:
            self._rate_limit()
            data = self.kite.historical_data(
                instrument_token,
                from_date,
                to_date,
                interval
            )
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return data
        except Exception as e:
            if "Too many requests" in str(e):
                self._handle_rate_limit()
            logger.error(f"Error fetching historical data: {e}")
            self._handle_api_failure()
            return []
    
    def get_instruments(self, exchange):
        """
        Get all instruments for an exchange (with caching)
        
        Args:
            exchange: "NSE", "BSE", "MCX", "NCDEX"
        
        Returns:
            List of instrument dicts
        """
        try:
            # Check cache first
            now = time.time()
            if exchange in self._instruments_cache and \
               (now - self._instruments_cache_time) < self.INSTRUMENTS_CACHE_TTL:
                return self._instruments_cache[exchange]
            
            # Fetch from API with rate limiting
            self._rate_limit()
            instruments = self.kite.instruments(exchange)
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            
            # Cache the result
            self._instruments_cache[exchange] = instruments
            self._instruments_cache_time = now
            
            return instruments
        except Exception as e:
            if "Too many requests" in str(e):
                self._handle_rate_limit()
            logger.error(f"Error fetching instruments: {e}")
            self._handle_api_failure()
            return []
    
    def find_instrument_token(self, exchange, symbol):
        """
        Find instrument token for a given symbol (with caching)
        
        Args:
            exchange: "NSE", "BSE", "MCX", "NCDEX"
            symbol: Symbol name (e.g., "TATASTEEL")
        
        Returns:
            Instrument token (int) or None
        """
        # Check token cache first
        cache_key = f"{exchange}:{symbol}"
        if cache_key in self._instrument_tokens:
            return self._instrument_tokens[cache_key]
        
        try:
            instruments = self.get_instruments(exchange)
            for instrument in instruments:
                if instrument.get('tradingsymbol') == symbol:
                    token = instrument.get('instrument_token')
                    # Cache the token
                    self._instrument_tokens[cache_key] = token
                    return token
            
            logger.warning(f"Instrument {symbol} not found on {exchange}")
            return None
        except Exception as e:
            logger.error(f"Error finding instrument token: {e}")
            return None
    
    def place_order(self, symbol, transaction_type, quantity, price=None,
                   product=None, order_type=None, validity=None, trigger_price=None):
        """
        Place an order
        
        Args:
            symbol: Symbol name (e.g., "TATASTEEL")
            transaction_type: "BUY" or "SELL"
            quantity: Number of shares
            price: Price (required for limit orders)
            product: "MIS" (intraday), "CNC" (delivery), "NRML" (normal)
            order_type: "MARKET", "LIMIT"
            validity: "DAY", "IOC", "GTC"
            trigger_price: Trigger price for SL/SL-M orders
        
        Returns:
            Order ID or None
        """
        try:
            product = product or config.TRADE_TYPE
            order_type = order_type or "MARKET"
            validity = validity or "DAY"
            
            order_id = self.kite.place_order(
                variety="regular",
                exchange=config.EXCHANGE,
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                product=product,
                order_type=order_type,
                validity=validity
            )
            
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            logger.info(f"Order placed: {order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            self._handle_api_failure()
            return None
    
    def place_bracket_order(self, symbol, transaction_type, quantity, price,
                           takeprofit_value, stoploss_value, parent_order_id=None):
        """
        Place a bracket order (order with predefined profit and stoploss)
        
        Args:
            symbol: Symbol name
            transaction_type: "BUY" or "SELL"
            quantity: Number of shares
            price: Entry price
            takeprofit_value: Profit target price
            stoploss_value: Stoploss price
            parent_order_id: Parent order ID (for modifications)
        
        Returns:
            Order ID or None
        """
        try:
            order_id = self.kite.place_order(
                variety="bo",
                exchange=config.EXCHANGE,
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                price=price,
                product=config.TRADE_TYPE,
                order_type="LIMIT",
                validity="DAY",
                squareoff=takeprofit_value,
                stoploss=stoploss_value
            )
            
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            logger.info(f"Bracket order placed: {order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Error placing bracket order: {e}")
            self._handle_api_failure()
            return None
    
    def cancel_order(self, order_id, variety="regular"):
        """
        Cancel an order
        
        Args:
            order_id: Order ID to cancel
            variety: "regular", "bo", "co"
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.kite.cancel_order(
                variety=variety,
                order_id=order_id
            )
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            self._handle_api_failure()
            return False
    
    def modify_order(self, order_id, quantity=None, price=None, 
                    order_type=None, variety="regular"):
        """
        Modify an open order
        
        Args:
            order_id: Order ID to modify
            quantity: New quantity
            price: New price
            order_type: New order type
            variety: "regular", "bo", "co"
        
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            response = self.kite.modify_order(
                variety=variety,
                order_id=order_id,
                quantity=quantity,
                price=price,
                order_type=order_type
            )
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            logger.info(f"Order modified: {order_id}")
            return response
        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            self._handle_api_failure()
            return None
    
    def get_orders(self):
        """Get all orders for the day"""
        try:
            orders = self.kite.orders()
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return orders
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            self._handle_api_failure()
            return []
    
    def get_order_history(self, order_id):
        """Get history of an order"""
        try:
            history = self.kite.order_history(order_id)
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return history
        except Exception as e:
            logger.error(f"Error fetching order history: {e}")
            self._handle_api_failure()
            return []
    
    def get_trades(self):
        """Get all trades for the day"""
        try:
            trades = self.kite.trades()
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return trades
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            self._handle_api_failure()
            return []
    
    def get_positions(self):
        """Get current positions"""
        try:
            positions = self.kite.positions()
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            self._handle_api_failure()
            return {"net": [], "day": []}
    
    def get_holdings(self):
        """Get all holdings (delivery positions)"""
        try:
            holdings = self.kite.holdings()
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return holdings
        except Exception as e:
            logger.error(f"Error fetching holdings: {e}")
            self._handle_api_failure()
            return []
    
    def get_account_balance(self):
        """Get account balance and margin details"""
        try:
            margins = self.kite.margins()
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return margins
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}")
            self._handle_api_failure()
            return None
    
    def health_check(self):
        """
        Perform health check on API connectivity
        
        Returns:
            True if all checks pass, False otherwise
        """
        try:
            logger.info("🏥 KITE API HEALTH CHECK")
            
            # Test 1: Get profile
            logger.info("   Test 1: Fetching user profile...")
            profile = self.get_profile()
            if not profile:
                logger.error("   ✗ FAILED: Cannot fetch profile")
                return False
            logger.info(f"   ✓ Profile fetched: {profile.get('user_name', 'Unknown')}")
            
            # Test 2: Get quote for configured symbol
            logger.info(f"   Test 2: Fetching quote for {config.SYMBOL_NSE}...")
            quote = self.get_quote(config.EXCHANGE, config.SYMBOL_NSE)
            if not quote:
                logger.error("   ✗ FAILED: Cannot fetch quotes")
                return False
            ltp = quote.get('last_price', 0)
            logger.info(f"   ✓ Quote fetched: {config.SYMBOL_NSE} = ₹{ltp}")
            
            # Test 3: Get positions
            logger.info(f"   Test 3: Fetching positions...")
            positions = self.get_positions()
            if positions is None:
                logger.error("   ✗ FAILED: Cannot fetch positions")
                return False
            logger.info(f"   ✓ Positions fetched: {len(positions.get('day', []))} open positions")
            
            logger.info("")
            logger.info("✅ ALL API CHECKS PASSED - Kite API is working perfectly!")
            logger.info(f"   • User: {profile.get('user_name', 'Unknown')}")
            logger.info(f"   • Current Price: ₹{ltp}")
            logger.info(f"   • Open Positions: {len(positions.get('day', []))}")
            logger.info("")
            return True
            
        except Exception as e:
            logger.error(f"❌ API HEALTH CHECK FAILED: {e}")
            return False
    
    def _handle_api_failure(self):
        """Track API failures and handle reconnection logic"""
        self.failed_api_attempts += 1
        if self.failed_api_attempts >= self.max_failed_attempts:
            logger.warning("Maximum API failures reached. May need to re-authenticate.")
    
    def is_market_hours(self):
        """Check if current time is within market hours"""
        now = datetime.now(IST)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Only check on weekdays (0-4 are Mon-Fri)
        if now.weekday() > 4:
            return False
        
        return market_open <= now <= market_close
    
    def get_time_until_market_open(self):
        """Get minutes until market opens"""
        now = datetime.now(IST)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        
        if now > market_open:
            # Market already opened or closed today
            # Check for next day
            market_open += timedelta(days=1)
        
        time_diff = market_open - now
        return time_diff.total_seconds() / 60  # Return in minutes
    
    def calculate_vwap(self, candles):
        """
        Calculate VWAP (Volume Weighted Average Price) from candle data
        
        Args:
            candles: List of candle dicts with 'close', 'volume' keys
        
        Returns:
            VWAP value
        """
        if not candles:
            return 0
        
        typical_price_volume = sum(
            ((c['close'] + c['high'] + c['low']) / 3) * c['volume']
            for c in candles
        )
        total_volume = sum(c['volume'] for c in candles)
        
        if total_volume == 0:
            return candles[-1]['close']
        
        return typical_price_volume / total_volume
