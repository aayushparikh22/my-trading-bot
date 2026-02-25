# Trading Bot - Zerodha Kite API

An automated trading bot using opening range breakout strategy with Zerodha's Kite Connect API. Features real-time market monitoring, automated entry/exit signals, stop-loss management, and a web-based dashboard for monitoring and control.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 14+ & npm
- Zerodha account with Kite Connect API access
- Win 10/11 or Linux/Mac with Python & Node.js installed

### Installation (5 minutes)

1. **Clone the repository**
   ```bash
   git clone https://github.com/aayushparikh22/my-trading-bot.git
   cd my-trading-bot
   ```

2. **Set up Python environment**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # Linux/Mac
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r app_files/requirements.txt
   pip install -r backend/requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   # Create .env file in project root
   KITE_API_KEY=YOUR_KITE_API_KEY
   KITE_ACCESS_TOKEN=YOUR_KITE_ACCESS_TOKEN
   ZERODHA_USER_ID=YOUR_USER_ID
   ```
   
   > Get these from: https://kite.trade/connect/console

5. **Set up frontend**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

### Run the Bot

**Option 1: Simple Start (Windows)**
```bash
.\START.bat
```

**Option 2: Manual Start**

Terminal 1 (Backend API):
```bash
cd backend
python app.py
```

Terminal 2 (Frontend UI):
```bash
cd frontend
npm start
```

Terminal 3 (Trading Bot):
```bash
python -m app_files.bot_kite
```

**Option 3: PowerShell (Windows)**
```powershell
.\START.ps1
```

The bot will:
- Open Flask API at `http://localhost:5000`
- Open Frontend at `http://localhost:3000`
- Start trading bot in background

Once running, open **http://localhost:3000** in your browser.

---

## 📋 How the Bot Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Dashboard (React)                    │
│              http://localhost:3000                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Flask Backend API                         │
│        http://localhost:5000 (REST endpoints)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ - Authentication & User Management                  │  │
│  │ - Order Management (Entry, Exit, SL)                │  │
│  │ - Trade History & Analytics                        │  │
│  │ - Real-time Status Monitoring                       │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Trading Bot Core (bot_kite.py)                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 1. Market Data: Fetch OHLC & VWAP every 1 min       │  │
│  │ 2. Breakout Detection: Compare price vs VWAP        │  │
│  │ 3. Entry Signal: Buy on breakout + buffer           │  │
│  │ 4. Exit Signal: Sell at target (2:1 risk/reward)   │  │
│  │ 5. Stop Loss: Auto-cancel if SL touched             │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            Zerodha Kite Connect API                         │
│    ┌──────────────────────────────────────────────────┐    │
│    │ - Real-time market data (historical quotes)      │    │
│    │ - Order placement & management                   │    │
│    │ - Portfolio tracking                             │    │
│    └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Trading Strategy: Opening Range Breakout with VWAP

#### Entry Logic
1. **Monitor market** - Track symbols listed in `config.py`
2. **Calculate VWAP** - Daily Volume-Weighted Average Price
3. **Detect breakout** - Price closes above VWAP + buffer (10%)
4. **Place entry order** - Buy with leverage (MIS product type) at breakout price
5. **Set stop-loss** - Automatic SL order at: `Entry Price - (Position Size × 1.5)`

```
Price
  │
  │      ╱╱╱ ← Breakout (Price > VWAP + Buffer)
  │    ╱╱╱
  │  ╱╱╱
  ├─────────────── VWAP + Buffer (Entry level)
  │                
  │    ╱    ← Entry order placed here
  │  ╱╱     
  │────────────── VWAP
  │
  └───────────────────── Time (1-minute candles)
```

#### Exit Logic
1. **Profit Target**: Exit at `Entry Price + (Risk × 2)`
   - Risk = Entry Price - Stop Loss Price
   - Example: Entry @10, SL @9 → Risk=1 → Exit @12 (1×2=2 profit)

2. **Stop Loss Hit**: Auto-exit if price hits SL
   - Market volatility triggered the stop

#### Quantity Calculation
```
Quantity = (Capital × Margin% × Leverage) / Entry Price

Example:
  Capital = ₹20,000
  Margin% = 50%
  Leverage = 5x (MIS)
  Entry Price = ₹200
  
  Quantity = (20,000 × 0.50 × 5) / 200 = 250 shares
```

---

## 📁 Project Structure

```
Trading-bot/
├── app_files/                    # Core bot logic
│   ├── bot_kite.py              # Main trading bot (opens position, manages exits)
│   ├── kite_service.py          # Kite API wrapper
│   ├── config.py                # Trading config (symbols, leverage, targets, etc.)
│   └── requirements.txt          # Python dependencies
│
├── backend/                      # Flask API server
│   ├── app.py                   # Flask app & REST endpoints
│   ├── models.py                # Database models (User, Trade, Order, etc.)
│   ├── trading_service.py       # Service layer for trading logic
│   ├── requirements.txt         # Backend dependencies
│   └── tradingbot.db            # SQLite database
│
├── frontend/                     # React web dashboard
│   ├── src/
│   │   ├── App.jsx              # Main app component
│   │   ├── pages/               # Pages (Dashboard, Portfolio, TradingMonitor)
│   │   ├── components/          # Reusable components (APITester, LiveTerminal)
│   │   └── services/            # API calls (api.js)
│   ├── package.json             # Frontend dependencies
│   └── public/                  # Static files
│
├── .env                         # Environment variables (KEEP SECRET!)
├── README.md                    # This file
└── CLEANUP.ps1                  # Cleanup script for removing test files
```

---

## ⚙️ Configuration Guide

Edit `app_files/config.py` to customize the bot:

### Trading Capital & Leverage
```python
STARTING_CAPITAL = 20000        # Your actual trading capital
LEVERAGE = 5                    # Intraday MIS leverage (automatic)
MARGIN_UTILIZATION = 0.50       # Use 50% of capital per trade
```

### Symbols to Monitor
```python
SYMBOLS_TO_MONITOR = [
    {"symbol": "HDFCBANK", "exchange": "NSE"},  # First hit wins
    {"symbol": "INFY", "exchange": "NSE"},
    {"symbol": "TCS", "exchange": "NSE"},
    # ... more symbols
]
```

### Profit Targets
```python
PROFIT_TARGET_TYPE = "ratio"    # "ratio", "percent", or "fixed"
PROFIT_TARGET_RATIO = 2.0       # 2:1 risk/reward ratio
PROFIT_TARGET_PERCENT = 1.0     # Alternative: 1% profit target
PROFIT_TARGET_FIXED = 300       # Alternative: ₹300 fixed profit
```

### Market Hours
```python
MARKET_OPEN_TIME = "09:15"      # IST (India Standard Time)
MARKET_CLOSE_TIME = "15:30"
```

---

## 🔌 API Endpoints

### Authentication
- `POST /api/login` - User login
- `POST /api/register` - Register new user
- `POST /api/logout` - Logout user

### Trading Control
- `POST /api/start-bot` - Start trading bot
- `POST /api/stop-bot` - Stop trading bot
- `GET /api/bot-status` - Get bot status

### Orders & Positions
- `GET /api/orders` - List all orders
- `POST /api/place-order` - Place manual order
- `POST /api/cancel-order` - Cancel pending order
- `GET /api/positions` - Current positions

### Dashboard & Analytics
- `GET /api/portfolio` - Portfolio summary
- `GET /api/trades` - Trade history
- `GET /api/daily-stats` - Daily statistics
- `GET /api/market-data` - Current market data

---

## 📊 Running the Bot in Detail

### Step 1: Start Backend API
```bash
cd backend
python app.py
# Output: "Running on http://localhost:5000"
```

The API will:
- Initialize SQLite database
- Set up Flask routes
- Listen for frontend requests

### Step 2: Start Frontend UI
```bash
cd frontend
npm start
# Output: "Compiled successfully!"
# Browser opens: http://localhost:3000
```

### Step 3: Authenticate
1. Click "Login" or "Register"
2. Enter your Zerodha credentials
3. Click "Start Trading"

### Step 4: Monitor in Real-Time
The dashboard shows:
- **Current Position**: Entry price, target, SL
- **Market Data**: Current price, VWAP, change %
- **P&L**: Running profit/loss
- **Orders**: Entry, target, stop-loss status
- **History**: Past trades and stats

### Step 5: Check Logs
```bash
# Bot logs appear in the terminal where bot_kite.py runs
# Example output:
# [09:15:23] - Starting bot...
# [09:15:45] - HDFCBANK: Price 1520.50 > VWAP 1490.20 (breakout!)
# [09:16:00] - ENTRY: BUY 250 @ 1520.50
# [09:16:15] - STOP LOSS: SL order placed @ 1510.00
# [09:20:30] - EXIT: Sell 250 @ 1541.00 (Profit: ₹5,125)
```

---

## 🛑 Stopping the Bot

**Option 1: Use Dashboard**
- Click "Stop Trading" button
- Bot exits active position
- Cancels pending orders

**Option 2: Keyboard Interrupt**
```bash
# In the bot terminal, press: Ctrl + C
```

**Option 3: Kill Process (Windows)**
```bash
taskkill /IM python.exe /F
```

---

## 🐛 Troubleshooting

### "Connection Refused" Error
```
Error: Failed to connect to Kite API
Solution: Check .env file has correct KITE_API_KEY and KITE_ACCESS_TOKEN
```

### "ModuleNotFoundError: No module named 'kiteconnect'"
```bash
# Install missing dependency
pip install kiteconnect -U
```

### "Port 5000 already in use"
```bash
# Kill existing process
lsof -ti:5000 | xargs kill -9  # Mac/Linux

# Windows: Find process using port 5000 and close it
# Or use different port: FLASK_PORT=5001 python app.py
```

### "Bot not placing orders"
1. Check **market hours** - Bot only runs 09:15 - 15:30 IST
2. Check **capital** - Sufficient margin available?
3. Check **API limits** - Zerodha may rate-limit requests
4. Check **symbol** - Is it in SYMBOLS_TO_MONITOR?

### "Getting incomplete data" 
- Zerodha has a **7-minute delay** on historical data
- Use **real-time subscription** for live quotes
- Check that your API key has **market data access**

---

## 📈 Performance Metrics

After running several trades, check:

**Dashboard Statistics:**
- Win Rate: % trades profitable
- Avg Profit: Average profit per trade
- Max Loss: Largest single loss
- Sharpe Ratio: Risk-adjusted returns

**View Trade History:**
```bash
# Query database
sqlite3 tradingbot.db "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10;"
```

---

## 🔒 Security Notes

1. **Never commit .env file** - Credentials exposed!
2. **Use environment variables** - Load from .env at startup
3. **Encrypt tokens in production** - Don't store plaintext
4. **API rate limits** - Zerodha: 180 requests/min
5. **Paper trading first** - Test with dummy capital before live trading

---

## 📚 Understanding the Code

### bot_kite.py - Core Trading Logic
```python
class KiteApp:
    def __init__(self):
        # Initialize Kite API connection
        
    def check_breakout(self):
        # Fetch OHLC data
        # Calculate VWAP
        # Check if price > VWAP + buffer
        
    def place_entry_order(self):
        # Calculate quantity based on capital
        # Place BUY order at breakout price
        # Place SL order 1.5x risk below
        
    def check_targets(self):
        # Monitor if profit target hit
        # Execute SELL order
        # Or handle stop-loss
```

### app.py - Backend API
```python
@app.route('/api/start-bot', methods=['POST'])
def start_bot():
    # Authenticate user
    # Start KiteApp instance
    # Return status
    
@app.route('/api/orders', methods=['GET'])
def get_orders():
    # Query database
    # Return active orders
```

### App.jsx - Frontend Dashboard
```jsx
function Dashboard() {
    // Fetch real-time data from API
    // Display position, P&L, market data
    // Handle buy/sell buttons
    // Show live logs
}
```

---

## 🚀 Next Steps

1. **Test with paper trading** - Use minimal capital first
2. **Monitor for 1 week** - Check if strategy is profitable
3. **Optimize parameters** - Adjust buffer, targets based on results
4. **Add more symbols** - Increase opportunities
5. **Scale up capital** - Increase leverage gradually

---

## 📞 Support & Issues

- **API Issues**: Check [Kite Connect Docs](https://kite.trade/docs/connect/v3/)
- **Database Issues**: Reset `tradingbot.db` and restart
- **Frontend Bugs**: Check browser console (F12) for errors
- **Bot Logic**: Review logs in terminal

---

## 📝 License

Personal use only. Do not redistribute without permission.

---

## ⚠️ Disclaimer

This bot is for **educational purposes** only. 

**Trading Risks:**
- Markets are unpredictable
- Leverage amplifies losses
- Past performance ≠ future results
- Use only capital you can afford to lose
- Always set stop-loss orders
- Never trade on borrowed capital without understanding risks

**Always do your own research before trading.**

---

**Last Updated:** Feb 25, 2026  
**Version:** 1.0  
**Author:** Aayush Parikh
