"""
🤖 OPTIMIZED OPENING RANGE BREAKOUT BOT - KITE API VERSION
VWAP + BUFFER STRATEGY

This version uses Kite Connect API from Zerodha instead of Shoonya API
All trading logic remains the same, only API calls are different
"""

import time
import datetime
import pytz
import logging
from app_files import config
from app_files.kite_service import KiteService

# Setup logging FIRST before using logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

# Update logging configuration to include console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

IST = pytz.timezone('Asia/Kolkata')

def get_ist_time():
    """
    Get current time in IST reliably by converting UTC to IST (+5:30 hours)
    This works even if system timezone is not set to IST
    """
    utc_now = datetime.datetime.utcnow()
    ist_time = utc_now + datetime.timedelta(hours=5, minutes=30)
    return ist_time


class KiteApp:
    """Trading bot using Kite Connect API"""
    
    def __init__(self, api_key, access_token, user_id=None):
        """
        Initialize bot with Kite API credentials
        
        Args:
            api_key: Kite API key
            access_token: Access token from authentication
            user_id: User ID for database logging
        """
        self.user_id = user_id
        self.kite = KiteService(api_key, access_token)
        self.api_key = api_key
        self.access_token = access_token
        
        # Additional logging helper
        def log_to_db(msg, log_type='BOT'):
            """Log message to database if user_id is available"""
            logger.info(msg)  # Always log to console/file
            if self.user_id:
                try:
                    from models import BotLog
                    BotLog.create_log(self.user_id, log_type, msg, 'INFO')
                except Exception as e:
                    # Log warning but don't fail trading due to DB issues
                    logger.warning(f"⚠️  DB logging failed: {str(e)}")
        
        self.log_to_db = log_to_db
        
        # Fetch actual account balance instead of using hardcoded value
        self.account_balance = None
        self.starting_balance = None  # Will be set at start of trading session
        self.leverage = config.LEVERAGE
        
        # Bot control flag
        self.should_stop = False
        self.trades = []
        self.trades_today = []  # Track today's trades for multi-trade logic
        
        # Current position tracking
        self.entry_price = None
        self.entry_quantity = None
        self.entry_side = None
        self.sl_price = None
        self.sl_order_id = None  # Track stoploss order ID for updates/cancellation
        self.trade_type = config.TRADE_TYPE
        
        # NEW: Algorithm Upgrade Variables
        # Phase 1: Critical Fixes
        self.atr_values = {}  # Cache ATR per symbol
        self.volume_history = {}  # Cache volume history per symbol
        
        # Phase 2: Strategy Logic  
        self.num_trades_today = 0  # Max 2 trades per day
        self.trade1_result = None  # 'WIN' or 'LOSS'
        self.nifty_bias = None  # 'LONG' or 'SHORT' based on NIFTY VWAP
        self.entry_window_state = "PRIMARY"  # PRIMARY (9:30-10:15) or SOFT (10:15-10:45)
        
        # Phase 3: Risk Management
        self.partial_booked_75pct = False  # Track if 75% booked at 2R
        self.sl_moved_to_breakeven = False  # Track if SL moved to entry at 1R
        self.remaining_quantity = None  # Quantity after partial exit
        self.last_5min_lows = []  # Track 5-min candle lows for trailing
        self.traded_symbol = None  # Current traded symbol for partial booking
        self.effective_capital = 0  # Effective capital with leverage
        self.trade_db_id = None  # Database ID of current trade for real-time sync
        self.sl_moved_to_entry_after_2r = False  # NEW: Track if SL moved to entry after 2R booking

        # Caches and state for new filters
        self.retest_states = {}
        self.htf_cache = {}
        self.atr_cache = {}
        self.atr_cache_time = {}
        self.trades_by_symbol = {}
        self.nifty_strength_pct = 0.0
        
        # Daily tracking
        self.daily_loss_pct = 0.0
        self.daily_pnl = 0.0
        
    def log_section(self, title):
        """Log a formatted section header"""
        logger.info("=" * 60)
        logger.info(f"  {title}")
        logger.info("=" * 60)
    
    def save_trade_to_db(self, entry_side, symbol, quantity, entry_price, sl_price, target_price):
        """
        Save a newly opened trade to the database immediately for real-time sync
        Returns: database trade ID on success, None on failure
        """
        if not self.user_id:
            return None
            
        try:
            from datetime import datetime
            from backend.models import Trade, db
            
            trade = Trade(
                user_id=self.user_id,
                trade_date=get_ist_time().date(),
                entry_time=get_ist_time(),
                side='B' if entry_side == 'BUY' else 'S',
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                stoploss_price=sl_price,
                target_price=target_price,
                status='OPEN'
            )
            
            db.session.add(trade)
            db.session.commit()
            
            logger.info(f"✓ Trade saved to database (ID: {trade.id})")
            return trade.id
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to save trade to DB: {str(e)}")
            return None
    
    def update_trade_in_db(self, trade_db_id, **updates):
        """
        Update an existing trade in the database with partial booking, SL changes, etc.
        Updates can include: quantity, exit_price, stoploss_price, pnl, exit_time, status, etc.
        """
        if not trade_db_id or not self.user_id:
            return False
            
        try:
            from backend.models import Trade, db
            
            trade = Trade.query.filter_by(id=trade_db_id, user_id=self.user_id).first()
            if not trade:
                logger.warning(f"⚠️  Trade ID {trade_db_id} not found in database")
                return False
            
            # Update fields that are provided
            for key, value in updates.items():
                if hasattr(trade, key):
                    setattr(trade, key, value)
            
            # If exit_price is provided, calculate P&L
            if 'exit_price' in updates and 'exit_qty' not in updates:
                exit_qty = trade.quantity
            else:
                exit_qty = updates.get('exit_qty', trade.quantity)
            
            if 'exit_price' in updates and updates['exit_price'] is not None:
                exit_price = updates['exit_price']
                if trade.side == 'B':
                    pnl = (exit_price - trade.entry_price) * exit_qty
                else:
                    pnl = (trade.entry_price - exit_price) * exit_qty
                
                trade.pnl = pnl
                if trade.entry_price > 0:
                    trade.pnl_percent = (pnl / (trade.entry_price * exit_qty)) * 100
            
            trade.updated_at = get_ist_time()
            db.session.commit()
            
            logger.info(f"✓ Trade {trade_db_id} updated in database")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to update trade in DB: {str(e)}")
            return False
    
    def get_account_balance(self):
        """Fetch actual account balance from Kite"""
        try:
            self.log_to_db("Calling Kite API for account balance...")
            # Try to get balance from Kite, but if credentials are missing, use fallback
            if not self.api_key or not self.access_token:
                self.log_to_db("⚠️  No Kite credentials provided - using configured starting capital")
                return config.STARTING_CAPITAL
                
            margins = self.kite.get_account_balance()
            if margins and 'equity' in margins:
                # Get available cash (live balance)
                available_cash = margins['equity'].get('available', {}).get('live_balance', 0)
                logger.info(f"💰 Account Balance Fetched: ₹{available_cash:,.2f}")
                self.log_to_db(f"Account balance fetched: ₹{available_cash:,.2f}")
                return available_cash
            else:
                self.log_to_db("⚠️  Could not fetch account balance from API - using configured starting capital")
                logger.warning("⚠️  Could not fetch account balance - using configured starting capital")
                return config.STARTING_CAPITAL
        except Exception as e:
            self.log_to_db(f"⚠️  ERROR in get_account_balance: {str(e)} - using configured starting capital")
            logger.warning(f"⚠️  Error fetching account balance: {e} - using configured starting capital")
            return config.STARTING_CAPITAL
    
    def calculate_dynamic_quantity(self, entry_price):
        """Calculate quantity dynamically based on actual account balance and leverage"""
        try:
            # Fetch actual account balance
            if self.account_balance is None:
                self.account_balance = self.get_account_balance()
            
            if self.account_balance <= 0:
                logger.error("✗ No available balance in account")
                return 0
            
            # Use configured utilization of available balance for trading
            utilization_percentage = getattr(config, "MARGIN_UTILIZATION", 0.85)
            leverage_factor = self.leverage if config.USE_LEVERAGE_IN_SIZING else 1
            capital_for_trade = self.account_balance * utilization_percentage * leverage_factor
            
            # Calculate quantity based on final order price
            quantity = int(capital_for_trade / entry_price)
            
            if quantity < 1:
                logger.error(f"✗ Calculated quantity is 0. Entry price too high: ₹{entry_price}")
                return 0
            
            logger.info(f"📊 DYNAMIC QUANTITY CALCULATION:")
            logger.info(f"   Account Balance: ₹{self.account_balance:,.2f}")
            logger.info(f"   Utilization: {utilization_percentage*100:.0f}%")
            logger.info(f"   Leverage Sizing: {leverage_factor}x")
            logger.info(f"   Capital for Trade: ₹{capital_for_trade:,.2f}")
            logger.info(f"   Order Price (for sizing): ₹{entry_price:.2f}")
            logger.info(f"   ✓ Calculated Quantity: {quantity} shares")
            logger.info(f"   Total Cost: ₹{quantity * entry_price:,.2f}")
            logger.info("")
            
            return quantity
            
        except Exception as e:
            logger.error(f"✗ Error calculating quantity: {e}")
            return 0
    
    def health_check(self):
        """Verify Kite APIs are working correctly"""
        return self.kite.health_check()
    
    def calculate_trade_details(self, symbol, entry_price, quantity, side, sl_price):
        """Calculate detailed trade metrics"""
        total_amount = entry_price * quantity
        risk_per_share = abs(entry_price - sl_price)
        total_risk = risk_per_share * quantity
        reward_potential = total_risk * 2
        risk_percentage = (risk_per_share / entry_price) * 100
        
        # Calculate margin required (typical brokers use ~20% margin for MIS)
        margin_required = (total_amount / self.leverage) if self.leverage > 0 else total_amount
        
        return {
            'total_amount': total_amount,
            'margin_required': margin_required,
            'risk_per_share': risk_per_share,
            'total_risk': total_risk,
            'reward_potential': reward_potential,
            'risk_percentage': risk_percentage
        }
    
    def display_trade_details(self, side, price, quantity, sl_price, symbol):
        """Display comprehensive trade execution details"""
        details = self.calculate_trade_details(symbol, price, quantity, side, sl_price)
        
        # Use account_balance or starting_balance, fallback to 0 if not initialized
        balance = self.starting_balance or self.account_balance or 0
        
        logger.info(f"")
        logger.info(f"📊 TRADE EXECUTION DETAILS:")
        logger.info(f"   Entry Price: ₹{price:.2f}")
        logger.info(f"   Quantity: {quantity} shares")
        logger.info(f"   Total Amount: ₹{details['total_amount']:,.2f}")
        logger.info(f"   ")
        logger.info(f"💼 MARGIN & LEVERAGE:")
        logger.info(f"   Leverage Used: {self.leverage}x (MIS product type)")
        logger.info(f"   Margin Required: ₹{details['margin_required']:,.2f}")
        logger.info(f"   Available Balance: ₹{balance:,.2f}")
        if balance > 0:
            logger.info(f"   Margin Utilization: {(details['margin_required']/balance*100):.1f}%")
        logger.info(f"   ")
        logger.info(f"⚠️  RISK MANAGEMENT:")
        logger.info(f"   Stoploss Price: ₹{sl_price:.2f}")
        logger.info(f"   Risk Per Share: ₹{details['risk_per_share']:.2f} ({details['risk_percentage']:.2f}%)")
        logger.info(f"   Total Risk Amount: ₹{details['total_risk']:.2f}")
        logger.info(f"   Potential Reward (2:1): ₹{details['reward_potential']:.2f}")
        logger.info(f"   Risk to Reward Ratio: 1 : 2")
    
    def log_trade(self, action, side, price, quantity, pnl=None):
        """Log trade execution"""
        action_emoji = "🟢 BOUGHT" if side == 'BUY' else "🔴 SOLD"
        pnl_str = f" | P&L: ₹{pnl:.2f}" if pnl is not None else ""
        logger.info(f"{action_emoji} {quantity} shares at ₹{price:.2f}{pnl_str}")

    def log_skip(self, message):
        """Log skip reasons to DB so UI can show them"""
        self.log_to_db(f"SKIP: {message}")
    
    def display_portfolio_status(self):
        """Display current portfolio and balance - DEPRECATED: not used in main flow"""
        logger.info("")
        logger.info("💰 AVAILABLE FUNDS (BEFORE TRADING):")
        logger.info(f"   Actual Balance: ₹{self.starting_balance:,.2f}")
        logger.info(f"   Leverage: {self.leverage}x")
        logger.info(f"   Effective Capital Available: ₹{self.effective_capital:,.2f}")
        logger.info(f"   Trade Type: {config.TRADE_TYPE_DISPLAY} (MIS) - Intraday - Must square off by market close")
        logger.info("")
    
    def generate_final_report(self):
        """Generate final trading report"""
        self.log_section("📊 FINAL TRADING REPORT")
        
        logger.info("Strategy: VWAP + Buffer Filter (Optimized ORB)")
        logger.info(f"   15-min candle range with VWAP filter")
        logger.info(f"   5-min candle confirmation with ±₹{config.BUFFER_AMOUNT} buffer")
        logger.info(f"   Entry Window: 9:30 AM - 9:45 AM IST")
        logger.info("")
        
        logger.info("Trade Summary:")
        logger.info(f"   Total Trades: {len(self.trades)}")
        logger.info(f"   Margin Utilization: {config.MARGIN_UTILIZATION*100:.0f}%")
        logger.info(f"   Position Sizing: Dynamic (70% margin × {self.leverage}x leverage ÷ entry price)")
        
        if len(self.trades) > 0:
            total_pnl = sum([t.get('pnl', 0) for t in self.trades])
            winning_trades = len([t for t in self.trades if t.get('pnl', 0) > 0])
            losing_trades = len([t for t in self.trades if t.get('pnl', 0) < 0])
            
            win_rate = (winning_trades / len(self.trades) * 100) if len(self.trades) > 0 else 0
            
            logger.info(f"   Winning Trades: {winning_trades}")
            logger.info(f"   Losing Trades: {losing_trades}")
            logger.info(f"   Win Rate: {win_rate:.1f}%")
            logger.info("")
            
            logger.info("💰 FUND POSITION:")
            logger.info(f"   Starting Balance: ₹{self.starting_balance:,.2f}")
            logger.info(f"   Total P&L: ₹{total_pnl:.2f}")
            logger.info(f"   Ending Balance: ₹{self.starting_balance + total_pnl:,.2f}")
            logger.info(f"   Return on Capital: {(total_pnl / self.starting_balance * 100):.2f}%")
        else:
            logger.info("   No trades executed (no valid breakout signals detected)")
        
        logger.info("")
    
    def get_first_candle(self, instrument_token):
        """Fetch the 09:15-09:30 IST opening candle"""
        try:
            now = get_ist_time()
            start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
            end_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
            
            candles = self.kite.get_historical_data(
                instrument_token,
                start_time,
                end_time,
                interval=f"{config.TIMEFRAME_RANGE}minute"
            )
            
            if not candles or len(candles) == 0:
                logger.error("✗ No candle data received")
                return None, None, None, None
            
            candle = candles[0]
            o = float(candle.get('open', 0))
            h = float(candle.get('high', 0))
            l = float(candle.get('low', 0))
            c = float(candle.get('close', 0))
            
            if h <= 0 or l <= 0 or h < l:
                logger.error(f"✗ Invalid candle data: H={h}, L={l}")
                return None, None, None, None
            
            logger.info(f"✓ Candle fetched - Open: ₹{o}, High: ₹{h}, Low: ₹{l}, Close: ₹{c}")
            return o, h, l, c
            
        except Exception as e:
            logger.error(f"✗ Error fetching candle: {e}")
            return None, None, None, None
    
    def find_instrument_token(self, symbol):
        """Find instrument token for symbol"""
        try:
            token = self.kite.find_instrument_token(config.EXCHANGE, symbol)
            if token:
                logger.info(f"✓ Found instrument token: {token} for {symbol}")
            else:
                logger.error(f"✗ Could not find instrument token for {symbol}")
            return token
        except Exception as e:
            logger.error(f"✗ Error finding instrument token: {e}")
            return None
    
    def calculate_vwap(self, instrument_token):
        """Calculate VWAP from candle data"""
        try:
            now = get_ist_time()
            start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
            
            candles = self.kite.get_historical_data(
                instrument_token,
                start_time,
                now,
                interval="5minute"
            )
            
            if not candles:
                logger.error("✗ No candle data for VWAP calculation")
                return None
            
            vwap = self.kite.calculate_vwap(candles)
            if vwap:
                logger.info(f"✓ VWAP Calculated: ₹{vwap:.2f}")
            return vwap
            
        except Exception as e:
            logger.error(f"✗ Error calculating VWAP: {e}")
            return None
    
    def get_latest_5min_candle(self, instrument_token):
        """Fetch the latest 5-minute candle with timestamp"""
        try:
            now = get_ist_time()
            start_time = now - datetime.timedelta(minutes=15)
            
            candles = self.kite.get_historical_data(
                instrument_token,
                start_time,
                now,
                interval="5minute"
            )
            
            if not candles or len(candles) == 0:
                return None
            
            latest = candles[-1]
            o = float(latest.get('open', 0))
            h = float(latest.get('high', 0))
            l = float(latest.get('low', 0))
            c = float(latest.get('close', 0))
            v = float(latest.get('volume', 0))
            candle_time = latest.get('date')
            
            return o, h, l, c, v, candle_time
            
        except Exception as e:
            logger.error(f"✗ Error fetching 5-min candle: {e}")
            return None
    
    def wait_until_market_time(self, target_hour, target_minute):
        """Wait until market reaches target time"""
        last_log_time = get_ist_time()
        
        while True:
            now = get_ist_time()
            
            # Check if current time is >= target time
            if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
                logger.info(f"✓ Reached {target_hour:02d}:{target_minute:02d} IST")
                self.log_to_db(f"✓ Market time reached: {now.strftime('%H:%M:%S IST')}")
                break
            
            if now.weekday() >= 5:
                logger.error("✗ Market closed - Weekend")
                self.log_to_db("✗ Market closed - Weekend")
                return False
            
            if (now - last_log_time).seconds >= 60:
                logger.info(f"⏳ Waiting for {target_hour:02d}:{target_minute:02d} IST... Current: {now.strftime('%H:%M:%S')}")
                last_log_time = now
            
            time.sleep(5)
        
        return True
    
    def wait_until_next_day_market(self):
        """Wait until next trading day at 9:15 AM"""
        logger.info("🛌 Bot is in standby mode - waiting for next trading day")
        logger.info("⏰ Will resume at 9:15 AM IST on next trading day")
        last_log_time = get_ist_time()
        
        while not self.should_stop:
            now = get_ist_time()
            
            # Check if it's a weekday
            if now.weekday() >= 5:
                if (now - last_log_time).seconds >= 3600:  # Log every hour on weekends
                    logger.info(f"📅 Weekend - waiting for Monday. Current: {now.strftime('%A, %I:%M %p IST')}")
                    last_log_time = now
                time.sleep(1)  # Check every second for responsive stop
                continue
            
            # Check if we've reached 9:15 AM
            if now.hour == 9 and now.minute >= 15:
                logger.info(f"✓ Market day! Starting trading session")
                break
            elif now.hour > 9:
                # It's past 9:15 AM but same day - wait until next day
                if (now - last_log_time).seconds >= 1800:  # Log every 30 min
                    tomorrow = (now + datetime.timedelta(days=1)).strftime('%A, %B %d')
                    logger.info(f"⏳ Waiting for tomorrow ({tomorrow}) at 9:15 AM IST")
                    last_log_time = now
                time.sleep(1)  # Check every second for responsive stop
            else:
                # Same day, before 9:15 AM
                if (now - last_log_time).seconds >= 300:  # Log every 5 min
                    wait_time = datetime.datetime.combine(now.date(), datetime.time(9, 15)) - now
                    logger.info(f"⏳ Waiting {wait_time.seconds//60} minutes until 9:15 AM IST")
                    last_log_time = now
                time.sleep(1)  # Check every second for responsive stop
        
        # Check if stopped during wait
        if self.should_stop:
            logger.info("🛑 Stop signal received during wait")
            return False
        
        return True
    
    def get_live_price(self, instrument_token, symbol):
        """Fetch current live price"""
        try:
            quote = self.kite.get_quote(config.EXCHANGE, symbol)
            
            if not quote:
                logger.error("✗ Failed to get quote")
                return None
            
            ltp = quote.get('last_price', 0)
            if ltp <= 0:
                logger.error(f"✗ Invalid price: {ltp}")
                return None
            
            return ltp
            
        except Exception as e:
            logger.error(f"✗ Error getting live price: {e}")
            return None
    
    def place_buy_order(self, symbol, quantity, price, sl_price):
        """Place a buy order"""
        try:
            logger.info(f"🟢 Placing BUY order: {quantity} shares @ ₹{price}")
            
            order_id = self.kite.place_order(
                symbol=symbol,
                transaction_type="BUY",
                quantity=quantity,
                price=price,
                product=config.TRADE_TYPE,
                order_type="MARKET"
            )
            
            if order_id:
                self.entry_price = price
                self.entry_quantity = quantity
                self.entry_side = "BUY"
                self.sl_price = sl_price
                self.log_trade("BUY", "BUY", price, quantity)
                
                # Place stoploss order immediately after buy order
                logger.info(f"   Placing STOPLOSS order for protection...")
                sl_order_id = self.place_stoploss_order(symbol, "BUY", quantity, sl_price)
                if sl_order_id:
                    self.sl_order_id = sl_order_id  # Store for future updates
                    logger.info(f"   ✓ Stoploss order placed: {sl_order_id} @ ₹{sl_price}")
                else:
                    logger.warning(f"   ⚠️  Failed to place stoploss order - monitoring software SL only")
                
                return order_id
            return None
            
        except Exception as e:
            logger.error(f"✗ Error placing buy order: {e}")
            return None
    
    def place_sell_order(self, symbol, quantity, price, sl_price):
        """Place a sell order"""
        try:
            logger.info(f"🔴 Placing SELL order: {quantity} shares @ ₹{price}")
            
            order_id = self.kite.place_order(
                symbol=symbol,
                transaction_type="SELL",
                quantity=quantity,
                price=price,
                product=config.TRADE_TYPE,
                order_type="MARKET"
            )
            
            if order_id:
                self.entry_price = price
                self.entry_quantity = quantity
                self.entry_side = "SELL"
                self.sl_price = sl_price
                self.log_trade("SELL", "SELL", price, quantity)
                
                # Place stoploss order immediately after sell order
                logger.info(f"   Placing STOPLOSS order for protection...")
                sl_order_id = self.place_stoploss_order(symbol, "SELL", quantity, sl_price)
                if sl_order_id:
                    self.sl_order_id = sl_order_id  # Store for future updates
                    logger.info(f"   ✓ Stoploss order placed: {sl_order_id} @ ₹{sl_price}")
                else:
                    logger.warning(f"   ⚠️  Failed to place stoploss order - monitoring software SL only")
                
                return order_id
            return None
            
        except Exception as e:
            logger.error(f"✗ Error placing sell order: {e}")
            return None
    
    def place_stoploss_order(self, symbol, side, quantity, sl_price):
        """Place a stoploss order (cancel previous if exists)"""
        try:
            # Cancel previous stoploss order if one exists
            if self.sl_order_id:
                try:
                    self.kite.cancel_order(self.sl_order_id)
                    logger.info(f"   ✓ Previous stoploss order {self.sl_order_id} cancelled")
                except Exception as e:
                    logger.warning(f"   ⚠️  Could not cancel previous SL order: {e}")
                self.sl_order_id = None
            
            opposite_side = "SELL" if side == "BUY" else "BUY"
            logger.info(f"⚠️  Placing STOPLOSS {opposite_side} order @ ₹{sl_price}")
            
            order_id = self.kite.place_order(
                symbol=symbol,
                transaction_type=opposite_side,
                quantity=quantity,
                trigger_price=sl_price,
                product=config.TRADE_TYPE,
                order_type="SL-M"  # Stop Loss Market
            )
            
            if order_id:
                logger.info(f"✓ Stoploss order placed: {order_id}")
                return order_id
            return None
            
        except Exception as e:
            logger.error(f"✗ Error placing stoploss order: {e}")
            return None
    
    def close_position(self, symbol, quantity, exit_price):
        """Close a position at current market price"""
        try:
            opposite_side = "SELL" if self.entry_side == "BUY" else "BUY"
            
            order_id = self.kite.place_order(
                symbol=symbol,
                transaction_type=opposite_side,
                quantity=quantity,
                product=config.TRADE_TYPE,
                order_type="MARKET"
            )
            
            if order_id:
                pnl = (exit_price - self.entry_price) * quantity
                if self.entry_side == "SELL":
                    pnl = (self.entry_price - exit_price) * quantity
                
                self.log_trade("EXIT", opposite_side, exit_price, quantity, pnl)
                return order_id
            return None
            
        except Exception as e:
            logger.error(f"✗ Error closing position: {e}")
            return None
    
    def get_symbols_setup_data(self):
        """Fetch opening candles and calculate triggers for all monitored symbols"""
        symbols_data = {}
        
        self.log_to_db("=" * 80)
        self.log_to_db("📊 FETCHING DATA FOR ALL MONITORED SYMBOLS")
        self.log_to_db("=" * 80)
        logger.info("=" * 80)
        logger.info("📊 FETCHING DATA FOR ALL MONITORED SYMBOLS")
        logger.info("=" * 80)
        
        for symbol_config in config.SYMBOLS_TO_MONITOR:
            symbol = symbol_config["symbol"]
            exchange = symbol_config["exchange"]
            
            try:
                msg = f"\n🔍 Processing {exchange}:{symbol}..."
                logger.info(msg)
                self.log_to_db(msg)
                
                # Skip if API is unavailable - use demo data
                if not self.api_key or not self.access_token:
                    self.log_to_db(f"   ⚠️  {symbol}: No API credentials - Skipping symbol (real API required for backtesting)")
                    logger.warning(f"   ⚠️  {symbol}: No API credentials - Skipping symbol")
                    continue  # Skip this symbol instead of using fake data
                    # Use demo opening range data (will work with watchlist from API)
                    vwap = config.DEMO_VWAP if hasattr(config, 'DEMO_VWAP') else 200.0
                    h = 205.0
                    l = 195.0
                    o = 200.0
                    c = 202.0
                    token = None
                else:
                    # Find instrument token
                    token = self.kite.find_instrument_token(exchange, symbol)
                    if not token:
                        msg = f"  ✗ Could not find token for {symbol}, skipping"
                        logger.warning(msg)
                        self.log_to_db(msg)
                        continue
                    
                    # Get opening candle
                    o, h, l, c = self.get_first_candle(token)
                    if o is None or h is None:
                        msg = f"  ✗ Could not fetch candle for {symbol}, skipping"
                        logger.warning(msg)
                        self.log_to_db(msg)
                        continue
                    
                    # Calculate VWAP
                    vwap = self.calculate_vwap(token)
                    if vwap is None:
                        msg = f"  ✗ Could not calculate VWAP for {symbol}, skipping"
                        logger.warning(msg)
                        self.log_to_db(msg)
                        continue
                
                # Range quality filter (skip in demo mode)
                if config.USE_RANGE_FILTER and self.api_key and self.access_token:
                    if not self.check_range_quality(symbol, h, l, vwap):
                        continue

                # Define triggers using ATR-based buffer if enabled
                if config.USE_DYNAMIC_ATR_BUFFER and token:
                    buffer = self.calculate_atr_buffer(token)
                else:
                    buffer = config.BUFFER_AMOUNT

                long_trigger = h + buffer
                short_trigger = l - buffer
                
                symbols_data[symbol] = {
                    "token": token,
                    "exchange": exchange,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "vwap": vwap,
                    "long_trigger": long_trigger,
                    "short_trigger": short_trigger,
                    "buffer": buffer
                }
                
                msg = f"  ✓ {symbol} setup complete: Range {l:.2f} - {h:.2f}, VWAP ₹{vwap:.2f}, Buffer ₹{buffer:.2f}, Triggers: {long_trigger:.2f} / {short_trigger:.2f}"
                logger.info(msg)
                self.log_to_db(msg)
                
            except Exception as e:
                msg = f"  ✗ Error processing {symbol}: {e}"
                logger.error(msg)
                self.log_to_db(msg)
                continue
        
        msg = f"\n✓ Successfully configured {len(symbols_data)}/{len(config.SYMBOLS_TO_MONITOR)} symbols for monitoring"
        logger.info(msg)
        self.log_to_db(msg)
        
        return symbols_data
    
    def run_daily_trading_session(self):
        """Execute one day's trading session with multiple symbols"""
        self.log_to_db("ENTERED run_daily_trading_session - checking Kite API...")
        
        # Skip health check if credentials are missing - just proceed with trading attempt
        if not self.api_key or not self.access_token:
            self.log_to_db("⚠️  Skipping API health check (no credentials) - proceeding with trading attempt")
            logger.warning("⚠️  No API credentials - skipping health check")
        else:
            # Verify API
            logger.info("Checking Kite API connectivity...")
            self.log_to_db("Running API health check...")
            if not self.health_check():
                self.log_to_db("ERROR: API health check failed - will continue anyway")
                logger.error("❌ API health check failed - continuing with trading attempt anyway")
        
        logger.info("✓ Bot initialized successfully")
        self.log_to_db("✓ Bot initialized - checking market time")
        logger.info("Waiting for market open...")
        
        # Wait for market to open and for the entry window
        self.log_to_db("Waiting for market to open at 9:30 AM...")
        if not self.wait_until_market_time(9, 30):
            self.log_to_db("ERROR: Cannot start - market is closed")
            logger.error("Cannot start - market is closed")
            return False
        
        # Get setup data for all symbols
        self.log_to_db("Fetching opening range data for all symbols...")
        symbols_data = self.get_symbols_setup_data()
        
        if not symbols_data:
            self.log_to_db("ERROR: No symbols configured successfully")
            logger.error("❌ No symbols configured successfully. Skipping today.")
            return False
        
        # Wait for entry signals from ANY symbol (until 9:45 AM)
        signal_found = False
        entry_side = None
        entry_price = None
        selected_symbol = None
        selected_symbol_data = None
        pending_retests = {}
        
        logger.info("\n🔍 MONITORING ALL SYMBOLS FOR ENTRY SIGNALS...")
        logger.info(f"📊 Watching: {', '.join(symbols_data.keys())}")
        logger.info("⏰ IMPROVEMENT #4: Extended window: 9:30-10:15 (PRIMARY) + 10:15-10:45 (SOFT)\n")
        self.log_to_db("🔍 MONITORING ALL SYMBOLS FOR ENTRY SIGNALS...")
        self.log_to_db(f"📊 Watching: {', '.join(symbols_data.keys())}")
        self.log_to_db("⏰ Entry window: 9:30-10:15 (PRIMARY) + 10:15-10:45 (SOFT)")
        
        # IMPROVEMENT #6: Check NIFTY trend at start
        self.nifty_bias = self.check_nifty_trend()
        logger.info(f"📈 NIFTY Bias: {self.nifty_bias}")
        self.log_to_db(f"📈 NIFTY Bias: {self.nifty_bias}")
        
        last_debug_log_time = get_ist_time()
        while not signal_found and not self.should_stop:
            now = get_ist_time()
            current_time_int = now.hour * 100 + now.minute  # 930 = 9:30, 1045 = 10:45

            if self.num_trades_today >= config.MAX_TRADES_PER_DAY_PORTFOLIO:
                logger.info("🛑 Portfolio trade cap reached - no more entries")
                self.log_to_db("🛑 Portfolio trade cap reached - no more entries")
                break
            
            # IMPROVEMENT #4: Extended entry window - check if trading is allowed
            if current_time_int >= 1045:  # After 10:45 AM
                logger.info("⏰ Entry window CLOSED (after 10:45 AM)")
                self.log_to_db("⏰ Entry window CLOSED (after 10:45 AM)")
                break
            
            # Determine window state for soft cutoff logic
            if current_time_int < 1015:  # Before 10:15 AM
                self.entry_window_state = "PRIMARY"
            elif current_time_int < 1045:  # Between 10:15-10:45 AM
                self.entry_window_state = "SOFT"
            else:
                self.entry_window_state = "CLOSED"
                break
            
            # Check stop flag
            if self.should_stop:
                logger.info("🛑 Stop requested during entry search")
                self.log_to_db("🛑 Stop requested during entry search")
                return False
            
            # Periodic debug logging for why signals are not firing
            should_log_debug = (now - last_debug_log_time).seconds >= 120

            # Check each symbol for signals
            for symbol, data in symbols_data.items():
                if self.trades_by_symbol.get(symbol, 0) >= config.MAX_TRADES_PER_SYMBOL:
                    continue
                token = data["token"]
                vwap = data["vwap"]
                long_trigger = data["long_trigger"]
                short_trigger = data["short_trigger"]
                buffer = data.get("buffer", 0.1)
                
                # Get latest 5-min candle
                candle = self.get_latest_5min_candle(token)
                if not candle:
                    if should_log_debug:
                        self.log_to_db(f"⚠️  {symbol}: No 5-min candle data yet")
                    continue
                
                o, h_5, l_5, c_5, v, candle_time = candle
                
                # IMPROVEMENT #3: Volume Confirmation Check
                volume_confirmed = self.check_volume_confirmation(token, candle)

                if should_log_debug:
                    debug_msg = (
                        f"🧪 {symbol} | Close: ₹{c_5:.2f} | LT: ₹{long_trigger:.2f} | ST: ₹{short_trigger:.2f} | "
                        f"VWAP: ₹{vwap:.2f} | VolOK: {volume_confirmed} | Window: {self.entry_window_state} | "
                        f"NIFTY: {self.nifty_bias}"
                    )
                    logger.info(debug_msg)
                    self.log_to_db(debug_msg)
                
                # Retest handling (if waiting for confirmation)
                if config.USE_RETEST_ENTRY and symbol in pending_retests:
                    state = pending_retests[symbol]
                    if candle_time == state.get("last_candle_time"):
                        continue
                    state["last_candle_time"] = candle_time
                    state["candles_waited"] += 1

                    if state["candles_waited"] > config.RETEST_MAX_CANDLES:
                        logger.info(f"   ⏳ {symbol}: Retest timeout - no entry")
                        self.log_skip(f"{symbol}: Retest timeout - no entry")
                        del pending_retests[symbol]
                        continue

                    zone_pct = config.RETEST_ZONE_PCT / 100
                    zone_low = state["trigger"] * (1 - zone_pct)
                    zone_high = state["trigger"] * (1 + zone_pct)

                    if state["side"] == "BUY":
                        retest_ok = l_5 <= zone_high and h_5 >= zone_low and c_5 > state["trigger"] and c_5 > vwap
                    else:
                        retest_ok = h_5 >= zone_low and l_5 <= zone_high and c_5 < state["trigger"] and c_5 < vwap

                    if not retest_ok:
                        continue

                    # Filters for retest entry
                    if config.USE_VOLUME_FILTER and not volume_confirmed:
                        logger.info(f"   ⚠️  {symbol}: Volume not confirmed on retest - SKIP")
                        self.log_skip(f"{symbol}: Volume not confirmed on retest")
                        continue

                    if self.is_nifty_bias_blocking(state["side"]):
                        logger.info(f"   ⚠️  {symbol}: NIFTY bias blocking {state['side']} - SKIP")
                        self.log_skip(f"{symbol}: NIFTY bias blocking {state['side']}")
                        continue

                    if config.USE_TREND_FILTER and not self.is_trend_aligned(token, c_5, state["side"]):
                        logger.info(f"   ⚠️  {symbol}: Trend filter not aligned - SKIP")
                        self.log_skip(f"{symbol}: Trend filter not aligned")
                        continue

                    if config.USE_LIQUIDITY_FILTER and not self.check_liquidity_and_spread(data["exchange"], symbol):
                        logger.info(f"   ⚠️  {symbol}: Liquidity/spread filter failed - SKIP")
                        self.log_skip(f"{symbol}: Liquidity/spread filter failed")
                        continue

                    logger.info(f"\n✅ RETEST CONFIRMED on {symbol}!")
                    entry_side = state["side"]
                    entry_price = c_5
                    selected_symbol = symbol
                    selected_symbol_data = data
                    signal_found = True
                    del pending_retests[symbol]
                    break

                # Check for long signal
                if c_5 > long_trigger and c_5 > vwap:
                    # Apply soft cutoff restrictions
                    if self.entry_window_state == "SOFT":
                        # In soft window, need extra confirmation (volume 2x or ATR expanding)
                        if not volume_confirmed:
                            logger.info(f"   ⚠️  {symbol}: Volume not 2x in SOFT window - SKIP")
                            self.log_skip(f"{symbol}: Volume not 2x in SOFT window")
                            continue
                    
                    # IMPROVEMENT #6: NIFTY Filter - only LONG if NIFTY > NIFTY_VWAP
                    if self.is_nifty_bias_blocking("BUY"):
                        logger.info(f"   ⚠️  {symbol}: NIFTY bias blocking BUY - SKIP")
                        self.log_skip(f"{symbol}: NIFTY bias blocking BUY")
                        continue
                    
                    # Higher timeframe trend alignment
                    if config.USE_TREND_FILTER and not self.is_trend_aligned(token, c_5, "BUY"):
                        logger.info(f"   ⚠️  {symbol}: Trend filter not aligned - SKIP")
                        self.log_skip(f"{symbol}: Trend filter not aligned")
                        continue

                    # Liquidity & spread filter
                    if config.USE_LIQUIDITY_FILTER and not self.check_liquidity_and_spread(data["exchange"], symbol):
                        logger.info(f"   ⚠️  {symbol}: Liquidity/spread filter failed - SKIP")
                        self.log_skip(f"{symbol}: Liquidity/spread filter failed")
                        continue

                    if config.USE_RETEST_ENTRY:
                        pending_retests[symbol] = {
                            "side": "BUY",
                            "trigger": long_trigger,
                            "last_candle_time": candle_time,
                            "candles_waited": 0
                        }
                        logger.info(f"   🧪 {symbol}: Breakout detected - waiting for retest")
                        self.log_to_db(f"🧪 {symbol}: Breakout detected - waiting for retest")
                        continue

                    logger.info(f"\n🟢 LONG SIGNAL DETECTED on {symbol}!")
                    logger.info(f"   Exchange: {data['exchange']}")
                    logger.info(f"   5-min close: ₹{c_5:.2f} > trigger ₹{long_trigger:.2f}")
                    logger.info(f"   Price > VWAP: ₹{c_5:.2f} > ₹{vwap:.2f}")
                    logger.info(f"   IMPROVEMENT #3: Volume Confirmed: {volume_confirmed}")
                    logger.info(f"   IMPROVEMENT #6: NIFTY Bias: {self.nifty_bias}")
                    entry_side = "BUY"
                    entry_price = c_5
                    selected_symbol = symbol
                    selected_symbol_data = data
                    signal_found = True
                    break
                
                # Check for short signal
                elif c_5 < short_trigger and c_5 < vwap:
                    # Apply soft cutoff restrictions
                    if self.entry_window_state == "SOFT":
                        if not volume_confirmed:
                            logger.info(f"   ⚠️  {symbol}: Volume not 2x in SOFT window - SKIP")
                            self.log_skip(f"{symbol}: Volume not 2x in SOFT window")
                            continue
                    
                    # IMPROVEMENT #6: NIFTY Filter - only SHORT if NIFTY < NIFTY_VWAP
                    if self.is_nifty_bias_blocking("SELL"):
                        logger.info(f"   ⚠️  {symbol}: NIFTY bias blocking SELL - SKIP")
                        self.log_skip(f"{symbol}: NIFTY bias blocking SELL")
                        continue
                    
                    # Higher timeframe trend alignment
                    if config.USE_TREND_FILTER and not self.is_trend_aligned(token, c_5, "SELL"):
                        logger.info(f"   ⚠️  {symbol}: Trend filter not aligned - SKIP")
                        self.log_skip(f"{symbol}: Trend filter not aligned")
                        continue

                    # Liquidity & spread filter
                    if config.USE_LIQUIDITY_FILTER and not self.check_liquidity_and_spread(data["exchange"], symbol):
                        logger.info(f"   ⚠️  {symbol}: Liquidity/spread filter failed - SKIP")
                        self.log_skip(f"{symbol}: Liquidity/spread filter failed")
                        continue

                    if config.USE_RETEST_ENTRY:
                        pending_retests[symbol] = {
                            "side": "SELL",
                            "trigger": short_trigger,
                            "last_candle_time": candle_time,
                            "candles_waited": 0
                        }
                        logger.info(f"   🧪 {symbol}: Breakout detected - waiting for retest")
                        self.log_to_db(f"🧪 {symbol}: Breakout detected - waiting for retest")
                        continue

                    logger.info(f"\n🔴 SHORT SIGNAL DETECTED on {symbol}!")
                    logger.info(f"   Exchange: {data['exchange']}")
                    logger.info(f"   5-min close: ₹{c_5:.2f} < trigger ₹{short_trigger:.2f}")
                    logger.info(f"   Price < VWAP: ₹{c_5:.2f} < ₹{vwap:.2f}")
                    logger.info(f"   IMPROVEMENT #3: Volume Confirmed: {volume_confirmed}")
                    logger.info(f"   IMPROVEMENT #6: NIFTY Bias: {self.nifty_bias}")
                    entry_side = "SELL"
                    entry_price = c_5
                    selected_symbol = symbol
                    selected_symbol_data = data
                    signal_found = True
                    break
            
            if signal_found:
                break

            if should_log_debug:
                last_debug_log_time = now
            
            time.sleep(30)
        
        if not signal_found:
            logger.info("\n📊 No entry signal found from any symbol today.")
            self.generate_final_report()
            return True  # Successful day, just no signals
        
        # Execute trade on the selected symbol
        logger.info(f"\n💼 EXECUTING TRADE ON: {selected_symbol}")
        logger.info("=" * 60)
        
        # IMPROVEMENT #7: Dynamic Stop Loss (instead of just VWAP)
        # Get current candle to calculate dynamic SL
        current_candle = self.get_latest_5min_candle(selected_symbol_data["token"])
        if current_candle:
            o, h_5, l_5, c_5, v, _ = current_candle
            sl_price = self.calculate_dynamic_sl(entry_side, selected_symbol_data["vwap"], h_5, l_5)
        else:
            # Fallback: Use VWAP
            sl_price = selected_symbol_data["vwap"]
        
        # IMPROVEMENT #9: Tighter Stop Loss (apply distance factor)
        # Apply STOPLOSS_DISTANCE_FACTOR to make SL tighter (50% closer to entry)
        sl_price = self.apply_stoploss_distance_factor(entry_price, sl_price, entry_side)
        
        # Store traded symbol for partial exit tracking
        self.traded_symbol = selected_symbol
        
        # IMPROVEMENT #1: Smart Limit Orders (not market orders)
        # Place entry order with limit price = trigger + buffer
        if config.USE_LIMIT_ORDERS:
            limit_price = entry_price + (0.20 if entry_side == "BUY" else -0.20)
            logger.info(f"   IMPROVEMENT #1: Using Limit Order - Entry: ₹{entry_price:.2f} -> Limit: ₹{limit_price:.2f}")
        else:
            limit_price = entry_price

        quantity = self.calculate_dynamic_quantity(limit_price)
        if quantity == 0:
            logger.error("Cannot calculate quantity. Skipping trade.")
            return False

        logger.info(f"   IMPROVEMENT #7: Dynamic SL calculated: ₹{sl_price:.2f}")
        self.display_trade_details(entry_side, limit_price, quantity, sl_price, selected_symbol)
        
        if entry_side == "BUY":
            order = self.place_buy_order(selected_symbol, quantity, limit_price, sl_price)
        else:
            order = self.place_sell_order(selected_symbol, quantity, limit_price, sl_price)
        
        if not order:
            logger.error("Failed to place order. Skipping trade.")
            return False
        
        # 🆕 SAVE TRADE TO DATABASE IMMEDIATELY for real-time sync
        self.trade_db_id = self.save_trade_to_db(entry_side, selected_symbol, quantity, entry_price, sl_price, target_price)
        
        # Record trade (for tracking daily stats and multi-trade logic)
        self.num_trades_today += 1  # IMPROVEMENT #5: Track number of trades
        self.trades_by_symbol[selected_symbol] = self.trades_by_symbol.get(selected_symbol, 0) + 1
        trade = {
            'entry_side': entry_side,
            'entry_price': entry_price,
            'entry_qty': quantity,
            'exit_price': None,
            'exit_qty': quantity,
            'sl_price': sl_price,
            'pnl': None,
            'trade_number': self.num_trades_today
        }
        
        # Wait for exit (until 3:25 PM)
        # IMPROVEMENT #8: Track partial booking and trailing state
        last_price = entry_price
        target_price = None
        second_target_price = None
        eod_target_price = None
        token = selected_symbol_data["token"]
        self.partial_booked_75pct = False
        first_partial_booked = False
        second_partial_booked = False
        self.sl_moved_to_breakeven = False
        self.remaining_quantity = quantity
        initial_quantity = quantity
        realized_pnl = 0.0
        
        if config.PROFIT_TARGET_TYPE == "ratio":
            risk = abs(entry_price - sl_price)
            
            # AGGRESSIVE PARTIAL BOOKING TARGETS:
            # First target at 0.5R (take 25% quick profit)
            first_reward = risk * getattr(config, 'PARTIAL_BOOKING_FIRST_TARGET_R', 0.5)
            target_price = entry_price + first_reward if entry_side == "BUY" else entry_price - first_reward
            
            # Second target at 1R (take 50% at breakeven SL)
            second_reward = risk * getattr(config, 'PARTIAL_BOOKING_SECOND_TARGET_R', 1.0)
            second_target_price = entry_price + second_reward if entry_side == "BUY" else entry_price - second_reward
            
            # Final target at 2R (for end of day - hold remaining 25%)
            final_reward = risk * config.PROFIT_TARGET_RATIO
            eod_target_price = entry_price + final_reward if entry_side == "BUY" else entry_price - final_reward

        first_close_pct = getattr(config, 'PARTIAL_BOOKING_FIRST_CLOSE_PCT', 0.25)
        second_close_pct = getattr(config, 'PARTIAL_BOOKING_SECOND_CLOSE_PCT', 0.50)
        eod_close_pct = getattr(config, 'PARTIAL_BOOKING_EOD_CLOSE_PCT', 0.25)
        
        first_close_qty = int(initial_quantity * first_close_pct)
        second_close_qty = int(initial_quantity * second_close_pct)
        eod_close_qty = int(initial_quantity * eod_close_pct)

        if initial_quantity >= 2 and first_close_qty == 0:
            first_close_qty = 1
        if initial_quantity >= 4 and second_close_qty == 0:
            second_close_qty = 1

        if first_close_qty + second_close_qty >= initial_quantity:
            overflow = (first_close_qty + second_close_qty) - (initial_quantity - 1)
            if overflow > 0 and second_close_qty > 0:
                reduce_second = min(second_close_qty, overflow)
                second_close_qty -= reduce_second
                overflow -= reduce_second
            if overflow > 0 and first_close_qty > 0:
                reduce_first = min(first_close_qty, overflow)
                first_close_qty -= reduce_first

        base_risk = abs(entry_price - sl_price)
        
        logger.info(f"")
        logger.info(f"🎯 AGGRESSIVE EXIT TARGETS for {selected_symbol}:")
        if config.USE_PARTIAL_BOOKING and target_price:
            logger.info(f"   Target 1 @ 0.5R ({first_close_pct*100:.0f}% qty): ₹{target_price:.2f} - QUICK PROFIT")
            if second_target_price:
                logger.info(f"   Target 2 @ 1.0R ({second_close_pct*100:.0f}% qty): ₹{second_target_price:.2f} - SL MOVES TO BREAKEVEN")
            if eod_target_price:
                logger.info(f"   Target 3 @ 2.0R ({eod_close_pct*100:.0f}% qty): ₹{eod_target_price:.2f} - FINAL TARGET")
            logger.info("   Final Qty Exit: 3:25 PM auto-exit (or Stoploss hit earlier)")
        elif target_price:
            logger.info(f"   Profit Target: ₹{target_price:.2f}")
        logger.info(f"   Stoploss (TIGHT): ₹{sl_price:.2f} (50% closer to entry)")
        logger.info("")
        
        # Monitoring loop
        while True:
            now = get_ist_time()
            
            # Auto-exit at 3:25 PM
            if now.hour == 15 and now.minute >= 25:
                logger.warning("⏰ Market closing time - Auto-exiting position")
                exit_qty = self.remaining_quantity if (self.remaining_quantity and self.remaining_quantity > 0) else quantity
                if exit_qty > 0:  # Only close if there's remaining quantity
                    exit_order = self.close_position(selected_symbol, exit_qty, last_price)
                    if exit_order:
                        trade['exit_price'] = last_price
                        final_leg_pnl = (last_price - entry_price) * exit_qty if entry_side == "BUY" else (entry_price - last_price) * exit_qty
                        trade['pnl'] = realized_pnl + final_leg_pnl
                        self.trades.append(trade)
                        
                        # 🆕 UPDATE DB with market close exit
                        if self.trade_db_id:
                            self.update_trade_in_db(
                                self.trade_db_id,
                                exit_price=last_price,
                                exit_time=get_ist_time(),
                                pnl=trade['pnl'],
                                status='CLOSED'
                            )
                break
            
            # IMPROVEMENT #9: Check Daily Loss Limit
            if config.USE_DAILY_LOSS_LIMIT:
                can_continue = self.check_daily_loss_limit()
                if not can_continue:
                    logger.error("IMPROVEMENT #9: Daily Loss Limit Hit! Auto-shutdown initiated")
                    exit_qty = self.remaining_quantity if (self.remaining_quantity and self.remaining_quantity > 0) else quantity
                    if exit_qty > 0:  # Only close if there's remaining quantity
                        exit_order = self.close_position(selected_symbol, exit_qty, last_price)
                        if exit_order:
                            trade['exit_price'] = last_price
                            final_leg_pnl = (last_price - entry_price) * exit_qty if entry_side == "BUY" else (entry_price - last_price) * exit_qty
                            trade['pnl'] = realized_pnl + final_leg_pnl
                            self.trades.append(trade)
                            
                            # 🆕 UPDATE DB with loss limit exit
                            if self.trade_db_id:
                                self.update_trade_in_db(
                                    self.trade_db_id,
                                    exit_price=last_price,
                                    exit_time=get_ist_time(),
                                    pnl=trade['pnl'],
                                    status='CLOSED'
                                )
                    return False  # Stop trading for the day
            
            # Get live price
            price = self.get_live_price(token, selected_symbol)
            if price:
                last_price = price

                # ATR trailing stop update
                if config.USE_ATR_TRAILING_EXIT and base_risk > 0:
                    profit = price - entry_price if entry_side == "BUY" else entry_price - price
                    if profit >= base_risk * config.ATR_TRAIL_START_R:
                        atr_value = self.get_cached_atr(token, config.ATR_TRAIL_REFRESH_SEC)
                        if atr_value and atr_value > 0:
                            trail_distance = atr_value * config.ATR_TRAIL_MULTIPLIER
                            if entry_side == "BUY":
                                new_sl = price - trail_distance
                                if new_sl > sl_price:
                                    sl_price = new_sl
                                    logger.info(f"🔁 ATR Trailing SL updated (LONG): ₹{sl_price:.2f}")
                                    # Update stoploss order
                                    new_sl_id = self.place_stoploss_order(selected_symbol, entry_side, quantity, sl_price)
                                    if new_sl_id:
                                        self.sl_order_id = new_sl_id
                            else:
                                new_sl = price + trail_distance
                                if new_sl < sl_price:
                                    sl_price = new_sl
                                    logger.info(f"🔁 ATR Trailing SL updated (SHORT): ₹{sl_price:.2f}")
                                    # Update stoploss order
                                    new_sl_id = self.place_stoploss_order(selected_symbol, entry_side, quantity, sl_price)
                                    if new_sl_id:
                                        self.sl_order_id = new_sl_id
                
                # IMPROVEMENT #8: Partial Booking Logic
                if config.USE_PARTIAL_BOOKING:
                    risk = base_risk if base_risk > 0 else abs(entry_price - sl_price)
                    profit = abs(price - entry_price)
                    
                    # At 1R: Move SL to breakeven
                    if not self.sl_moved_to_breakeven and profit >= risk:
                        logger.info(f"IMPROVEMENT #8: 1R Hit! Moving SL to breakeven (entry price)")
                        sl_price = entry_price
                        self.sl_moved_to_breakeven = True
                        # Update stoploss order
                        new_sl_id = self.place_stoploss_order(selected_symbol, entry_side, quantity, sl_price)
                        if new_sl_id:
                            self.sl_order_id = new_sl_id
                    
                    # Target 1: Close 25% at 0.5R (QUICK PROFIT)
                    current_quantity = self.remaining_quantity if self.remaining_quantity else quantity
                    if (not first_partial_booked and target_price and first_close_qty > 0 and current_quantity > 1 and
                        ((entry_side == "BUY" and price >= target_price) or (entry_side == "SELL" and price <= target_price))):
                        close_qty = min(first_close_qty, max(current_quantity - 1, 0))
                        if close_qty > 0:
                            logger.info(f"🎯 TARGET 1 @ 0.5R HIT! Closing {close_qty} shares ({first_close_pct*100:.0f}%) at ₹{price:.2f} - QUICK PROFIT TAKEN")
                            exit_order = self.close_position(selected_symbol, close_qty, price)
                            if exit_order:
                                partial_pnl = (price - entry_price) * close_qty if entry_side == "BUY" else (entry_price - price) * close_qty
                                realized_pnl += partial_pnl
                                logger.info(f"   ✓ Partial P&L (Target 1): ₹{partial_pnl:.2f}")
                                first_partial_booked = True
                                self.remaining_quantity = current_quantity - close_qty

                    # Target 2: Close 50% at 1.0R (MAIN TARGET - SL MOVES TO BREAKEVEN)
                    current_quantity = self.remaining_quantity if self.remaining_quantity else quantity
                    if (first_partial_booked and not second_partial_booked and second_target_price and second_close_qty > 0 and current_quantity > 1 and
                        ((entry_side == "BUY" and price >= second_target_price) or (entry_side == "SELL" and price <= second_target_price))):
                        close_qty = min(second_close_qty, max(current_quantity - 1, 0))
                        if close_qty > 0:
                            logger.info(f"🎯 TARGET 2 @ 1.0R HIT! Closing {close_qty} shares ({second_close_pct*100:.0f}%) at ₹{price:.2f} - MAIN TARGET")
                            exit_order = self.close_position(selected_symbol, close_qty, price)
                            if exit_order:
                                partial_pnl = (price - entry_price) * close_qty if entry_side == "BUY" else (entry_price - price) * close_qty
                                realized_pnl += partial_pnl
                                logger.info(f"   ✓ Partial P&L (Target 2): ₹{partial_pnl:.2f}")
                                second_partial_booked = True
                                self.remaining_quantity = current_quantity - close_qty
                                
                                # 🔒 LOCK PROFITS: Move SL to entry price - remaining position is now FREE
                                old_sl = sl_price
                                sl_price = entry_price
                                self.sl_moved_to_entry_after_2r = True
                                logger.info(f"🔒 SL MOVED TO BREAKEVEN! Remaining position is now FREE (guaranteed profit)")
                                logger.info(f"   Old SL: ₹{old_sl:.2f} → New SL: ₹{sl_price:.2f}")
                                
                                # Update stoploss order on exchange
                                new_sl_id = self.place_stoploss_order(selected_symbol, entry_side, self.remaining_quantity, sl_price)
                                if new_sl_id:
                                    self.sl_order_id = new_sl_id
                                
                                # 🆕 UPDATE DB with partial booking details
                                if self.trade_db_id:
                                    self.update_trade_in_db(
                                        self.trade_db_id,
                                        quantity=self.remaining_quantity,
                                        exit_price=price,
                                        exit_qty=close_qty,
                                        stoploss_price=sl_price,
                                        pnl=realized_pnl
                                    )
                                second_partial_booked = True
                                self.partial_booked_75pct = True
                                self.remaining_quantity = current_quantity - close_qty
                                
                                # 🆕 UPDATE DB with second partial booking details
                                if self.trade_db_id:
                                    # Remaining quantity still has profit guarantee since SL is at entry price
                                    self.update_trade_in_db(
                                        self.trade_db_id,
                                        quantity=self.remaining_quantity,
                                        exit_price=price,
                                        exit_qty=close_qty,
                                        pnl=realized_pnl
                                    )
                
                # Check for profit target (apply for remaining shares in partial booking mode too)
                exit_qty = self.remaining_quantity if (self.remaining_quantity and self.remaining_quantity > 0) else quantity
                if target_price and exit_qty > 0 and entry_side == "BUY" and price >= target_price and not config.USE_PARTIAL_BOOKING:
                    logger.info(f"🎉 PROFIT TARGET HIT! Closing {selected_symbol} position @ ₹{price:.2f}")
                    exit_order = self.close_position(selected_symbol, exit_qty, price)
                    if exit_order:
                        trade['exit_price'] = price
                        final_leg_pnl = (price - entry_price) * exit_qty
                        trade['pnl'] = realized_pnl + final_leg_pnl
                        self.trades.append(trade)
                        
                        # 🆕 UPDATE DB with final exit
                        if self.trade_db_id:
                            self.update_trade_in_db(
                                self.trade_db_id,
                                exit_price=price,
                                exit_time=get_ist_time(),
                                pnl=trade['pnl'],
                                status='CLOSED'
                            )
                        
                        # IMPROVEMENT #5: Update multi-trade logic result
                        self.trade1_result = "WIN" if trade['pnl'] > 0 else "LOSS"
                    break
                
                elif target_price and exit_qty > 0 and entry_side == "SELL" and price <= target_price and not config.USE_PARTIAL_BOOKING:
                    logger.info(f"🎉 PROFIT TARGET HIT! Closing {selected_symbol} position @ ₹{price:.2f}")
                    exit_order = self.close_position(selected_symbol, exit_qty, price)
                    if exit_order:
                        trade['exit_price'] = price
                        final_leg_pnl = (entry_price - price) * exit_qty
                        trade['pnl'] = realized_pnl + final_leg_pnl
                        self.trades.append(trade)
                        
                        # 🆕 UPDATE DB with final exit
                        if self.trade_db_id:
                            self.update_trade_in_db(
                                self.trade_db_id,
                                exit_price=price,
                                exit_time=get_ist_time(),
                                pnl=trade['pnl'],
                                status='CLOSED'
                            )
                        
                        # IMPROVEMENT #5: Update multi-trade logic result
                        self.trade1_result = "WIN" if trade['pnl'] > 0 else "LOSS"
                    break
                
                # Check for stoploss (Always check - applies to remaining shares too)
                if entry_side == "BUY" and price <= sl_price and exit_qty > 0:
                    logger.error(f"🛑 STOPLOSS HIT! Closing {selected_symbol} position @ ₹{price:.2f} ({exit_qty} shares)")
                    exit_order = self.close_position(selected_symbol, exit_qty, price)
                    if exit_order:
                        trade['exit_price'] = price
                        final_leg_pnl = (price - entry_price) * exit_qty
                        trade['pnl'] = realized_pnl + final_leg_pnl
                        self.trades.append(trade)
                        
                        # 🆕 UPDATE DB with SL hit
                        if self.trade_db_id:
                            self.update_trade_in_db(
                                self.trade_db_id,
                                exit_price=price,
                                exit_time=get_ist_time(),
                                pnl=trade['pnl'],
                                status='CLOSED'
                            )
                        # IMPROVEMENT #5: Update multi-trade logic result
                        self.trade1_result = "WIN" if trade['pnl'] > 0 else "LOSS"
                    break
                
                elif entry_side == "SELL" and price >= sl_price and exit_qty > 0:
                    logger.error(f"🛑 STOPLOSS HIT! Closing {selected_symbol} position @ ₹{price:.2f} ({exit_qty} shares)")
                    exit_order = self.close_position(selected_symbol, exit_qty, price)
                    if exit_order:
                        trade['exit_price'] = price
                        final_leg_pnl = (entry_price - price) * exit_qty
                        trade['pnl'] = realized_pnl + final_leg_pnl
                        self.trades.append(trade)
                        
                        # 🆕 UPDATE DB with SL hit
                        if self.trade_db_id:
                            self.update_trade_in_db(
                                self.trade_db_id,
                                exit_price=price,
                                exit_time=get_ist_time(),
                                pnl=trade['pnl'],
                                status='CLOSED'
                            )
                        
                        # IMPROVEMENT #5: Update multi-trade logic result
                        self.trade1_result = "WIN" if trade['pnl'] > 0 else "LOSS"
                    break
            
            time.sleep(30)
        
        # Generate report
        self.generate_final_report()
        return True
    
    # =======================================
    # 🆕 ALGORITHM UPGRADE METHODS (9 IMPROVEMENTS)
    # =======================================
    
    # PHASE 1: CRITICAL FIXES
    
    def calculate_atr_buffer(self, instrument_token):
        """
        CHANGE 2: Dynamic Volatility Buffer using ATR
        Replaces fixed buffer with adaptive buffer = ATR_MULTIPLIER × ATR
        """
        try:
            atr_value = self.calculate_atr_value(instrument_token)
            if not atr_value:
                logger.warning("Not enough candles for ATR, using fallback buffer")
                return config.BUFFER_AMOUNT

            buffer = config.ATR_MULTIPLIER * atr_value
            logger.info(f"   ATR({config.ATR_PERIOD}): ₹{atr_value:.2f} → Dynamic Buffer: ₹{buffer:.2f}")
            return buffer
            
        except Exception as e:
            logger.warning(f"Error calculating ATR: {e}, using fallback ₹0.10")
            return config.BUFFER_AMOUNT

    def calculate_atr_value(self, instrument_token):
        """Calculate ATR using configured timeframe and period"""
        try:
            now = get_ist_time()
            timeframe = getattr(config, "ATR_TIMEFRAME", "5minute")
            period = getattr(config, "ATR_PERIOD", 14)

            minutes_per_candle = 5
            if timeframe.endswith("minute"):
                try:
                    minutes_per_candle = int(timeframe.replace("minute", ""))
                except ValueError:
                    minutes_per_candle = 5

            lookback_minutes = (period + 2) * minutes_per_candle
            start_time = now - datetime.timedelta(minutes=lookback_minutes)

            candles = self.kite.get_historical_data(
                instrument_token,
                start_time,
                now,
                interval=timeframe
            )

            if not candles or len(candles) < period + 1:
                return None

            tr_values = []
            for i in range(1, len(candles)):
                high = candles[i]['high']
                low = candles[i]['low']
                prev_close = candles[i-1]['close']

                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                tr_values.append(tr)

            atr_value = sum(tr_values[-period:]) / period
            return atr_value
        except Exception as e:
            logger.warning(f"Error calculating ATR value: {e}")
            return None
    
    def check_volume_confirmation(self, instrument_token, current_candle):
        """
        CHANGE 3: Volume Confirmation
        Current volume must be > dynamic threshold based on time-of-day
        """
        try:
            if not config.USE_VOLUME_FILTER:
                return True
            now = get_ist_time()
            lookback = max(5, int(config.VOLUME_LOOKBACK_CANDLES))
            start_time = now - datetime.timedelta(minutes=lookback * 5)

            candles = self.kite.get_historical_data(
                instrument_token,
                start_time,
                now,
                interval="5minute"
            )

            if not candles or len(candles) < 5:
                logger.warning("Not enough candles for volume check, allowing trade")
                return True

            volumes = [c['volume'] for c in candles[-lookback:]]
            avg_volume = sum(volumes) / len(volumes)

            if isinstance(current_candle, (tuple, list)) and len(current_candle) >= 5:
                current_volume = current_candle[4]
            else:
                current_volume = current_candle.get('volume', 0)

            time_factor = 1.0
            if config.USE_TIME_OF_DAY_VOLUME:
                minutes = now.hour * 100 + now.minute
                if minutes < 1015:
                    time_factor = config.VOLUME_EARLY_MULT
                elif minutes < 1230:
                    time_factor = config.VOLUME_MID_MULT
                elif minutes < 1430:
                    time_factor = config.VOLUME_LATE_MULT
                else:
                    time_factor = config.VOLUME_CLOSE_MULT

            required_ratio = config.VOLUME_MULTIPLIER * time_factor
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            if volume_ratio >= required_ratio:
                logger.info(f"   ✓ Volume confirmed: {volume_ratio:.1f}x (need {required_ratio:.1f}x)")
                return True

            logger.info(f"   ✗ Volume weak: {volume_ratio:.1f}x (need {required_ratio:.1f}x)")
            return False
                
        except Exception as e:
            logger.warning(f"Error checking volume: {e}, allowing trade")
            return True

    def check_range_quality(self, symbol, high, low, vwap):
        """Filter out ranges that are too small or too large"""
        try:
            if not vwap or vwap <= 0:
                logger.warning(f"{symbol}: VWAP missing for range check - skipping filter")
                return True

            range_pct = ((high - low) / vwap) * 100
            if range_pct < config.RANGE_MIN_PCT or range_pct > config.RANGE_MAX_PCT:
                logger.info(
                    f"   ⚠️  {symbol}: Opening range {range_pct:.2f}% outside "
                    f"{config.RANGE_MIN_PCT:.2f}%–{config.RANGE_MAX_PCT:.2f}% - SKIP"
                )
                self.log_skip(
                    f"{symbol}: Opening range {range_pct:.2f}% outside "
                    f"{config.RANGE_MIN_PCT:.2f}%–{config.RANGE_MAX_PCT:.2f}%"
                )
                return False

            return True
        except Exception as e:
            logger.warning(f"Error checking range quality: {e}, allowing trade")
            return True

    def check_liquidity_and_spread(self, exchange, symbol):
        """Filter out illiquid or wide-spread symbols"""
        try:
            if not self.api_key or not self.access_token:
                return True

            quote = self.kite.get_quote(exchange, symbol)
            if not quote:
                logger.warning(f"{symbol}: Quote unavailable - skipping")
                return False

            volume = quote.get("volume", 0) or 0
            if volume and volume < config.MIN_DAILY_VOLUME:
                logger.info(f"   ⚠️  {symbol}: Volume {volume} below minimum {config.MIN_DAILY_VOLUME}")
                self.log_skip(f"{symbol}: Volume {volume} below minimum {config.MIN_DAILY_VOLUME}")
                return False

            ltp = quote.get("last_price", 0)
            depth = quote.get("depth", {}) or {}
            bid = (depth.get("buy") or [{}])[0].get("price")
            ask = (depth.get("sell") or [{}])[0].get("price")

            if not bid or not ask or ltp <= 0:
                logger.warning(f"{symbol}: Depth/price data missing - skipping")
                return False

            spread_pct = ((ask - bid) / ltp) * 100
            if spread_pct > config.MAX_SPREAD_PCT:
                logger.info(f"   ⚠️  {symbol}: Spread {spread_pct:.2f}% above {config.MAX_SPREAD_PCT:.2f}%")
                self.log_skip(
                    f"{symbol}: Spread {spread_pct:.2f}% above {config.MAX_SPREAD_PCT:.2f}%"
                )
                return False

            return True
        except Exception as e:
            logger.warning(f"Error checking liquidity/spread: {e}, allowing trade")
            return True

    def get_cached_atr(self, instrument_token, refresh_sec):
        """Get cached ATR value for trailing stops"""
        try:
            now = get_ist_time()
            last_time = self.atr_cache_time.get(instrument_token)
            if last_time and (now - last_time).seconds < refresh_sec:
                return self.atr_cache.get(instrument_token)

            atr_value = self.calculate_atr_value(instrument_token)
            if atr_value:
                self.atr_cache[instrument_token] = atr_value
                self.atr_cache_time[instrument_token] = now
            return atr_value
        except Exception as e:
            logger.warning(f"Error reading ATR cache: {e}")
            return None

    def get_trend_vwap(self, instrument_token):
        """Get cached higher timeframe VWAP for trend alignment"""
        try:
            now = get_ist_time()
            cache_entry = self.htf_cache.get(instrument_token)
            if cache_entry and (now - cache_entry["time"]).seconds < config.TREND_REFRESH_SEC:
                return cache_entry["vwap"]

            start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
            candles = self.kite.get_historical_data(
                instrument_token,
                start_time,
                now,
                interval=config.TREND_TIMEFRAME
            )

            if not candles:
                return None

            vwap = self.kite.calculate_vwap(candles)
            if vwap:
                self.htf_cache[instrument_token] = {"vwap": vwap, "time": now}
            return vwap
        except Exception as e:
            logger.warning(f"Error calculating trend VWAP: {e}")
            return None

    def is_trend_aligned(self, instrument_token, price, side):
        """Check higher timeframe trend alignment"""
        if not config.USE_TREND_FILTER:
            return True

        vwap = self.get_trend_vwap(instrument_token)
        if not vwap:
            return True

        if side == "BUY":
            return price > vwap
        return price < vwap
    
    # ⚠️  DEPRECATED: Limit order methods not used in main flow
    # The CONFIG_USE_LIMIT_ORDERS flag is set but implementation was moved to place_buy_order/place_sell_order
    # Keeping these for reference if limit order support is needed in future
    
    def place_limit_buy_order(self, symbol, quantity, trigger_price):
        """
        DEPRECATED - Use place_buy_order() instead
        CHANGE 1: Smart Limit Orders
        Place STOP-LIMIT order instead of market order to eliminate slippage
        """
        logger.warning("place_limit_buy_order() is deprecated - use place_buy_order() instead")
        try:
            limit_price = trigger_price + config.LIMIT_ORDER_BUFFER  # Trigger + 0.20
            
            logger.info(f"🟢 Placing STOP-LIMIT BUY order:")
            logger.info(f"   Trigger: ₹{trigger_price:.2f}")
            logger.info(f"   Limit: ₹{limit_price:.2f} (Trigger + ₹{config.LIMIT_ORDER_BUFFER})")
            
            order_id = self.kite.place_order(
                symbol=symbol,
                transaction_type="BUY",
                quantity=quantity,
                trigger_price=trigger_price,
                limit_price=limit_price,
                product=config.TRADE_TYPE,
                order_type="SL" if config.USE_LIMIT_ORDERS else "MARKET"
            )
            
            if order_id:
                logger.info(f"   ✓ Order placed: {order_id}")
                return order_id
            return None
            
        except Exception as e:
            logger.error(f"Error placing limit buy order: {e}")
            return None
    
    def place_limit_sell_order(self, symbol, quantity, trigger_price):
        """
        DEPRECATED - Use place_sell_order() instead
        CHANGE 1: Smart Limit Orders (SELL variant)
        """
        logger.warning("place_limit_sell_order() is deprecated - use place_sell_order() instead")
        try:
            limit_price = trigger_price - config.LIMIT_ORDER_BUFFER  # Trigger - 0.20
            
            logger.info(f"🔴 Placing STOP-LIMIT SELL order:")
            logger.info(f"   Trigger: ₹{trigger_price:.2f}")
            logger.info(f"   Limit: ₹{limit_price:.2f} (Trigger - ₹{config.LIMIT_ORDER_BUFFER})")
            
            order_id = self.kite.place_order(
                symbol=symbol,
                transaction_type="SELL",
                quantity=quantity,
                trigger_price=trigger_price,
                limit_price=limit_price,
                product=config.TRADE_TYPE,
                order_type="SL" if config.USE_LIMIT_ORDERS else "MARKET"
            )
            
            if order_id:
                logger.info(f"   ✓ Order placed: {order_id}")
                return order_id
            return None
            
        except Exception as e:
            logger.error(f"Error placing limit sell order: {e}")
            return None
    
    # PHASE 2: STRATEGY LOGIC
    
    def check_nifty_trend(self):
        """
        CHANGE 6: Index Trend Alignment (NIFTY Filter)
        Check if NIFTY is above/below its VWAP to determine bias
        Only take LONG signals if NIFTY > NIFTY_VWAP
        Only take SHORT signals if NIFTY < NIFTY_VWAP
        """
        try:
            # Get NIFTY current quote
            nifty_quote = self.kite.get_quote("NSE", "NIFTY 50")
            nifty_price = nifty_quote.get('last_price', 0)
            
            if nifty_price <= 0:
                logger.warning("Could not fetch NIFTY price, skipping filter")
                return "NEUTRAL"
            
            # Get NIFTY 15-min opening candle for VWAP
            now = get_ist_time()
            candle_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
            candle_end = now.replace(hour=9, minute=30, second=0, microsecond=0)
            
            try:
                # Try to get NIFTY instrument token or use direct API
                nifty_candles = self.kite.get_historical_data(
                    "NIFTY",  # May need proper token
                    candle_start,
                    candle_end,
                    interval="15minute"
                )
                
                if nifty_candles and len(nifty_candles) > 0:
                    candle = nifty_candles[0]
                    nifty_vwap = self.kite.calculate_vwap([candle])
                else:
                    # Fallback: use opening price as approximation
                    nifty_vwap = nifty_quote.get('ohlc', {}).get('open', nifty_price)
            except:
                nifty_vwap = nifty_quote.get('ohlc', {}).get('open', nifty_price)
            
            # Determine bias strength
            self.nifty_strength_pct = abs(nifty_price - nifty_vwap) / nifty_vwap * 100 if nifty_vwap else 0

            if self.nifty_strength_pct < config.NIFTY_STRONG_THRESHOLD_PCT:
                self.nifty_bias = "NEUTRAL"
                logger.info(
                    f"   ➖ NIFTY near VWAP ({nifty_price:.0f} ~ {nifty_vwap:.0f}) → NEUTRAL bias "
                    f"({self.nifty_strength_pct:.2f}%)"
                )
                return "NEUTRAL"

            # Determine bias
            if nifty_price > nifty_vwap:
                self.nifty_bias = "LONG"
                logger.info(
                    f"   📈 NIFTY > VWAP ({nifty_price:.0f} > {nifty_vwap:.0f}) → LONG bias "
                    f"({self.nifty_strength_pct:.2f}%)"
                )
                return "LONG"
            else:
                self.nifty_bias = "SHORT"
                logger.info(
                    f"   📉 NIFTY < VWAP ({nifty_price:.0f} < {nifty_vwap:.0f}) → SHORT bias "
                    f"({self.nifty_strength_pct:.2f}%)"
                )
                return "SHORT"
                
        except Exception as e:
            logger.warning(f"Error checking NIFTY trend: {e}, allowing both directions")
            self.nifty_bias = "NEUTRAL"
            return "NEUTRAL"
    
    def check_entry_window_and_rules(self):
        """
        CHANGE 4: Extended & Adaptive Window
        Determine if we're in PRIMARY (9:30-10:15) or SOFT (10:15-10:45) window
        """
        now = get_ist_time()
        minutes = now.hour * 100 + now.minute
        
        if config.PRIMARY_ENTRY_START <= minutes <= config.PRIMARY_ENTRY_END:
            self.entry_window_state = "PRIMARY"
            return "PRIMARY", True  # Can take any signal
        elif config.SOFT_CUTOFF_START <= minutes <= config.SOFT_CUTOFF_END:
            self.entry_window_state = "SOFT"
            return "SOFT", False  # Need additional confirmation (Volume 2x or ATR expanding)
        elif minutes > config.NO_ENTRY_AFTER:
            return "CLOSED", False
        else:
            return "NOT_OPEN", False
    
    def can_take_trade_2(self):
        """
        CHANGE 5: Smart Multi-Trade Logic
        Allow up to 2 trades/day with specific rules:
        - Trade 1 wins → Stop, keep profits
        - Trade 1 loses + before 10:45 AM → Allow Trade 2
        - Trade 2 loses → Stop, protect capital
        """
        if not config.ALLOW_RECOVERY_TRADE:
            return False

        if self.num_trades_today >= config.MAX_TRADES_PER_DAY_PORTFOLIO:
            return False
        
        now = get_ist_time()
        minutes = now.hour * 100 + now.minute
        
        # Check if we can still take recovery trade
        if minutes > config.RECOVERY_TRADE_TIMEOUT:
            logger.info("🛑 Recovery trade timeout (10:45 AM) - no more entries")
            return False
        
        # Allow Trade 2 only if Trade 1 lost
        if self.num_trades_today >= 1 and self.trade1_result == "LOSS":
            logger.info("🟢 Trade 1 lost - allowing recovery trade (Trade 2)")
            return True
        
        return False

    def is_nifty_bias_blocking(self, side):
        """Soft NIFTY bias filter: only block when strongly opposite."""
        if not config.USE_NIFTY_FILTER:
            return False

        if not config.USE_NIFTY_SOFT_BIAS:
            if side == "BUY" and self.nifty_bias != "LONG":
                return True
            if side == "SELL" and self.nifty_bias != "SHORT":
                return True
            return False

        if self.nifty_bias == "NEUTRAL":
            return False

        if self.nifty_strength_pct < config.NIFTY_STRONG_THRESHOLD_PCT:
            return False

        if side == "BUY" and self.nifty_bias == "SHORT":
            return True
        if side == "SELL" and self.nifty_bias == "LONG":
            return True
        return False
    
    # PHASE 3: RISK & EXIT MANAGEMENT
    
    def apply_stoploss_distance_factor(self, entry_price, sl_price, side):
        """
        Apply STOPLOSS_DISTANCE_FACTOR to tighten stop loss
        Default factor = 0.5 means SL moves 50% closer to entry
        
        Example: Entry=100, Original SL=90 (risk=10)
                 With factor=0.5: New SL=95 (risk=5, which is 50% of original)
        """
        factor = getattr(config, 'STOPLOSS_DISTANCE_FACTOR', 0.5)
        if factor >= 1.0:
            return sl_price  # No change if factor >= 1.0
        
        risk_distance = abs(entry_price - sl_price)
        new_risk_distance = risk_distance * factor
        
        if side == "BUY":
            adjusted_sl = entry_price - new_risk_distance
        else:  # SELL
            adjusted_sl = entry_price + new_risk_distance
        
        logger.info(f"   Applying STOPLOSS_DISTANCE_FACTOR ({factor}): Original SL ₹{sl_price:.2f} -> Adjusted SL ₹{adjusted_sl:.2f}")
        return adjusted_sl

    def calculate_dynamic_sl(self, side, vwap, h_5, l_5):
        """
        CHANGE 7: Dynamic Stop Loss
        Use min(VWAP, Candle Low - buffer) for LONG (tighter SL)
        Use max(VWAP, Candle High + buffer) for SHORT (tighter SL)
        
        Logic: Uses structural candle level with buffer to avoid wicks
        Picks tighter (safer) of candle or VWAP level
        """
        try:
            if side == "BUY":
                # For LONG trades: Use lower of (VWAP) or (Candle Low - small buffer)
                buffer = getattr(config, 'DYNAMIC_SL_BUFFER', 0.20)
                structural_sl = l_5 - buffer  # Slightly below candle low
                dynamic_sl = min(structural_sl, vwap)  # Use whichever is lower (tighter)
                logger.info(f"   Dynamic SL (LONG): min(VWAP:{vwap:.2f}, Low-Buffer:{structural_sl:.2f}) = {dynamic_sl:.2f}")
                return dynamic_sl
            else:  # SELL
                # For SHORT trades: Use higher of (VWAP) or (Candle High + small buffer)
                buffer = getattr(config, 'DYNAMIC_SL_BUFFER', 0.20)
                structural_sl = h_5 + buffer  # Slightly above candle high
                dynamic_sl = max(structural_sl, vwap)  # Use whichever is higher (tighter)
                logger.info(f"   Dynamic SL (SHORT): max(VWAP:{vwap:.2f}, High+Buffer:{structural_sl:.2f}) = {dynamic_sl:.2f}")
                return dynamic_sl
        except Exception as e:
            logger.error(f"Error in calculate_dynamic_sl: {e}, using VWAP")
            return vwap
    
    def manage_partial_exit(self, current_price, entry_price, risk_amount, side):
        """
        CHANGE 8: Optimized Partial Booking
        At 1R: Move SL to breakeven (trade is now FREE)
        At 2R: Book 75% of position
        At 3R+: Trail SL on 5-min candle low, let winner run
        """
        if side == "BUY":
            profit = current_price - entry_price
        else:  # SELL
            profit = entry_price - current_price
        
        if risk_amount <= 0:
            return
        
        risk_reward_ratio = profit / risk_amount
        
        # At 2R: Close 75%
        if risk_reward_ratio >= 2.0 and not self.partial_booked_75pct:
            logger.info(f"💰 AT 2R PROFIT - Booking 75% of position")
            close_qty = int(self.entry_quantity * 0.75)
            self.place_sell_order(symbol=self.traded_symbol, quantity=close_qty, price=current_price)
            self.partial_booked_75pct = True
            self.remaining_quantity = self.entry_quantity - close_qty
            logger.info(f"   Closed: {close_qty} shares")
            logger.info(f"   Remaining: {self.remaining_quantity} shares (for trailing)")
        
        # At 1R: Move SL to breakeven
        elif risk_reward_ratio >= 1.0 and not self.sl_moved_to_breakeven:
            logger.info(f"✓ AT 1R PROFIT - Trade is now FREE! Moving SL to breakeven")
            self.sl_price = self.entry_price
            # Update the SL order on Kite
            logger.info(f"   New SL: ₹{self.entry_price:.2f} (Breakeven)")
            self.sl_moved_to_breakeven = True
    
    def check_daily_loss_limit(self):
        """
        CHANGE 9: Daily Loss Limit
        Hard stop at -2% of starting capital
        Auto-closes all positions and shuts down bot
        """
        if not config.USE_DAILY_LOSS_LIMIT:
            return True
        
        # Calculate daily P&L
        self.daily_pnl = sum([t.get('pnl', 0) for t in self.trades_today])
        actual_balance = self.starting_balance or self.account_balance or 1  # Avoid division by zero
        self.daily_loss_pct = self.daily_pnl / actual_balance if actual_balance > 0 else 0
        
        logger.info(f"📊 Daily P&L: ₹{self.daily_pnl:.2f} ({self.daily_loss_pct*100:.2f}%)")
        
        if self.daily_loss_pct <= -config.DAILY_LOSS_LIMIT_PCT:
            logger.error(f"🛑 DAILY LOSS LIMIT HIT: {self.daily_loss_pct*100:.2f}% loss")
            logger.error(f"   Limit: {-config.DAILY_LOSS_LIMIT_PCT*100:.2f}%")
            logger.error(f"🆘 AUTO-SHUTTING DOWN BOT TO PROTECT CAPITAL")
            
            # Close all positions
            self.close_all_positions()
            
            # Stop trading
            if config.AUTO_SHUTDOWN_ON_LOSS_LIMIT:
                self.should_stop = True
            
            return False  # Stop taking new trades
        
        return True  # Continue trading
    
    def close_all_positions(self):
        """Close all open positions (emergency shutdown)"""
        try:
            logger.info("🆘 Closing ALL OPEN POSITIONS - Emergency shutdown")
            # Get all open positions
            positions = self.kite.get_positions()
            if not positions:
                logger.info("No open positions to close")
                return True
            
            for position in positions:
                symbol = position.get('tradingsymbol')
                quantity = position.get('quantity')
                if quantity and quantity > 0:
                    logger.info(f"   Closing {quantity} shares of {symbol}")
                    try:
                        self.kite.place_order(
                            symbol=symbol,
                            transaction_type="SELL",
                            quantity=int(quantity),
                            order_type="MARKET",
                            product=config.TRADE_TYPE
                        )
                        logger.info(f"   ✓ Close order placed for {symbol}")
                    except Exception as e:
                        logger.error(f"   ✗ Error closing {symbol}: {e}")
            return True
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
            return False
    
    def stop(self):
        """Signal the bot to stop gracefully"""
        logger.info("🛑 Stop signal received - bot will shutdown gracefully...")
        self.should_stop = True
    
    def run(self):
        """Continuous bot - runs forever, trading every day automatically"""
        try:
            # Validate critical config values at startup
            critical_configs = [
                'STARTING_CAPITAL', 'LEVERAGE', 'BUFFER_AMOUNT',
                'SYMBOLS_TO_MONITOR', 'TRADE_TYPE', 'PROFIT_TARGET_TYPE',
                'PROFIT_TARGET_RATIO'
            ]
            missing_configs = []
            for key in critical_configs:
                if not hasattr(config, key):
                    missing_configs.append(key)
            
            if missing_configs:
                error_msg = f"❌ Missing critical config values: {', '.join(missing_configs)}"
                logger.error(error_msg)
                self.log_to_db(f"ERROR: {error_msg}")
                return False
            
            self.log_to_db("BOT SESSION STARTING - Checking time and market conditions")
            self.log_section("🚀 TRADING BOT - 24/7 CONTINUOUS MODE")
            logger.info("🔄 Bot will run continuously and trade every day")
            logger.info("⏰ Trading window: 9:30-10:45 AM IST (Entry)")
            logger.info("📊 Auto-exit: Target/Stoploss or 3:25 PM")
            logger.info("🛌 After trading: Waits for next day automatically")
            logger.info("")
            
            # Ensure attributes exist with safe defaults
            if not hasattr(self, 'starting_balance') or self.starting_balance is None:
                self.starting_balance = 0
            if not hasattr(self, 'account_balance') or self.account_balance is None:
                self.account_balance = 0
            if not hasattr(self, 'current_balance'):
                self.current_balance = 0
            
            # Fetch initial account balance
            self.log_to_db("Fetching account balance...")
            logger.info("💰 AVAILABLE FUNDS (BEFORE TRADING):")
            self.starting_balance = self.get_account_balance()
            self.log_to_db(f"Starting balance obtained: ₹{self.starting_balance:,.2f}")
            self.account_balance = self.starting_balance
            self.current_balance = self.starting_balance
            
            if self.starting_balance <= 0:
                self.log_to_db("ERROR: No available balance in account. Cannot start bot.")
                logger.error("❌ No available balance in account. Cannot start bot.")
                return False
            
            self.log_to_db("Account initialization successful - proceeding to trading loop")
        except Exception as e:
            logger.error(f"❌ Error in bot initialization: {e}")
            return False
        
        # Display portfolio with effective capital calculation
        self.effective_capital = self.starting_balance * self.leverage
        logger.info(f"   Actual Balance: ₹{self.starting_balance:,.2f}")
        logger.info(f"   Leverage: {self.leverage}x")
        logger.info(f"   Effective Capital Available: ₹{self.effective_capital:,.2f}")
        logger.info(f"   Trade Type: {config.TRADE_TYPE_DISPLAY} (MIS) - Intraday - Must square off by market close")
        logger.info("")
        
        # Daily trading loop - runs until stop signal
        while not self.should_stop:
            try:
                # Check stop flag at start of iteration
                if self.should_stop:
                    logger.info("🛑 Stop requested - exiting main loop")
                    break
                
                # Check if we're within valid trading time
                now = get_ist_time()
                self.log_to_db(f"Main loop iteration - Current time: {now.strftime('%H:%M:%S IST')}")
                
                # Extended entry window: PRIMARY (9:30-10:15 AM) + SOFT (10:15-10:45 AM)
                if now.hour > 10 or (now.hour == 10 and now.minute >= 45):
                    self.log_to_db(f"Entry window CLOSED check: hour={now.hour}, minute={now.minute}")
                    if now.hour < 15 or (now.hour == 15 and now.minute < 30):
                        logger.warning("⚠️  Entry window already closed for today (9:30-10:45 AM)")
                        logger.info("📅 Bot will wait until next trading day (9:15 AM)")
                        logger.info("💡 Bot is in STANDBY mode - will auto-resume tomorrow")
                        # Wait for next day's market open
                        if not self.wait_until_next_day_market():
                            logger.error("Error waiting for next market day")
                            time.sleep(3600)  # Wait 1 hour and retry
                            continue
                    else:
                        logger.info("📅 Market closed. Waiting for next trading day...")
                        if not self.wait_until_next_day_market():
                            logger.error("Error waiting for next market day")
                            time.sleep(3600)  # Wait 1 hour and retry
                            continue
                
                # Execute today's trading session
                self.log_to_db("STARTING TODAY'S TRADING SESSION")
                logger.info("=" * 60)
                logger.info(f"📅 TRADING SESSION: {get_ist_time().strftime('%A, %B %d, %Y')}")
                logger.info("=" * 60)
                
                session_success = self.run_daily_trading_session()
                
                if session_success:
                    logger.info("")
                    logger.info("✅ Today's trading session completed")
                else:
                    logger.warning("⚠️  Today's trading session had issues")
                
                logger.info("🛌 Entering STANDBY mode until next trading day...")
                logger.info("")
                
                # Wait for next trading day (check stop flag periodically)
                if not self.wait_until_next_day_market():
                    logger.error("Error waiting for next market day")
                    # Check stop flag before long sleep
                    if self.should_stop:
                        break
                    time.sleep(3600)  # Wait 1 hour and retry
                    continue
                
                # Check stop flag before starting new day
                if self.should_stop:
                    logger.info("🛑 Stop requested - skipping new trading day")
                    break
                
                # Reset daily stats for new day
                self.trades = []
                # Refresh account balance for new day
                self.starting_balance = self.get_account_balance()
                self.account_balance = self.starting_balance
                self.current_balance = self.starting_balance
                logger.info("")
                logger.info("🔄 New trading day - Bot ready!")
                logger.info("")
                
            except Exception as e:
                logger.error(f"❌ Error in daily loop: {str(e)}")
                # Check stop flag before retry
                if self.should_stop:
                    break
                logger.info("⏳ Waiting 5 minutes before retry...")
                time.sleep(300)  # Wait 5 minutes on error
                continue
        
        # Bot stopped gracefully
        logger.info("")
        logger.info("="*60)
        logger.info("🛑 BOT STOPPED SUCCESSFULLY")
        logger.info("="*60)
