"""Database models for trading bot"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

class User(db.Model):
    """User account with trading configuration"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Trading config
    starting_capital = db.Column(db.Float, default=20000)
    leverage = db.Column(db.Float, default=5.0)
    trade_symbol = db.Column(db.String(50), default="NSE:TATASTEEL")
    buffer_amount = db.Column(db.Float, default=0.10)
    profit_target_type = db.Column(db.String(20), default="ratio")  # ratio, percent, fixed
    profit_target_ratio = db.Column(db.Float, default=2.0)
    profit_target_percent = db.Column(db.Float, default=1.0)
    profit_target_fixed = db.Column(db.Float, default=300)
    
    # Kite API credentials (encrypted should be used in production)
    kite_api_key = db.Column(db.String(100), default='')
    kite_access_token = db.Column(db.String(255), default='')  # Obtained after OAuth login
    zerodha_user_id = db.Column(db.String(100), default='')  # User ID for API calls
    
    # Bot status
    bot_active = db.Column(db.Boolean, default=False)
    bot_last_run = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    trades = db.relationship('Trade', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    sessions = db.relationship('Session', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'starting_capital': self.starting_capital,
            'leverage': self.leverage,
            'trade_symbol': self.trade_symbol,
            'bot_active': self.bot_active,
            'bot_last_run': self.bot_last_run.isoformat() if self.bot_last_run else None,
        }


class Trade(db.Model):
    """Individual trade record"""
    __tablename__ = 'trades'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    trade_date = db.Column(db.Date, nullable=False, index=True)
    entry_time = db.Column(db.DateTime, nullable=False)
    exit_time = db.Column(db.DateTime, nullable=True)
    
    side = db.Column(db.String(1), nullable=False)  # B for buy, S for sell
    symbol = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    entry_price = db.Column(db.Float, nullable=False)
    exit_price = db.Column(db.Float, nullable=True)
    
    stoploss_price = db.Column(db.Float, nullable=False)
    target_price = db.Column(db.Float, nullable=False)
    
    pnl = db.Column(db.Float, nullable=True)  # Profit/Loss in rupees
    pnl_percent = db.Column(db.Float, nullable=True)  # Profit/Loss percentage
    status = db.Column(db.String(20), default='OPEN')  # OPEN, CLOSED, CANCELLED
    
    entry_order_id = db.Column(db.String(50), nullable=True)
    exit_order_id = db.Column(db.String(50), nullable=True)
    stoploss_order_id = db.Column(db.String(50), nullable=True)
    
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'trade_date': self.trade_date.isoformat(),
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'side': self.side,
            'symbol': self.symbol,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'stoploss_price': self.stoploss_price,
            'target_price': self.target_price,
            'pnl': self.pnl,
            'pnl_percent': self.pnl_percent,
            'status': self.status,
        }


class DailyStats(db.Model):
    """Daily trading statistics and summary"""
    __tablename__ = 'daily_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stats_date = db.Column(db.Date, nullable=False, unique=True, index=True)
    
    # Daily metrics
    total_trades = db.Column(db.Integer, default=0)
    winning_trades = db.Column(db.Integer, default=0)
    losing_trades = db.Column(db.Integer, default=0)
    cancelled_trades = db.Column(db.Integer, default=0)
    
    win_rate = db.Column(db.Float, default=0.0)  # percentage
    total_pnl = db.Column(db.Float, default=0.0)
    avg_profit_per_trade = db.Column(db.Float, nullable=True)
    largest_win = db.Column(db.Float, nullable=True)
    largest_loss = db.Column(db.Float, nullable=True)
    
    # Status
    market_open_time = db.Column(db.DateTime, nullable=True)
    market_close_time = db.Column(db.DateTime, nullable=True)
    bot_active = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'stats_date': self.stats_date.isoformat(),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'cancelled_trades': self.cancelled_trades,
            'win_rate': self.win_rate,
            'total_pnl': self.total_pnl,
            'avg_profit_per_trade': self.avg_profit_per_trade,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
        }


class Session(db.Model):
    """Session tracking for API authentication"""
    __tablename__ = 'sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    session_token = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    is_active = db.Column(db.Boolean, default=True)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'is_active': self.is_active,
        }


class BotLog(db.Model):
    """Bot activity and event logs"""
    __tablename__ = 'bot_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    log_type = db.Column(db.String(50), nullable=False)  # LOGIN, TRADE, ERROR, INFO, WARNING
    message = db.Column(db.Text, nullable=False)
    log_level = db.Column(db.String(20), default='INFO')  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'), nullable=True)
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'log_type': self.log_type,
            'message': self.message,
            'log_level': self.log_level,
            'timestamp': self.timestamp.isoformat(),
        }
    
    @staticmethod
    def create_log(user_id, log_type, message, log_level='INFO', trade_id=None):
        """Helper method to create and save a log entry"""
        log = BotLog(
            user_id=user_id,
            log_type=log_type,
            message=message,
            log_level=log_level,
            trade_id=trade_id
        )
        db.session.add(log)
        db.session.commit()
        return log
