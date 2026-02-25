"""Trading service - handles bot logic separately from API"""
import threading
import logging
from datetime import datetime, date, timedelta
import pyotp
from models import db, Trade, DailyStats, BotLog

logger = logging.getLogger(__name__)

def get_ist_time():
    """Get current time in IST by converting UTC to IST (+5:30 hours)"""
    utc_now = datetime.utcnow()
    ist_time = utc_now + timedelta(hours=5, minutes=30)
    return ist_time


class TradingService:
    """Manages trading bot execution and state"""
    
    def __init__(self, app):
        self.app = app
        self.bot_threads = {}  # user_id -> thread
        self.bot_states = {}   # user_id -> bot state dict
        self.bots = {}         # user_id -> bot instance
    
    def start_bot(self, user):
        """Start bot for a user"""
        logger.info(f"Attempting to start bot for user {user.id}")
        # Clean up any existing stopped thread first
        if user.id in self.bot_threads:
            if not self.bot_threads[user.id].is_alive():
                logger.info(f'Cleaning up previous bot thread for user {user.id}')
                del self.bot_threads[user.id]
                if user.id in self.bots:
                    del self.bots[user.id]
            else:
                logger.error('Bot already running for user {user.id}')
                raise Exception('Bot already running')
        
        # Create bot thread with credentials as separate args
        logger.info(f"Creating bot thread for user {user.id}")
        thread = threading.Thread(
            target=self._run_bot,
            args=(user.id, user.kite_api_key, user.kite_access_token),
            daemon=True
        )
        logger.info(f"Thread for user {user.id} created and starting...")
        thread.start()
        logger.info(f"Thread for user {user.id} started successfully")
        
        self.bot_threads[user.id] = thread
        self.bot_states[user.id] = {
            'status': 'RUNNING',
            'startTime': get_ist_time().isoformat(),
            'trades_today': 0,
            'pnl_today': 0,
            'current_position': None,
        }
        
        logger.info(f'Bot started for user {user.id}')
    
    def stop_bot(self, user_id):
        """Stop bot for a user"""
        try:
            # Call stop method on bot instance if it exists
            if user_id in self.bots:
                logger.info(f'Sending stop signal to bot for user {user_id}')
                self.bots[user_id].stop()
            
            # Update state
            if user_id in self.bot_states:
                self.bot_states[user_id]['status'] = 'STOPPED'
            
            # Wait for thread to finish gracefully (increased timeout)
            if user_id in self.bot_threads:
                thread = self.bot_threads[user_id]
                logger.info(f'Waiting for bot thread to stop (max 10 seconds)...')
                thread.join(timeout=10)  # Wait up to 10 seconds for graceful shutdown
                
                # Clean up thread reference
                if not thread.is_alive():
                    del self.bot_threads[user_id]
                    logger.info(f'✓ Bot thread stopped cleanly for user {user_id}')
                else:
                    # Thread still alive after timeout - force cleanup
                    logger.warning(f'Bot thread did not stop in time for user {user_id}, forcing cleanup')
                    del self.bot_threads[user_id]
            
            # Clean up bot instance reference
            if user_id in self.bots:
                del self.bots[user_id]
            
            logger.info(f'Bot stop completed for user {user_id}')
            
        except Exception as e:
            logger.error(f'Error stopping bot for user {user_id}: {str(e)}')
    
    def get_bot_status(self, user_id):
        """Get current bot status and live data"""
        # Check if thread died unexpectedly and clean up
        if user_id in self.bot_threads:
            if not self.bot_threads[user_id].is_alive():
                logger.warning(f'Bot thread died for user {user_id}, cleaning up')
                del self.bot_threads[user_id]
                if user_id in self.bots:
                    del self.bots[user_id]
                if user_id in self.bot_states:
                    if self.bot_states[user_id]['status'] not in ['STOPPED', 'ERROR']:
                        self.bot_states[user_id]['status'] = 'ERROR'
        
        if user_id not in self.bot_states:
            return {
                'status': 'NOT_RUNNING',
                'trades_today': 0,
                'pnl_today': 0,
                'last_trade': None,
                'current_position': None,
                'current_time': get_ist_time().isoformat(),
            }
        
        state = self.bot_states[user_id]
        
        # Get today's stats
        today_stats = DailyStats.query.filter_by(
            user_id=user_id,
            stats_date=date.today()
        ).first()
        
        return {
            'status': state.get('status', 'RUNNING'),
            'startTime': state.get('startTime'),
            'trades_today': state.get('trades_today', 0),
            'pnl_today': state.get('pnl_today', 0),
            'current_position': state.get('current_position'),
            'daily_stats': today_stats.to_dict() if today_stats else None,
            'current_time': get_ist_time().isoformat(),
        }
    
    def _run_bot(self, user_id, api_key, access_token):
        """Main bot trading loop (runs in separate thread)"""
        logger.info(f"_run_bot started for user {user_id}")
        with self.app.app_context():
            try:
                logger.info(f"Initializing trading bot for user {user_id}")
                logger.info(f"API Key: {api_key}, Access Token: {access_token}")
                
                # Initialize daily stats if not exists
                today = get_ist_time().date()
                daily_stats = DailyStats.query.filter_by(
                    user_id=user_id,
                    stats_date=today
                ).first()
                
                if not daily_stats:
                    daily_stats = DailyStats(
                        user_id=user_id,
                        stats_date=today,
                        bot_active=True,
                        market_open_time=get_ist_time()
                    )
                    db.session.add(daily_stats)
                    db.session.commit()
                
                logger.info(f"Daily stats initialized for user {user_id}")
                
                BotLog.create_log(user_id, 'BOT', 'Daily bot session started', 'INFO')
                
                # Import and initialize Kite bot
                from app_files.bot_kite import KiteApp
                from app_files.kite_service import KiteService
                
                # Initialize Kite service with user credentials
                kite_service = KiteApp(api_key, access_token, user_id)
                
                # Store reference to bot instance
                self.bots[user_id] = kite_service
                self.bot_states[user_id]['status'] = 'READY'
                
                logger.info(f"Starting bot run for user {user_id}")
                # Run bot - it handles its own main trading loop
                kite_service.run()
                
                # After bot completes, update daily stats
                daily_stats.bot_active = False
                daily_stats.market_close_time = get_ist_time()
                db.session.commit()
                
                BotLog.create_log(user_id, 'BOT', 'Daily bot session ended', 'INFO')
                
                self.bot_states[user_id]['status'] = 'STOPPED'
                logger.info(f"Bot stopped for user {user_id}")
                
            except Exception as e:
                logger.error(f'Bot error for user {user_id}: {str(e)}')
                BotLog.create_log(user_id, 'BOT', f'Bot error: {str(e)}', 'ERROR')
                self.bot_states[user_id]['status'] = 'ERROR'
    
    def record_trade(self, user_id, trade_data):
        """Record a completed trade"""
        with self.app.app_context():
            try:
                trade = Trade(
                    user_id=user_id,
                    trade_date=get_ist_time().date(),
                    **trade_data
                )
                db.session.add(trade)
                
                # Update daily stats
                daily_stats = DailyStats.query.filter_by(
                    user_id=user_id,
                    stats_date=get_ist_time().date()
                ).first()
                
                if daily_stats:
                    daily_stats.total_trades += 1
                    if trade.pnl and trade.pnl > 0:
                        daily_stats.winning_trades += 1
                    elif trade.pnl and trade.pnl < 0:
                        daily_stats.losing_trades += 1
                    
                    daily_stats.total_pnl += trade.pnl or 0
                    
                    if daily_stats.total_trades > 0:
                        daily_stats.win_rate = (daily_stats.winning_trades / daily_stats.total_trades) * 100
                    
                    if daily_stats.winning_trades > 0:
                        daily_stats.avg_profit_per_trade = (
                            sum((t.pnl for t in Trade.query.filter_by(
                                user_id=user_id,
                                trade_date=get_ist_time().date()
                            ).all() if t.pnl and t.pnl > 0), 0) / daily_stats.winning_trades
                        )
                
                # Update bot state
                if user_id in self.bot_states:
                    self.bot_states[user_id]['trades_today'] = daily_stats.total_trades if daily_stats else 0
                    self.bot_states[user_id]['pnl_today'] = daily_stats.total_pnl if daily_stats else 0
                
                db.session.commit()
                BotLog.create_log(user_id, 'TRADE', f"Trade recorded: {trade.side} {trade.quantity}@{trade.entry_price}", 'INFO', trade.id)
            
            except Exception as e:
                logger.error(f'Error recording trade: {str(e)}')
                db.session.rollback()
