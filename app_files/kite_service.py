"""
Kite API Service Wrapper - Handles all Kite Connect API calls
"""

import logging
from datetime import datetime, timedelta
import pytz
from kiteconnect import KiteConnect
from app_files import config

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')


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
    
    def get_profile(self):
        """Get user profile information"""
        try:
            profile = self.kite.profile()
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return profile
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
            self._handle_api_failure()
            return None
    
    def get_quote(self, exchange, symbol):
        """
        Get current quote for a symbol
        
        Args:
            exchange: NSE, BSE, MCX, NCDEX
            symbol: Symbol name (e.g., "TATASTEEL")
        
        Returns:
            Quote dict with last_price, high, low, etc.
        """
        try:
            instrument_key = f"{exchange}:{symbol}"
            quote = self.kite.quote([instrument_key])
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            
            # The response is directly indexed by instrument_key
            if instrument_key in quote:
                return quote[instrument_key]
            return None
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            self._handle_api_failure()
            return None
    
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
            logger.error(f"Error fetching historical data: {e}")
            self._handle_api_failure()
            return []
    
    def get_instruments(self, exchange):
        """
        Get all instruments for an exchange
        
        Args:
            exchange: "NSE", "BSE", "MCX", "NCDEX"
        
        Returns:
            List of instrument dicts
        """
        try:
            instruments = self.kite.instruments(exchange)
            self.last_api_call = datetime.now(IST)
            self.failed_api_attempts = 0
            return instruments
        except Exception as e:
            logger.error(f"Error fetching instruments: {e}")
            self._handle_api_failure()
            return []
    
    def find_instrument_token(self, exchange, symbol):
        """
        Find instrument token for a given symbol
        
        Args:
            exchange: "NSE", "BSE", "MCX", "NCDEX"
            symbol: Symbol name (e.g., "TATASTEEL")
        
        Returns:
            Instrument token (int) or None
        """
        try:
            instruments = self.get_instruments(exchange)
            for instrument in instruments:
                if instrument.get('tradingsymbol') == symbol:
                    return instrument.get('instrument_token')
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
                           takeprifit_value, stoploss_value, parent_order_id=None):
        """
        Place a bracket order (order with predefined profit and stoploss)
        
        Args:
            symbol: Symbol name
            transaction_type: "BUY" or "SELL"
            quantity: Number of shares
            price: Entry price
            takeprifit_value: Profit target price
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
                takeprifit_value=takeprifit_value,
                stoploss_value=stoploss_value
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
