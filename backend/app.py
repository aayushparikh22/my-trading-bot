"""Flask backend API for trading bot"""
import os
import sys
from datetime import datetime, timedelta
from functools import wraps
import jwt
import json
import re
from collections import defaultdict
from dotenv import load_dotenv

# Add parent directory to path so we can import app_files package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, request, jsonify
from flask_cors import CORS
from kiteconnect import KiteConnect
from models import db, User, Trade, DailyStats, Session, BotLog
from trading_service import TradingService


CANCELABLE_ORDER_STATUSES = {
    'OPEN',
    'TRIGGER PENDING',
    'PUT ORDER REQ RECEIVED',
    'VALIDATION PENDING',
    'MODIFY VALIDATION PENDING',
    'MODIFY PENDING',
    'AMO REQ RECEIVED',
}


def extract_target_order_id(notes):
    """Extract target order ID from trade notes"""
    if not notes:
        return None
    match = re.search(r'TARGET_ORDER_ID:([^|\s]+)', notes)
    return match.group(1) if match else None


def append_target_order_id(notes, target_order_id):
    """Append target order ID marker to notes"""
    base = notes or ''
    return f"{base} | TARGET_ORDER_ID:{target_order_id}"


def cancel_order_if_open(kite, order_id, orders_by_id=None):
    """Cancel order only if currently open/trigger-pending"""
    if not order_id:
        return False

    order = (orders_by_id or {}).get(order_id)
    if order:
        status = (order.get('status') or '').upper()
        if status not in CANCELABLE_ORDER_STATUSES:
            return False

    return kite.cancel_order(order_id)


def reconcile_open_trades_for_user(current_user):
    """If SL/TP exit got filled, close trade and cancel opposite exit order."""
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return

    from app_files.kite_service import KiteService

    kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
    orders = kite.get_orders() or []
    orders_by_id = {
        o.get('order_id'): o
        for o in orders
        if o.get('order_id')
    }

    open_trades = Trade.query.filter_by(user_id=current_user.id, status='OPEN').all()

    for trade in open_trades:
        sl_order_id = trade.stoploss_order_id
        target_order_id = extract_target_order_id(trade.notes)

        sl_order = orders_by_id.get(sl_order_id) if sl_order_id else None
        tp_order = orders_by_id.get(target_order_id) if target_order_id else None

        exit_order = None
        exit_reason = None
        opposite_order_id = None

        if sl_order and (sl_order.get('status') or '').upper() == 'COMPLETE':
            exit_order = sl_order
            exit_reason = 'STOPLOSS'
            opposite_order_id = target_order_id
        elif tp_order and (tp_order.get('status') or '').upper() == 'COMPLETE':
            exit_order = tp_order
            exit_reason = 'TARGET'
            opposite_order_id = sl_order_id

        if not exit_order:
            continue

        fill_price = exit_order.get('average_price') or exit_order.get('price') or 0
        if not fill_price or fill_price <= 0:
            fill_price = trade.stoploss_price if exit_reason == 'STOPLOSS' else trade.target_price

        trade.status = 'CLOSED'
        trade.exit_time = get_ist_time()
        trade.exit_price = float(fill_price)
        trade.exit_order_id = exit_order.get('order_id')

        if trade.side == 'B':
            trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
            trade.pnl_percent = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100 if trade.entry_price else 0
        else:
            trade.pnl = (trade.entry_price - trade.exit_price) * trade.quantity
            trade.pnl_percent = ((trade.entry_price - trade.exit_price) / trade.entry_price) * 100 if trade.entry_price else 0

        cancelled = cancel_order_if_open(kite, opposite_order_id, orders_by_id)

        db.session.add(BotLog(
            user_id=current_user.id,
            log_level='INFO',
            log_type='TRADE',
            trade_id=trade.id,
            message=(
                f"{exit_reason} exit completed for {trade.symbol} @ ₹{trade.exit_price:.2f} "
                f"| Exit Order: {trade.exit_order_id} | Opposite order cancelled: {cancelled}"
            )
        ))

    db.session.commit()

# Get IST time (UTC + 5:30 hours)
def get_ist_time():
    utc_now = datetime.utcnow()
    return utc_now + timedelta(hours=5, minutes=30)

# Global cache for opening range triggers (LOCKED at 9:30 AM)
TRIGGER_CACHE = {}  # {symbol: {'buy': X, 'sell': Y, 'locked_at': datetime, 'high': H, 'low': L}}
TRIGGER_CACHE_LOCK_TIME = None  # When triggers were locked (9:30 AM)
TRIGGER_CACHE_FILE = 'trigger_cache.json'  # File to persist triggers across restarts

def save_trigger_cache_to_file():
    """Save trigger cache to file for persistence across restarts"""
    try:
        cache_data = {
            'lock_time': TRIGGER_CACHE_LOCK_TIME.isoformat() if TRIGGER_CACHE_LOCK_TIME else None,
            'triggers': {}
        }
        
        for symbol, data in TRIGGER_CACHE.items():
            cache_data['triggers'][symbol] = {
                'buy': data['buy'],
                'sell': data['sell'],
                'high': data['high'],
                'low': data['low'],
                'locked_at': data['locked_at'].isoformat() if isinstance(data['locked_at'], datetime) else data['locked_at']
            }
        
        with open(TRIGGER_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        print(f"[OK] Trigger cache saved to {TRIGGER_CACHE_FILE}")
        return True
    except Exception as e:
        print(f"[WARN] Error saving trigger cache: {e}")
        return False

def load_trigger_cache_from_file():
    """Load trigger cache from file if it exists and is from today"""
    global TRIGGER_CACHE, TRIGGER_CACHE_LOCK_TIME
    
    try:
        if not os.path.exists(TRIGGER_CACHE_FILE):
            print("[INFO] No trigger cache file found")
            return False
        
        with open(TRIGGER_CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
        
        if not cache_data.get('lock_time'):
            print("[WARN] Cache file has no lock time")
            return False
        
        lock_time = datetime.fromisoformat(cache_data['lock_time'])
        now = get_ist_time()
        
        # Only load if cache is from today
        if lock_time.date() != now.date():
            print(f"[INFO] Cache file is from {lock_time.date()}, not loading (today is {now.date()})")
            return False
        
        # Load triggers into memory
        TRIGGER_CACHE_LOCK_TIME = lock_time
        for symbol, data in cache_data.get('triggers', {}).items():
            TRIGGER_CACHE[symbol] = {
                'buy': data['buy'],
                'sell': data['sell'],
                'high': data['high'],
                'low': data['low'],
                'locked_at': datetime.fromisoformat(data['locked_at'])
            }
        
        print(f"[OK] Loaded {len(TRIGGER_CACHE)} triggers from cache file (locked at {lock_time.strftime('%H:%M:%S')})")
        return True
        
    except Exception as e:
        print(f"[WARN] Error loading trigger cache: {e}")
        return False

def get_cached_triggers(symbol):
    """Get cached triggers if they exist and were locked today"""
    global TRIGGER_CACHE_LOCK_TIME
    now = get_ist_time()
    
    # Check if cache is from TODAY
    if TRIGGER_CACHE_LOCK_TIME and symbol in TRIGGER_CACHE:
        if TRIGGER_CACHE_LOCK_TIME.date() == now.date():
            # Cache is from today - use it (locked once, never recalculate)
            return TRIGGER_CACHE[symbol]
    
    return None

def cache_triggers(symbol, buy_trigger, sell_trigger, high, low):
    """Cache triggers when they're calculated from opening range"""
    global TRIGGER_CACHE, TRIGGER_CACHE_LOCK_TIME
    now = get_ist_time()
    
    # Cache triggers anytime during trading hours (9:15 AM - 3:30 PM)
    # if they come from the opening range (9:15-9:30 AM candle)
    if now.hour >= 9 and now.hour <= 15:
        # Only cache once per day (check if today's cache already exists)
        if not TRIGGER_CACHE_LOCK_TIME or TRIGGER_CACHE_LOCK_TIME.date() != now.date():
            TRIGGER_CACHE[symbol] = {
                'buy': buy_trigger,
                'sell': sell_trigger,
                'high': high,
                'low': low,
                'locked_at': now
            }
            if TRIGGER_CACHE_LOCK_TIME is None or TRIGGER_CACHE_LOCK_TIME.date() != now.date():
                TRIGGER_CACHE_LOCK_TIME = now
            # Save to file for persistence
            save_trigger_cache_to_file()
            return True
        else:
            # Already cached today
            if symbol not in TRIGGER_CACHE:
                TRIGGER_CACHE[symbol] = {
                    'buy': buy_trigger,
                    'sell': sell_trigger,
                    'high': high,
                    'low': low,
                    'locked_at': TRIGGER_CACHE_LOCK_TIME  # Use original lock time
                }
                # Save to file when new symbol added
                save_trigger_cache_to_file()
            return True
    
    return False

def calculate_atr_buffer_for_symbol(kite, exchange, symbol):
    """
    Calculate dynamic ATR-based buffer for a symbol (matching bot_kite.py logic)
    Uses ATR_PERIOD and ATR_TIMEFRAME from config
    Returns: buffer amount in ₹ or fallback BUFFER_AMOUNT if ATR calculation fails
    """
    try:
        from app_files import config
        
        if not config.USE_DYNAMIC_ATR_BUFFER:
            return config.BUFFER_AMOUNT
        
        now = get_ist_time()
        timeframe = getattr(config, "ATR_TIMEFRAME", "5minute")
        period = getattr(config, "ATR_PERIOD", 14)
        atr_multiplier = getattr(config, "ATR_MULTIPLIER", 0.7)
        
        # Parse timeframe to get minutes per candle
        minutes_per_candle = 5
        if timeframe.endswith("minute"):
            try:
                minutes_per_candle = int(timeframe.replace("minute", ""))
            except ValueError:
                minutes_per_candle = 5
        
        # Calculate lookback period
        lookback_minutes = (period + 2) * minutes_per_candle
        start_time = now - timedelta(minutes=lookback_minutes)
        
        # Fetch historical candles
        candles = kite.get_historical_data(
            exchange, symbol,
            start_time,
            now,
            interval=timeframe
        )
        
        if not candles or len(candles) < period + 1:
            return config.BUFFER_AMOUNT
        
        # Calculate True Range values
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
        
        # Calculate ATR (average of last 'period' True Range values)
        if len(tr_values) >= period:
            atr_value = sum(tr_values[-period:]) / period
            buffer = atr_multiplier * atr_value
            return buffer
        
        return config.BUFFER_AMOUNT
        
    except Exception as e:
        # Fallback to fixed buffer if ATR calculation fails
        from app_files import config
        return config.BUFFER_AMOUNT

# Initialize Flask app
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
app = Flask(__name__)

# Configuration
# Use SQLite for local development, PostgreSQL for production
db_uri = os.getenv('DATABASE_URL')
if not db_uri:
    # Default to SQLite in app directory
    db_path = os.path.join(os.path.dirname(__file__), '..', 'tradingbot.db')
    db_uri = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JWT_EXPIRATION_HOURS'] = int(os.getenv('JWT_EXPIRATION_HOURS', 24))

# Initialize extensions
db.init_app(app)
CORS(app)

# Initialize trading service
trading_service = TradingService(app)

# ===== Default User Setup =====

def get_default_user():
    """Get or create default user"""
    user = User.query.filter_by(email='default@tradingbot.local').first()
    if not user:
        user = User(
            email='default@tradingbot.local',
            starting_capital=20000,
            leverage=5.0,
            trade_symbol='NSE:TATASTEEL',
            buffer_amount=0.10,
            profit_target_type='ratio',
            profit_target_ratio=2.0,
            profit_target_percent=1.0,
            profit_target_fixed=300,
        )
        user.set_password('default')
        db.session.add(user)
        db.session.commit()
    
    env_api_key = os.getenv('KITE_API_KEY', '').strip()
    env_access_token = os.getenv('KITE_ACCESS_TOKEN', '').strip()
    env_user_id = os.getenv('KITE_USER_ID', '').strip()
    update_required = False
    if env_api_key and env_api_key != user.kite_api_key:
        user.kite_api_key = env_api_key
        update_required = True
    if env_access_token and env_access_token != user.kite_access_token:
        user.kite_access_token = env_access_token
        update_required = True
    if env_user_id and env_user_id != user.zerodha_user_id:
        user.zerodha_user_id = env_user_id
        update_required = True
    if update_required:
        user.updated_at = get_ist_time()
        db.session.commit()
    return user

# ===== Authentication =====

def token_required(f):
    """Decorator to verify JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def generate_token(user_id):
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'iat': get_ist_time(),
        'exp': get_ist_time() + timedelta(hours=app.config['JWT_EXPIRATION_HOURS'])
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


# ===== API Routes =====

# ---- Auth Routes ----

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user with trading config"""
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email and password required'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 409
    
    try:
        user = User(
            email=data['email'],
            starting_capital=data.get('starting_capital', 20000),
            leverage=data.get('leverage', 5.0),
            trade_symbol=data.get('trade_symbol', 'TATASTEEL'),
            buffer_amount=data.get('buffer_amount', 0.10),
            profit_target_type=data.get('profit_target_type', 'ratio'),
            profit_target_ratio=data.get('profit_target_ratio', 2.0),
            profit_target_percent=data.get('profit_target_percent', 1.0),
            profit_target_fixed=data.get('profit_target_fixed', 300),
            kite_api_key=data.get('kite_api_key', ''),
            kite_access_token=data.get('kite_access_token', ''),
            zerodha_user_id=data.get('zerodha_user_id', ''),
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        BotLog.create_log(user.id, 'AUTH', 'User registered', 'INFO')
        
        token = generate_token(user.id)
        return jsonify({
            'message': 'User registered successfully',
            'token': token,
            'user': user.to_dict()
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email and password required'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    try:
        token = generate_token(user.id)
        BotLog.create_log(user.id, 'AUTH', f'User logged in', 'INFO')
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': user.to_dict()
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """User logout"""
    current_user = get_default_user()
    BotLog.create_log(current_user.id, 'AUTH', 'User logged out', 'INFO')
    return jsonify({'message': 'Logged out successfully'}), 200


# ---- Kite OAuth Routes ----

@app.route('/api/kite/login', methods=['GET'])
def kite_login():
    """Get Kite Connect login URL"""
    current_user = get_default_user()
    if not current_user.kite_api_key:
        return jsonify({'error': 'Kite API key missing'}), 400

    kite = KiteConnect(api_key=current_user.kite_api_key)
    return jsonify({'login_url': kite.login_url()}), 200


@app.route('/api/kite/callback', methods=['GET'])
def kite_callback():
    """Handle Kite OAuth callback and store access token"""
    current_user = get_default_user()
    request_token = request.args.get('request_token')
    if not request_token:
        return jsonify({'error': 'Missing request_token'}), 400

    if not current_user.kite_api_key:
        return jsonify({'error': 'Kite API key missing'}), 400

    api_secret = os.getenv('KITE_API_SECRET')
    if not api_secret:
        return jsonify({
            'error': 'KITE_API_SECRET not set',
            'hint': 'Set the env var and restart the backend'
        }), 500

    try:
        kite = KiteConnect(api_key=current_user.kite_api_key)
        session = kite.generate_session(request_token, api_secret=api_secret)
        access_token = session.get('access_token')
        if not access_token:
            return jsonify({'error': 'Access token not returned'}), 500

        current_user.kite_access_token = access_token
        if session.get('user_id'):
            current_user.zerodha_user_id = session.get('user_id')
        current_user.updated_at = get_ist_time()
        db.session.commit()

        BotLog.create_log(current_user.id, 'AUTH', 'Kite access token updated', 'INFO')
        return jsonify({
            'message': 'Kite OAuth completed',
            'access_token': access_token,
            'user_id': current_user.zerodha_user_id
        }), 200
    except Exception as e:
        db.session.rollback()
        try:
            BotLog.create_log(current_user.id, 'AUTH', f'Kite OAuth failed: {e}', 'ERROR')
        except Exception:
            pass
        return jsonify({'error': str(e)}), 500


# ---- Config Routes ----

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get user trading configuration"""
    current_user = get_default_user()
    return jsonify({
        'kite_api_key': current_user.kite_api_key,
        'kite_access_token': current_user.kite_access_token,
        'zerodha_user_id': current_user.zerodha_user_id,
        'trading': {
            'starting_capital': current_user.starting_capital,
            'leverage': current_user.leverage,
            'trade_symbol': current_user.trade_symbol,
            'buffer_amount': current_user.buffer_amount,
            'profit_target_type': current_user.profit_target_type,
            'profit_target_ratio': current_user.profit_target_ratio,
            'profit_target_percent': current_user.profit_target_percent,
            'profit_target_fixed': current_user.profit_target_fixed,
        },
        'bot': {
            'active': current_user.bot_active,
            'last_run': current_user.bot_last_run.isoformat() if current_user.bot_last_run else None,
        }
    }), 200


@app.route('/api/config', methods=['PUT'])
def update_config():
    """Update user trading configuration"""
    current_user = get_default_user()
    data = request.get_json()
    
    try:
        # Update trading config
        if 'trading' in data:
            trading = data['trading']
            current_user.starting_capital = trading.get('starting_capital', current_user.starting_capital)
            current_user.leverage = trading.get('leverage', current_user.leverage)
            current_user.trade_symbol = trading.get('trade_symbol', current_user.trade_symbol)
            current_user.buffer_amount = trading.get('buffer_amount', current_user.buffer_amount)
            current_user.profit_target_type = trading.get('profit_target_type', current_user.profit_target_type)
            current_user.profit_target_ratio = trading.get('profit_target_ratio', current_user.profit_target_ratio)
            current_user.profit_target_percent = trading.get('profit_target_percent', current_user.profit_target_percent)
            current_user.profit_target_fixed = trading.get('profit_target_fixed', current_user.profit_target_fixed)
        
        # Update Kite API credentials
        if 'kite' in data:
            kite = data['kite']
            current_user.kite_api_key = kite.get('api_key', current_user.kite_api_key)
            current_user.kite_access_token = kite.get('access_token', current_user.kite_access_token)
            current_user.zerodha_user_id = kite.get('zerodha_user_id', current_user.zerodha_user_id)
        
        current_user.updated_at = get_ist_time()
        db.session.commit()
        
        BotLog.create_log(current_user.id, 'CONFIG', 'Configuration updated', 'INFO')
        
        return jsonify({'message': 'Configuration updated successfully'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ---- Bot Control Routes ----

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Start trading bot for the day"""
    current_user = get_default_user()
    try:
        # Check if bot is actually running (in-memory state, not database)
        if current_user.id in trading_service.bot_threads and trading_service.bot_threads[current_user.id].is_alive():
            return jsonify({'error': 'Bot already running'}), 400
        
        # Validate credentials
        if not all([current_user.kite_api_key, current_user.kite_access_token]):
            return jsonify({'error': 'Kite API credentials missing'}), 400
        
        # Start bot in background
        trading_service.start_bot(current_user)
        
        current_user.bot_active = True
        current_user.bot_last_run = get_ist_time()
        db.session.commit()
        
        BotLog.create_log(current_user.id, 'BOT', 'Bot started', 'INFO')
        
        return jsonify({'message': 'Bot started successfully'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """Stop trading bot"""
    current_user = get_default_user()
    try:
        trading_service.stop_bot(current_user.id)
        
        current_user.bot_active = False
        db.session.commit()
        
        BotLog.create_log(current_user.id, 'BOT', 'Bot stopped', 'INFO')
        
        return jsonify({'message': 'Bot stopped successfully'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bot/status', methods=['GET'])
def bot_status():
    """Get current bot status and live data"""
    current_user = get_default_user()
    try:
        status = trading_service.get_bot_status(current_user.id)
        # Sync database flag with actual running state
        is_actually_running = status['status'] in ['RUNNING', 'READY']
        if current_user.bot_active != is_actually_running:
            current_user.bot_active = is_actually_running
            db.session.commit()
        return jsonify(status), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Analytics Routes ----

def get_live_open_pnl(current_user):
    """Fetch live MTM P&L for currently open intraday positions."""
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return 0.0

    try:
        from app_files.kite_service import KiteService
        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        positions = kite.get_positions() or {"day": []}
        day_positions = positions.get('day', []) or []
        return float(sum((p.get('pnl', 0) or 0) for p in day_positions if (p.get('quantity', 0) or 0) != 0))
    except Exception:
        return 0.0


def build_daily_summary_from_trades(trades, include_open_pnl=0.0):
    """Build summary object expected by dashboard from Trade rows."""
    total_trades = len(trades)
    closed_trades = [t for t in trades if t.pnl is not None]
    winning_trades = len([t for t in closed_trades if t.pnl > 0])
    losing_trades = len([t for t in closed_trades if t.pnl < 0])
    total_pnl = float(sum((t.pnl or 0) for t in closed_trades) + include_open_pnl)
    win_rate = (winning_trades / len(closed_trades) * 100) if closed_trades else 0.0

    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'cancelled_trades': len([t for t in trades if t.status == 'CANCELLED']),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_profit_per_trade': (sum(t.pnl for t in closed_trades if t.pnl and t.pnl > 0) / winning_trades) if winning_trades else 0.0,
        'largest_win': max((t.pnl for t in closed_trades if t.pnl is not None), default=0.0),
        'largest_loss': min((t.pnl for t in closed_trades if t.pnl is not None), default=0.0),
    }

@app.route('/api/analytics/today', methods=['GET'])
def today_analytics():
    """Get today's trading analytics"""
    current_user = get_default_user()
    try:
        reconcile_open_trades_for_user(current_user)
        today = get_ist_time().date()
        trades = Trade.query.filter(
            Trade.user_id == current_user.id,
            Trade.trade_date == today
        ).all()

        open_pnl = get_live_open_pnl(current_user)
        summary = build_daily_summary_from_trades(trades, include_open_pnl=open_pnl)
        
        return jsonify({
            'date': today.isoformat(),
            'summary': summary,
            'includes_open_pnl': True,
            'open_positions_pnl': open_pnl,
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/weekly', methods=['GET'])
def weekly_analytics():
    """Get last 7 days analytics"""
    current_user = get_default_user()
    try:
        reconcile_open_trades_for_user(current_user)
        end_date = get_ist_time().date()
        start_date = end_date - timedelta(days=7)

        trades = Trade.query.filter(
            Trade.user_id == current_user.id,
            Trade.trade_date >= start_date,
            Trade.trade_date <= end_date
        ).all()

        trades_by_day = defaultdict(list)
        for trade in trades:
            trades_by_day[trade.trade_date].append(trade)

        open_pnl_today = get_live_open_pnl(current_user)

        daily_stats = []
        cursor = start_date
        while cursor <= end_date:
            day_trades = trades_by_day.get(cursor, [])
            include_open = open_pnl_today if cursor == end_date else 0.0
            summary = build_daily_summary_from_trades(day_trades, include_open_pnl=include_open)
            summary['stats_date'] = cursor.isoformat()
            daily_stats.append(summary)
            cursor += timedelta(days=1)

        non_empty_days = [d for d in daily_stats if d['total_trades'] > 0 or abs(d['total_pnl']) > 0]
        total_pnl = sum(d['total_pnl'] for d in daily_stats)
        total_trades = sum(d['total_trades'] for d in daily_stats)
        
        return jsonify({
            'period': f"{start_date.isoformat()} to {end_date.isoformat()}",
            'daily_stats': daily_stats,
            'summary': {
                'total_trading_days': len(non_empty_days),
                'total_trades': total_trades,
                'total_pnl': total_pnl,
                'avg_daily_pnl': (total_pnl / len(non_empty_days)) if non_empty_days else 0,
                'best_day': max((d['total_pnl'] for d in daily_stats), default=0),
                'worst_day': min((d['total_pnl'] for d in daily_stats), default=0),
            }
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/trades', methods=['GET'])
def get_trades():
    """Get trades with filtering and pagination"""
    current_user = get_default_user()
    try:
        reconcile_open_trades_for_user(current_user)

        # Query parameters
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        date_from = request.args.get('from')
        date_to = request.args.get('to')
        status = request.args.get('status')
        
        query = Trade.query.filter_by(user_id=current_user.id)
        
        if date_from:
            query = query.filter(Trade.trade_date >= datetime.fromisoformat(date_from).date())
        if date_to:
            query = query.filter(Trade.trade_date <= datetime.fromisoformat(date_to).date())
        if status:
            query = query.filter_by(status=status)
        
        total = query.count()
        trades = query.order_by(Trade.entry_time.desc()).limit(limit).offset(offset).all()
        
        return jsonify({
            'total': total,
            'limit': limit,
            'offset': offset,
            'trades': [t.to_dict() for t in trades]
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/performance', methods=['GET'])
def performance_analytics():
    """Get performance metrics"""
    current_user = get_default_user()
    try:
        reconcile_open_trades_for_user(current_user)
        # Last 30 days
        end_date = get_ist_time().date()
        start_date = end_date - timedelta(days=30)
        
        trades = Trade.query.filter(
            Trade.user_id == current_user.id,
            Trade.trade_date >= start_date,
            Trade.trade_date <= end_date,
            Trade.pnl.isnot(None)
        ).all()
        
        if not trades:
            return jsonify({
                'period_days': 30,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_profit': 0,
                'avg_loss': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'profit_factor': 0,
            }), 200
        
        winning = [t for t in trades if t.pnl and t.pnl > 0]
        losing = [t for t in trades if t.pnl and t.pnl < 0]
        
        total_wins = sum(t.pnl for t in winning) if winning else 0
        total_losses = abs(sum(t.pnl for t in losing)) if losing else 0
        
        return jsonify({
            'period_days': 30,
            'total_trades': len(trades),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': (len(winning) / len(trades) * 100) if trades else 0,
            'total_pnl': sum(t.pnl for t in trades if t.pnl),
            'avg_profit': (total_wins / len(winning)) if winning else 0,
            'avg_loss': (total_losses / len(losing)) if losing else 0,
            'best_trade': max((t.pnl for t in trades if t.pnl), default=0),
            'worst_trade': min((t.pnl for t in trades if t.pnl), default=0),
            'profit_factor': (total_wins / total_losses) if total_losses > 0 else float('inf') if total_wins > 0 else 0,
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Logs Routes ----

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get bot logs"""
    current_user = get_default_user()
    try:
        limit = request.args.get('limit', 100, type=int)
        log_type = request.args.get('type')
        log_level = request.args.get('level')
        
        query = BotLog.query.filter_by(user_id=current_user.id)
        
        if log_type:
            query = query.filter_by(log_type=log_type)
        if log_level:
            query = query.filter_by(log_level=log_level)
        
        logs = query.order_by(BotLog.timestamp.desc()).limit(limit).all()
        
        return jsonify({
            'total': len(logs),
            'logs': [l.to_dict() for l in logs]
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Manual Trading ----

@app.route('/api/orders/cancel', methods=['POST'])
def cancel_order_route():
    """Cancel an open order"""
    current_user = get_default_user()
    
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return jsonify({'error': 'Kite credentials not configured'}), 400
    
    try:
        data = request.get_json()
        order_id = data.get('order_id', '')
        
        if not order_id:
            return jsonify({'error': 'Order ID required'}), 400
        
        from app_files.kite_service import KiteService
        
        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        
        # Cancel the order
        result = kite.cancel_order(order_id)
        
        if not result:
            return jsonify({'error': 'Failed to cancel order'}), 500
        
        # Log the cancellation
        new_log = BotLog(
            user_id=current_user.id,
            log_level='INFO',
            log_type='TRADE',
            message=f'Order cancelled: {order_id}'
        )
        
        db.session.add(new_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'message': f'Order {order_id} cancelled successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/manual-trade', methods=['POST'])
def manual_trade():
    """Place a manual trade with automatic SL and TP levels"""
    current_user = get_default_user()
    
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return jsonify({'error': 'Kite credentials not configured'}), 400
    
    try:
        data = request.get_json()
        
        trade_type = data.get('trade_type', 'BUY')  # BUY or SELL
        quantity = int(data.get('quantity', 0))
        entry_price = float(data.get('entry_price', 0))
        sl_percent = float(data.get('sl_percent', 0.5))  # Default 0.5%
        tp_ratio = float(data.get('tp_ratio', 2.0))  # Default 2:1 R:R
        trade_symbol = data.get('symbol', current_user.trade_symbol)  # Allow override of symbol
        
        if quantity <= 0:
            return jsonify({'error': 'Invalid quantity'}), 400
        
        if entry_price <= 0:
            return jsonify({'error': 'Invalid entry price'}), 400
        
        from app_files.kite_service import KiteService
        from app_files import config
        from datetime import datetime, date
        
        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        
        # Extract symbol - use provided symbol or fall back to user's default
        symbol_parts = trade_symbol.split(':')
        if len(symbol_parts) == 2:
            exchange, symbol = symbol_parts
        else:
            exchange = config.EXCHANGE
            symbol = trade_symbol
        
        # Calculate SL and TP
        if trade_type == 'BUY':
            sl_price = entry_price * (1 - sl_percent / 100)
            risk_per_share = entry_price - sl_price
            tp_price = entry_price + (risk_per_share * tp_ratio)
            exit_side = 'SELL'
        else:  # SELL
            sl_price = entry_price * (1 + sl_percent / 100)
            risk_per_share = sl_price - entry_price
            tp_price = entry_price - (risk_per_share * tp_ratio)
            exit_side = 'BUY'
        
        # Place the entry order
        order_id = kite.place_order(
            symbol=symbol,
            transaction_type=trade_type,
            quantity=quantity,
            price=entry_price,
            product=config.TRADE_TYPE,
            order_type="MARKET"
        )
        
        if not order_id:
            return jsonify({'error': 'Failed to place order'}), 500

        stoploss_order_id = kite.place_order(
            symbol=symbol,
            transaction_type=exit_side,
            quantity=quantity,
            price=None,
            trigger_price=sl_price,
            product=config.TRADE_TYPE,
            order_type="SL-M"
        )

        if not stoploss_order_id:
            return jsonify({'error': 'Entry placed but SL order failed. Please exit manually immediately.'}), 500

        target_order_id = kite.place_order(
            symbol=symbol,
            transaction_type=exit_side,
            quantity=quantity,
            price=tp_price,
            product=config.TRADE_TYPE,
            order_type="LIMIT"
        )

        if not target_order_id:
            cancel_order_if_open(kite, stoploss_order_id)
            return jsonify({'error': 'Entry placed but target order failed. SL cancelled for safety; please manage exit manually.'}), 500
        
        # Log the trade in database
        new_trade = Trade(
            user_id=current_user.id,
            trade_date=get_ist_time().date(),
            entry_time=get_ist_time(),
            side='B' if trade_type == 'BUY' else 'S',
            symbol=trade_symbol,
            quantity=quantity,
            entry_price=entry_price,
            stoploss_price=sl_price,
            target_price=tp_price,
            entry_order_id=order_id,
            stoploss_order_id=stoploss_order_id,
            status='OPEN',
            notes=append_target_order_id(
                f'Manual trade: {trade_type} {quantity} @ ₹{entry_price}, SL: ₹{sl_price:.2f}, TP: ₹{tp_price:.2f}',
                target_order_id
            )
        )
        
        db.session.add(new_trade)
        
        # Log the action
        new_log = BotLog(
            user_id=current_user.id,
            log_level='INFO',
            log_type='TRADE',
            message=(
                f'Manual {trade_type}: {quantity} x {symbol} @ ₹{entry_price} | '
                f'SL: ₹{sl_price:.2f} ({stoploss_order_id}) | TP: ₹{tp_price:.2f} ({target_order_id}) | '
                f'Entry Order ID: {order_id}'
            )
        )
        
        db.session.add(new_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'stoploss_order_id': stoploss_order_id,
            'target_order_id': target_order_id,
            'trade_type': trade_type,
            'quantity': quantity,
            'entry_price': entry_price,
            'sl_price': round(sl_price, 2),
            'tp_price': round(tp_price, 2),
            'risk_per_share': round(risk_per_share, 2),
            'potential_profit': round(risk_per_share * tp_ratio * quantity, 2),
            'potential_loss': round(risk_per_share * quantity, 2),
            'message': f'{trade_type} order placed with linked SL/TP exits. Opposite exit order will be cancelled when one gets filled.'
        }), 200
        
    except ValueError as e:
        return jsonify({'error': f'Invalid input: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/manual-exit', methods=['POST'])
def manual_exit():
    """Manually exit an open position and cancel associated orders (SL and TP)"""
    current_user = get_default_user()
    
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return jsonify({'error': 'Kite credentials not configured'}), 400
    
    try:
        data = request.get_json()
        symbol = data.get('symbol', '')
        quantity = int(data.get('quantity', 0))
        exit_price = float(data.get('price', 0))
        
        if not symbol or quantity <= 0 or exit_price <= 0:
            return jsonify({'error': 'Invalid parameters'}), 400
        
        from app_files.kite_service import KiteService
        from app_files import config
        from datetime import datetime, date
        
        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        
        # Extract symbol and exchange
        symbol_parts = symbol.split(':')
        if len(symbol_parts) == 2:
            exchange, sym = symbol_parts
        else:
            exchange = config.EXCHANGE
            sym = symbol
        
        # Determine the opposite side (if we bought, we sell to exit)
        # Get recent trades to determine if it's BUY or SELL
        from models import Trade
        recent_trade = Trade.query.filter_by(
            user_id=current_user.id,
            symbol=symbol,
            status='OPEN'
        ).order_by(Trade.entry_time.desc()).first()

        if not recent_trade and ':' not in symbol:
            recent_trade = Trade.query.filter(
                Trade.user_id == current_user.id,
                Trade.status == 'OPEN',
                Trade.symbol.like(f'%:{sym}')
            ).order_by(Trade.entry_time.desc()).first()
        
        exit_side = 'SELL' if (recent_trade and recent_trade.side == 'B') else 'BUY'
        
        # Place the exit order
        exit_order_id = kite.place_order(
            symbol=sym,
            transaction_type=exit_side,
            quantity=quantity,
            price=exit_price,
            product=config.TRADE_TYPE,
            order_type="MARKET"
        )
        
        if not exit_order_id:
            return jsonify({'error': 'Failed to place exit order'}), 500
        
        cancelled_orders = []

        # Update trade status to CLOSED
        if recent_trade:
            orders = kite.get_orders() or []
            orders_by_id = {o.get('order_id'): o for o in orders if o.get('order_id')}

            target_order_id = extract_target_order_id(recent_trade.notes)

            if cancel_order_if_open(kite, recent_trade.stoploss_order_id, orders_by_id):
                cancelled_orders.append(recent_trade.stoploss_order_id)
            if cancel_order_if_open(kite, target_order_id, orders_by_id):
                cancelled_orders.append(target_order_id)

            recent_trade.status = 'CLOSED'
            recent_trade.exit_time = get_ist_time()
            recent_trade.exit_price = exit_price
            recent_trade.exit_order_id = exit_order_id
            
            # Calculate realized P&L
            if exit_side == 'SELL':
                pnl = (exit_price - recent_trade.entry_price) * quantity
                pnl_percent = ((exit_price - recent_trade.entry_price) / recent_trade.entry_price) * 100
            else:
                pnl = (recent_trade.entry_price - exit_price) * quantity
                pnl_percent = ((recent_trade.entry_price - exit_price) / recent_trade.entry_price) * 100
            
            recent_trade.pnl = pnl
            recent_trade.pnl_percent = pnl_percent
        
        # Log the manual exit
        new_log = BotLog(
            user_id=current_user.id,
            log_level='INFO',
            log_type='TRADE',
            message=(
                f'Manual Exit: {exit_side} {quantity} x {symbol} @ ₹{exit_price} | '
                f'Exit Order ID: {exit_order_id} | Cancelled exit orders: {cancelled_orders if cancelled_orders else "None"}'
            )
        )
        
        db.session.add(new_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'exit_order_id': exit_order_id,
            'symbol': symbol,
            'side': exit_side,
            'quantity': quantity,
            'exit_price': round(exit_price, 2),
            'cancelled_orders': cancelled_orders,
            'message': f'Position closed successfully. Exit order placed at ₹{exit_price}. Opposite SL/TP orders cancelled where open.'
        }), 200
        
    except ValueError as e:
        return jsonify({'error': f'Invalid input: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Portfolio & Holdings ----

@app.route('/api/portfolio/holdings', methods=['GET'])
def get_portfolio_holdings():
    """Get detailed portfolio holdings with P&L and performance metrics"""
    current_user = get_default_user()
    
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return jsonify({'error': 'Kite credentials not configured'}), 400
    
    try:
        from app_files.kite_service import KiteService
        
        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        
        # Fetch holdings and margins
        holdings = kite.get_holdings()
        margins = kite.get_account_balance()
        
        if holdings is None:
            holdings = []
        
        if not margins:
            return jsonify({'error': 'Could not fetch account data'}), 503
        
        # Calculate portfolio summary
        total_investment = sum([h.get('average_price', 0) * h.get('quantity', 0) for h in holdings])
        total_current_value = sum([h.get('last_price', 0) * h.get('quantity', 0) for h in holdings])
        total_pnl = sum([h.get('pnl', 0) for h in holdings])
        total_day_pnl = sum([h.get('day_change', 0) * h.get('quantity', 0) for h in holdings])
        
        # Available funds
        available_cash = margins.get('equity', {}).get('available', {}).get('live_balance', 0)
        used_margin = margins.get('equity', {}).get('utilised', {}).get('debits', 0)
        
        # Calculate returns
        overall_return_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0
        day_return_pct = (total_day_pnl / total_current_value * 100) if total_current_value > 0 else 0
        
        # Enhance holdings with additional metrics
        enhanced_holdings = []
        for holding in holdings:
            avg_price = holding.get('average_price', 0)
            ltp = holding.get('last_price', 0)
            qty = holding.get('quantity', 0)
            investment = avg_price * qty
            current_value = ltp * qty
            pnl = holding.get('pnl', 0)
            pnl_pct = (pnl / investment * 100) if investment > 0 else 0
            
            enhanced_holdings.append({
                'symbol': holding.get('tradingsymbol', ''),
                'exchange': holding.get('exchange', ''),
                'quantity': qty,
                'average_price': round(avg_price, 2),
                'last_price': round(ltp, 2),
                'investment': round(investment, 2),
                'current_value': round(current_value, 2),
                'pnl': round(pnl, 2),
                'pnl_percentage': round(pnl_pct, 2),
                'day_change': round(holding.get('day_change', 0), 2),
                'day_change_percentage': round(holding.get('day_change_percentage', 0), 2),
                'isin': holding.get('isin', ''),
                'product': holding.get('product', '')
            })
        
        # Sort by investment amount (largest first)
        enhanced_holdings.sort(key=lambda x: x['investment'], reverse=True)
        
        return jsonify({
            'success': True,
            'summary': {
                'total_investment': round(total_investment, 2),
                'current_value': round(total_current_value, 2),
                'total_pnl': round(total_pnl, 2),
                'overall_return_percentage': round(overall_return_pct, 2),
                'day_pnl': round(total_day_pnl, 2),
                'day_return_percentage': round(day_return_pct, 2),
                'available_cash': round(available_cash, 2),
                'used_margin': round(used_margin, 2),
                'total_holdings': len(holdings),
                'portfolio_value': round(total_current_value + available_cash, 2)
            },
            'holdings': enhanced_holdings
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/positions', methods=['GET'])
def get_portfolio_positions():
    """Get open intraday positions for the user"""
    current_user = get_default_user()

    if not current_user.kite_api_key or not current_user.kite_access_token:
        return jsonify({'error': 'Kite credentials not configured'}), 400

    try:
        from app_files.kite_service import KiteService

        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        positions = kite.get_positions() or {"day": [], "net": []}
        day_positions = positions.get('day', []) or []

        open_positions = [p for p in day_positions if p.get('quantity', 0) != 0]
        enhanced_positions = []

        for position in open_positions:
            qty = position.get('quantity', 0)
            avg_price = position.get('average_price', 0) or 0
            ltp = position.get('last_price', 0) or position.get('ltp', 0) or 0
            pnl = position.get('pnl', 0) or 0

            enhanced_positions.append({
                'symbol': position.get('tradingsymbol', ''),
                'exchange': position.get('exchange', ''),
                'quantity': qty,
                'average_price': round(avg_price, 2),
                'last_price': round(ltp, 2),
                'pnl': round(pnl, 2),
                'product': position.get('product', ''),
                'day_buy_quantity': position.get('day_buy_quantity', 0),
                'day_sell_quantity': position.get('day_sell_quantity', 0)
            })

        return jsonify({
            'success': True,
            'total_positions': len(enhanced_positions),
            'positions': enhanced_positions
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Test Endpoint ----


@app.route('/api/test/market', methods=['GET'])
def test_market():
    """Simple test endpoint"""
    return jsonify({'status': 'test working', 'price': 123.45}), 200


# ---- Live Market Data ----

@app.route('/api/market/live', methods=['GET'])
def get_live_market_data():
    """Get live market data including price and trading levels"""
    current_user = get_default_user()
    
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return jsonify({'error': 'Kite credentials not configured'}), 400
    
    try:
        from app_files.kite_service import KiteService
        from app_files import config
        from datetime import datetime
        import pytz
        
        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        
        # Extract symbol from trade_symbol (e.g., "NSE:TATASTEEL" -> "TATASTEEL")
        symbol_parts = current_user.trade_symbol.split(':')
        if len(symbol_parts) == 2:
            exchange, symbol = symbol_parts
        else:
            exchange = config.EXCHANGE
            symbol = config.SYMBOL_NSE
        
        # Get quote
        quote = kite.get_quote(exchange, symbol)
        
        if not quote:
            return jsonify({'error': 'Unable to fetch market data'}), 503
        
        # Get current IST time
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist)
        
        # Calculate buffer using same method as bot (dynamic ATR if enabled, else fixed)
        buffer = calculate_atr_buffer_for_symbol(kite, exchange, symbol)
        
        # Check if triggers are cached (LOCKED at 9:30 AM)
        cached = get_cached_triggers(symbol)
        
        if cached:
            high = cached['high']
            low = cached['low']
            buy_trigger = cached['buy']
            sell_trigger = cached['sell']
        else:
            # Calculate trading levels from OPENING RANGE (9:15-9:30 AM), not daily OHLC
            import datetime as dt
            import pytz
            
            ist = pytz.timezone('Asia/Kolkata')
            now = dt.datetime.now(ist)
            
            # Try to get opening range candle (9:15-9:30 AM)
            high = None
            low = None
            
            try:
                start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
                end_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
                
                candles = kite.get_historical_data(
                    exchange, symbol,
                    start_time,
                    end_time,
                    interval="15minute"
                )
                
                if candles and len(candles) > 0:
                    # Use opening range high/low (LOCKED at 9:30 AM)
                    high = candles[0].get('high', 0)
                    low = candles[0].get('low', 0)
            except Exception:
                pass
            
            # Fallback to daily OHLC if opening range not available
            ohlc = quote.get('ohlc', {})
            if not high or not low:
                high = ohlc.get('high', 0) if not high else high
                low = ohlc.get('low', 0) if not low else low
            
            buy_trigger = high + buffer if high else None
            sell_trigger = low - buffer if low else None
            
            # Cache these triggers at opening range time
            cache_triggers(symbol, buy_trigger, sell_trigger, high, low)
        
        ohlc = quote.get('ohlc', {})
        
        return jsonify({
            'symbol': f"{exchange}:{symbol}",
            'current_price': quote.get('last_price'),
            'timestamp': current_time.isoformat(),
            'ohlc': {
                'open': ohlc.get('open'),
                'high': ohlc.get('high'),
                'low': ohlc.get('low'),
                'close': ohlc.get('close')
            },
            'volume': quote.get('volume'),
            'average_price': quote.get('average_price'),
            'trading_levels': {
                'buy_trigger': buy_trigger,
                'sell_trigger': sell_trigger,
                'buffer': buffer
            },
            'market_status': 'open'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e), 'market_status': 'error'}), 500


@app.route('/api/market/watchlist', methods=['GET'])
def get_market_watchlist():
    """Get live market data for all monitored symbols"""
    current_user = get_default_user()
    
    if not current_user.kite_api_key or not current_user.kite_access_token:
        return jsonify({'error': 'Kite credentials not configured'}), 400
    
    try:
        from app_files.kite_service import KiteService
        from app_files import config
        from datetime import datetime
        import pytz
        
        kite = KiteService(current_user.kite_api_key, current_user.kite_access_token)
        
        # Get current IST time
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist)
        
        watchlist_data = []
        
        # Fetch data for all monitored symbols
        for symbol_config in config.SYMBOLS_TO_MONITOR:
            symbol = symbol_config["symbol"]
            exchange = symbol_config["exchange"]
            
            try:
                # Check if triggers are cached (LOCKED at 9:30 AM)
                cached = get_cached_triggers(symbol)
                
                # Get quote (needed regardless)
                quote = kite.get_quote(exchange, symbol)
                
                if not quote:
                    continue
                
                ohlc = quote.get('ohlc', {})
                last_price = quote.get('last_price', 0)
                open_price = ohlc.get('open', 0)
                close_price = ohlc.get('close', 0)
                
                # Calculate buffer using same method as bot (dynamic ATR if enabled, else fixed)
                buffer = calculate_atr_buffer_for_symbol(kite, exchange, symbol)
                
                # Use cached triggers if available (LOCKED at 9:30 AM)
                if cached:
                    high = cached['high']
                    low = cached['low']
                    buy_trigger = cached['buy']
                    sell_trigger = cached['sell']
                else:
                    # Calculate trading levels from OPENING RANGE (9:15-9:30 AM), not daily OHLC
                    import datetime as dt
                    import pytz
                    
                    ist = pytz.timezone('Asia/Kolkata')
                    now = dt.datetime.now(ist)
                    
                    # Try to get opening range candle (9:15-9:30 AM)
                    high = None
                    low = None
                    
                    try:
                        start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
                        end_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
                        
                        candles = kite.get_historical_data(
                            exchange, symbol,
                            start_time,
                            end_time,
                            interval="15minute"
                        )
                        
                        if candles and len(candles) > 0:
                            # Use opening range high/low (LOCKED at 9:30 AM)
                            high = candles[0].get('high', 0)
                            low = candles[0].get('low', 0)
                    except Exception:
                        pass
                    
                    # Fallback to daily OHLC if opening range not available
                    if not high or not low:
                        high = ohlc.get('high', 0) if not high else high
                        low = ohlc.get('low', 0) if not low else low
                    
                    buy_trigger = high + buffer if high else None
                    sell_trigger = low - buffer if low else None
                    
                    # Cache these triggers at opening range time
                    cache_triggers(symbol, buy_trigger, sell_trigger, high, low)
                
                # Calculate price change
                price_change = last_price - open_price if open_price else 0
                price_change_percent = (price_change / open_price * 100) if open_price else 0
                
                watchlist_data.append({
                    'symbol': symbol,
                    'exchange': exchange,
                    'display_name': f"{exchange}:{symbol}",
                    'last_price': last_price,
                    'ohlc': {
                        'open': open_price,
                        'high': high,
                        'low': low,
                        'close': close_price
                    },
                    'volume': quote.get('volume', 0),
                    'average_price': quote.get('average_price', 0),
                    'price_change': price_change,
                    'price_change_percent': price_change_percent,
                    'trading_levels': {
                        'buy_trigger': buy_trigger,
                        'sell_trigger': sell_trigger,
                        'buffer': buffer
                    }
                })
                
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'timestamp': current_time.isoformat(),
            'trigger_cache_locked_at': TRIGGER_CACHE_LOCK_TIME.isoformat() if TRIGGER_CACHE_LOCK_TIME else None,
            'trigger_cache_status': 'LOCKED (9:30 AM)' if TRIGGER_CACHE_LOCK_TIME else 'NOT YET LOCKED',
            'symbols': watchlist_data,
            'total_symbols': len(watchlist_data)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


# ---- Health Check ----

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'test': 'version_2'}), 200


# ===== Database Setup =====

@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print('Database initialized')


# ===== Error Handlers =====

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500


# ===== Helper Extensions to Models =====

def create_log(user_id, log_type, message, log_level='INFO', trade_id=None):
    """Helper to create a log entry"""
    try:
        log = BotLog(
            user_id=user_id,
            log_type=log_type,
            message=message,
            log_level=log_level,
            trade_id=trade_id
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass

BotLog.create_log = staticmethod(create_log)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default user if needed
        user = get_default_user()
        # Reset bot_active flag on startup (in case server crashed)
        if user.bot_active:
            user.bot_active = False
            db.session.commit()
        
        # Load trigger cache from file if available
        print("\n" + "="*50)
        print("  Loading trigger cache...")
        print("="*50)
        load_trigger_cache_from_file()
        
        print("\n" + "="*50)
        print("  TRADING BOT BACKEND API - RUNNING")
        print("="*50)
        print(f"  API Server: http://localhost:{os.getenv('PORT', 5000)}")
        print(f"  Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print(f"  Environment: {'Development' if os.getenv('FLASK_DEBUG', '0') == '1' else 'Production'}")
        print("="*50 + "\n")
    
    # Use environment variables for configuration
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    port = int(os.getenv('PORT', 5000))
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
