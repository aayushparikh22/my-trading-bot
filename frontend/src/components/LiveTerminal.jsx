import React, { useState, useEffect, useRef } from 'react';
import './LiveTerminal.css';

const LiveTerminal = ({ botStatus, botRunning }) => {
  const [logs, setLogs] = useState([]);
  const [trades, setTrades] = useState([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [watchlistData, setWatchlistData] = useState([]);
  const terminalRef = useRef(null);
  const [filter, setFilter] = useState('all'); // all, trades, info, error
  
  // Manual trading state
  const [manualTradeType, setManualTradeType] = useState('BUY');
  const [manualSymbol, setManualSymbol] = useState('');
  const [manualQuantity, setManualQuantity] = useState('');
  const [manualEntryPrice, setManualEntryPrice] = useState('');
  const [manualSLPercent, setManualSLPercent] = useState('0.5');
  const [manualTPRatio, setManualTPRatio] = useState('2.0');
  const [submittingOrder, setSubmittingOrder] = useState(false);

  // Fetch live market data for all symbols
  useEffect(() => {
    const fetchMarketData = async () => {
      try {
        const response = await fetch('/api/market/watchlist');
        const data = await response.json();
        if (data.success && data.symbols) {
          setWatchlistData(data.symbols);
        }
      } catch (error) {
        console.error('Error fetching market data:', error);
      }
    };

    fetchMarketData();
    const interval = setInterval(fetchMarketData, 3000); // Update every 3 seconds
    return () => clearInterval(interval);
  }, []);

  // Fetch logs periodically
  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/api/logs?limit=100');
        const data = await response.json();
        if (data.logs) {
          setLogs(data.logs.reverse());
          
          // Filter trades from logs
          const tradeLogs = data.logs.filter(l => l.log_type === 'TRADE');
          setTrades(tradeLogs);
        }
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    fetchLogs();
    const interval = setInterval(fetchLogs, 2000); // Refresh every 2 seconds for real-time feel
    return () => clearInterval(interval);
  }, [botRunning]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Filter logs
  const filteredLogs = logs.filter(log => {
    if (filter === 'all') return true;
    if (filter === 'trades') return log.log_type === 'TRADE' || log.message.includes('TRADE');
    if (filter === 'info') return log.log_level === 'INFO';
    if (filter === 'error') return log.log_level === 'ERROR' || log.log_level === 'WARNING';
    return true;
  });

  const getLogStyle = (log) => {
    if (log.log_level === 'ERROR' || log.log_level === 'CRITICAL') {
      return 'log-error';
    }
    if (log.log_level === 'WARNING') {
      return 'log-warning';
    }
    if (log.log_type === 'TRADE') {
      return 'log-trade';
    }
    if (log.message.includes('✓') || log.message.includes('✅')) {
      return 'log-success';
    }
    return 'log-info';
  };

  const formatLogMessage = (log) => {
    const time = new Date(log.timestamp).toLocaleTimeString();
    return `[${time}] ${log.message}`;
  };

  // Handle manual trade submission
  const handleManualTrade = async () => {
    if (!manualSymbol || manualSymbol.trim() === '') {
      alert('Please select or enter a stock symbol (e.g., NSE:BAJAJFINSV)');
      return;
    }

    if (!manualQuantity || manualQuantity <= 0) {
      alert('Please enter a valid quantity');
      return;
    }

    const entryPrice = manualEntryPrice || (watchlistData.length > 0 ? watchlistData[0].last_price : null);
    if (!entryPrice) {
      alert('Entry price not available. Please enter manually or wait for market data.');
      return;
    }

    setSubmittingOrder(true);
    
    try {
      const response = await fetch('/api/manual-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trade_type: manualTradeType,
          symbol: manualSymbol,
          quantity: parseInt(manualQuantity),
          entry_price: parseFloat(entryPrice),
          sl_percent: parseFloat(manualSLPercent),
          tp_ratio: parseFloat(manualTPRatio)
        })
      });

      const data = await response.json();
      
      if (response.ok) {
        alert(`${manualTradeType} order placed successfully!\nStock: ${manualSymbol}\nEntry: ₹${entryPrice}\nSL: ₹${data.sl_price?.toFixed(2)}\nTP: ₹${data.tp_price?.toFixed(2)}`);
        // Reset form
        setManualSymbol('');
        setManualQuantity('');
        setManualEntryPrice('');
      } else {
        alert(`Error: ${data.error || 'Failed to place order'}`);
      }
    } catch (error) {
      alert(`Error placing order: ${error.message}`);
    } finally {
      setSubmittingOrder(false);
    }
  };

  return (
    <div className="live-terminal">
      <div className="terminal-header">
        <div className="terminal-title">
          <span className="terminal-icon">📡</span>
          <span>Live Trading Terminal</span>
          <span className={`status-indicator ${botRunning ? 'running' : 'stopped'}`}>
            {botRunning ? '● Running' : '○ Stopped'}
          </span>
        </div>
        
        <div className="terminal-controls">
          <div className="filter-buttons">
            <button 
              className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All ({logs.length})
            </button>
            <button 
              className={`filter-btn ${filter === 'trades' ? 'active' : ''}`}
              onClick={() => setFilter('trades')}
            >
              Trades ({trades.length})
            </button>
            <button 
              className={`filter-btn ${filter === 'info' ? 'active' : ''}`}
              onClick={() => setFilter('info')}
            >
              Info
            </button>
            <button 
              className={`filter-btn ${filter === 'error' ? 'active' : ''}`}
              onClick={() => setFilter('error')}
            >
              Errors
            </button>
          </div>
          
          <label className="auto-scroll-toggle">
            <input 
              type="checkbox" 
              checked={autoScroll} 
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            <span>Auto-scroll</span>
          </label>
        </div>
      </div>

      {/* Manual Trading Section */}
      <div className="manual-trading-section">
        <div className="section-header">
          <span className="section-icon">✋</span>
          <span className="section-title">Manual Trade Entry</span>
          <span className="section-hint">(Auto SL & TP with OCO)</span>
        </div>
        <div className="manual-trade-form">
          <div className="trade-type-selector">
            <button 
              className={`type-btn buy ${manualTradeType === 'BUY' ? 'active' : ''}`}
              onClick={() => setManualTradeType('BUY')}
            >
              🟢 BUY
            </button>
            <button 
              className={`type-btn sell ${manualTradeType === 'SELL' ? 'active' : ''}`}
              onClick={() => setManualTradeType('SELL')}
            >
              🔴 SELL
            </button>
          </div>

          <div className="form-row">
            <div className="form-field">
              <label>Stock Symbol</label>
              <select 
                value={manualSymbol}
                onChange={(e) => setManualSymbol(e.target.value)}
              >
                <option value="">Select or Type Below...</option>
                {watchlistData.map(symbol => (
                  <option key={symbol.symbol} value={`NSE:${symbol.symbol}`}>
                    {symbol.symbol} (₹{symbol.last_price?.toFixed(2)})
                  </option>
                ))}
              </select>
              <input 
                type="text" 
                placeholder="e.g., NSE:BAJAJFINSV"
                value={manualSymbol}
                onChange={(e) => setManualSymbol(e.target.value)}
                style={{ marginTop: '8px' }}
              />
            </div>
          </div>
          
          <div className="form-row">
            <div className="form-field">
              <label>Quantity</label>
              <input 
                type="number" 
                placeholder="e.g., 10"
                value={manualQuantity}
                onChange={(e) => setManualQuantity(e.target.value)}
                min="1"
              />
            </div>
            
            <div className="form-field">
              <label>Entry Price (₹)</label>
              <input 
                type="number" 
                placeholder="Market Price"
                value={manualEntryPrice}
                onChange={(e) => setManualEntryPrice(e.target.value)}
                step="0.01"
              />
            </div>
          </div>
          
          <div className="form-row">
            <div className="form-field">
              <label>SL % (Stop Loss)</label>
              <input 
                type="number" 
                value={manualSLPercent}
                onChange={(e) => setManualSLPercent(e.target.value)}
                step="0.1"
                min="0.1"
              />
            </div>
            
            <div className="form-field">
              <label>TP Ratio (Risk:Reward)</label>
              <input 
                type="number" 
                value={manualTPRatio}
                onChange={(e) => setManualTPRatio(e.target.value)}
                step="0.5"
                min="0.5"
              />
            </div>
          </div>
          
          <button 
            className={`submit-trade-btn ${manualTradeType.toLowerCase()}`}
            onClick={handleManualTrade}
            disabled={submittingOrder || !manualQuantity || !manualSymbol}
          >
            {submittingOrder ? '⏳ Placing Order...' : `${manualTradeType === 'BUY' ? '🟢' : '🔴'} Place ${manualTradeType} Order`}
          </button>
        </div>
      </div>

      {/* Live Price Monitor for All Symbols */}
      {watchlistData.length > 0 && (
        <div className="price-monitor">
          <div className="monitor-warning">
            ⚠️ These are LIVE triggers (updating). Bot uses FIXED triggers from 9:15-9:30 AM candle.
          </div>
          <div className="symbols-grid">
            {watchlistData.map((symbol, index) => {
              const priceChangeClass = symbol.price_change > 0 ? 'positive' : symbol.price_change < 0 ? 'negative' : 'neutral';
              const signalStatus = symbol.last_price > symbol.trading_levels.buy_trigger ? 'long' : 
                                   symbol.last_price < symbol.trading_levels.sell_trigger ? 'short' : 'neutral';
              
              return (
                <div key={index} className="symbol-card-compact">
                  <div className="symbol-header-compact">
                    <div className="symbol-name-compact">
                      <strong>{symbol.symbol}</strong>
                      <span className="exchange-text">{symbol.exchange}</span>
                    </div>
                    {signalStatus !== 'neutral' && (
                      <div className={`signal-dot ${signalStatus}`}>
                        {signalStatus === 'long' ? '🟢' : '🔴'}
                      </div>
                    )}
                  </div>
                  
                  <div className="price-main">
                    <div className="current-price-compact">
                      ₹{symbol.last_price?.toFixed(2)}
                    </div>
                    <div className={`price-change-compact ${priceChangeClass}`}>
                      {symbol.price_change > 0 ? '+' : ''}₹{symbol.price_change?.toFixed(2)}
                      ({symbol.price_change_percent > 0 ? '+' : ''}{symbol.price_change_percent?.toFixed(2)}%)
                    </div>
                  </div>
                  
                  <div className="ohlc-compact">
                    <div className="ohlc-row">
                      <span>O: ₹{symbol.ohlc.open?.toFixed(2)}</span>
                      <span className="high-text">H: ₹{symbol.ohlc.high?.toFixed(2)}</span>
                    </div>
                    <div className="ohlc-row">
                      <span className="low-text">L: ₹{symbol.ohlc.low?.toFixed(2)}</span>
                      <span>V: {(symbol.volume / 1000).toFixed(0)}K</span>
                    </div>
                  </div>
                  
                  <div className="triggers-compact">
                    <div className="trigger-line buy-line">
                      <span className="trigger-icon">🟢</span>
                      <span className="trigger-text">₹{symbol.trading_levels.buy_trigger?.toFixed(2)}</span>
                    </div>
                    <div className="trigger-line sell-line">
                      <span className="trigger-icon">🔴</span>
                      <span className="trigger-text">₹{symbol.trading_levels.sell_trigger?.toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="terminal-body" ref={terminalRef}>
        {filteredLogs.length === 0 ? (
          <div className="terminal-empty">
            <p>No logs to display</p>
            <p className="text-muted">Start the bot to see live trading activity</p>
          </div>
        ) : (
          filteredLogs.map((log, index) => (
            <div key={index} className={`terminal-line ${getLogStyle(log)}`}>
              {formatLogMessage(log)}
            </div>
          ))
        )}
      </div>

      <div className="terminal-stats">
        <div className="stat">
          <span className="stat-label">Total Logs:</span>
          <span className="stat-value">{logs.length}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Trades Recorded:</span>
          <span className="stat-value">{trades.length}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Last Update:</span>
          <span className="stat-value">{new Date().toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
};

export default LiveTerminal;
