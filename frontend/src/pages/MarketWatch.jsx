import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './MarketWatch.css';

const MarketWatch = () => {
  const navigate = useNavigate();
  const [watchlistData, setWatchlistData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    fetchWatchlistData();
    const interval = setInterval(fetchWatchlistData, 3000); // Update every 3 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchWatchlistData = async () => {
    try {
      const response = await fetch('/api/market/watchlist');
      const data = await response.json();
      
      if (data.success) {
        setWatchlistData(data.symbols);
        setLastUpdate(new Date(data.timestamp));
        setError(null);
      } else {
        setError(data.error || 'Failed to fetch market data');
      }
    } catch (err) {
      setError('Failed to connect to server');
      console.error('Error fetching watchlist:', err);
    } finally {
      setLoading(false);
    }
  };

  const getPriceColor = (change) => {
    if (change > 0) return 'positive';
    if (change < 0) return 'negative';
    return 'neutral';
  };

  const getSignalStatus = (symbol) => {
    const lastPrice = symbol.last_price;
    const buyTrigger = symbol.trading_levels.buy_trigger;
    const sellTrigger = symbol.trading_levels.sell_trigger;
    
    if (lastPrice > buyTrigger) {
      return { text: '🟢 LONG SIGNAL', class: 'signal-long' };
    } else if (lastPrice < sellTrigger) {
      return { text: '🔴 SHORT SIGNAL', class: 'signal-short' };
    } else {
      return { text: '⚪ NEUTRAL', class: 'signal-neutral' };
    }
  };

  if (loading) {
    return (
      <div className="market-watch-page">
        <div className="page-header">
          <button className="back-btn" onClick={() => navigate('/dashboard')}>
            ← Back to Dashboard
          </button>
          <h1>📈 Market Watch</h1>
        </div>
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading market data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="market-watch-page">
        <div className="page-header">
          <button className="back-btn" onClick={() => navigate('/dashboard')}>
            ← Back to Dashboard
          </button>
          <h1>📈 Market Watch</h1>
        </div>
        <div className="error-container">
          <div className="error-icon">⚠️</div>
          <h3>Error Loading Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={fetchWatchlistData}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="market-watch-page">
      <div className="page-header">
        <button className="back-btn" onClick={() => navigate('/dashboard')}>
          ← Back to Dashboard
        </button>
        <h1>📈 Market Watch</h1>
        <div className="header-info">
          <p className="subtitle">Real-time monitoring of all tracked symbols</p>
          {lastUpdate && (
            <p className="last-update">
              Last updated: {lastUpdate.toLocaleTimeString()}
            </p>
          )}
        </div>
      </div>

      <div className="watchlist-summary">
        <div className="summary-card">
          <div className="summary-icon">📊</div>
          <div className="summary-content">
            <h3>{watchlistData.length}</h3>
            <p>Total Symbols</p>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon">🟢</div>
          <div className="summary-content">
            <h3>{watchlistData.filter(s => s.price_change > 0).length}</h3>
            <p>Gainers</p>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon">🔴</div>
          <div className="summary-content">
            <h3>{watchlistData.filter(s => s.price_change < 0).length}</h3>
            <p>Losers</p>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon">⚡</div>
          <div className="summary-content">
            <h3>
              {watchlistData.filter(s => 
                s.last_price > s.trading_levels.buy_trigger || 
                s.last_price < s.trading_levels.sell_trigger
              ).length}
            </h3>
            <p>Active Signals</p>
          </div>
        </div>
      </div>

      <div className="watchlist-container">
        {watchlistData.map((symbol, index) => {
          const signal = getSignalStatus(symbol);
          const priceClass = getPriceColor(symbol.price_change);

          return (
            <div key={index} className="symbol-card">
              <div className="symbol-header">
                <div className="symbol-info">
                  <h3 className="symbol-name">{symbol.symbol}</h3>
                  <span className="exchange-badge">{symbol.exchange}</span>
                </div>
                <div className={`signal-badge ${signal.class}`}>
                  {signal.text}
                </div>
              </div>

              <div className="price-section">
                <div className="current-price">
                  <span className="label">Current Price</span>
                  <span className={`price ${priceClass}`}>
                    ₹{symbol.last_price?.toFixed(2)}
                  </span>
                </div>
                <div className="price-change">
                  <span className={`change ${priceClass}`}>
                    {symbol.price_change > 0 ? '+' : ''}
                    ₹{symbol.price_change?.toFixed(2)}
                  </span>
                  <span className={`change-percent ${priceClass}`}>
                    ({symbol.price_change_percent > 0 ? '+' : ''}
                    {symbol.price_change_percent?.toFixed(2)}%)
                  </span>
                </div>
              </div>

              <div className="ohlc-section">
                <div className="ohlc-item">
                  <span className="ohlc-label">Open</span>
                  <span className="ohlc-value">₹{symbol.ohlc.open?.toFixed(2)}</span>
                </div>
                <div className="ohlc-item high">
                  <span className="ohlc-label">High</span>
                  <span className="ohlc-value">₹{symbol.ohlc.high?.toFixed(2)}</span>
                </div>
                <div className="ohlc-item low">
                  <span className="ohlc-label">Low</span>
                  <span className="ohlc-value">₹{symbol.ohlc.low?.toFixed(2)}</span>
                </div>
                <div className="ohlc-item">
                  <span className="ohlc-label">Volume</span>
                  <span className="ohlc-value">
                    {(symbol.volume / 1000).toFixed(1)}K
                  </span>
                </div>
              </div>

              <div className="triggers-section">
                <h4>Trading Triggers</h4>
                <div className="trigger-row">
                  <div className="trigger-item buy">
                    <span className="trigger-label">🟢 Buy Trigger</span>
                    <span className="trigger-value">
                      ₹{symbol.trading_levels.buy_trigger?.toFixed(2)}
                    </span>
                  </div>
                  <div className="trigger-item sell">
                    <span className="trigger-label">🔴 Sell Trigger</span>
                    <span className="trigger-value">
                      ₹{symbol.trading_levels.sell_trigger?.toFixed(2)}
                    </span>
                  </div>
                </div>
                <div className="buffer-info">
                  Buffer: ₹{symbol.trading_levels.buffer}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="auto-refresh-indicator">
        <span className="pulse-dot"></span>
        Auto-refreshing every 3 seconds
      </div>
    </div>
  );
};

export default MarketWatch;
