import React, { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import './TradingMonitor.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:5000/api';
const POLL_INTERVAL_MS = 5000;
const MAX_LINE_POINTS = 120;
const MAX_CANDLE_POINTS = 80;

const toBaseSymbol = (symbol) => (symbol || '').split(':').pop();

const formatClock = (date) =>
  new Intl.DateTimeFormat('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);

const asNumber = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const updateLineSeries = (currentSeries, symbol, price, now) => {
  const existing = currentSeries[symbol] || [];
  const updated = [...existing, { ts: now.getTime(), time: formatClock(now), price }].slice(-MAX_LINE_POINTS);
  return { ...currentSeries, [symbol]: updated };
};

const updateCandles = (currentCandles, symbol, price, now) => {
  const existing = currentCandles[symbol] || [];
  const bucketTs = Math.floor(now.getTime() / POLL_INTERVAL_MS) * POLL_INTERVAL_MS;
  const label = formatClock(new Date(bucketTs));
  const last = existing[existing.length - 1];

  let updated;
  if (last && last.bucketTs === bucketTs) {
    updated = [
      ...existing.slice(0, -1),
      {
        ...last,
        high: Math.max(last.high, price),
        low: Math.min(last.low, price),
        close: price,
      },
    ];
  } else {
    updated = [
      ...existing,
      {
        bucketTs,
        time: label,
        open: price,
        high: price,
        low: price,
        close: price,
      },
    ];
  }

  return { ...currentCandles, [symbol]: updated.slice(-MAX_CANDLE_POINTS) };
};

const CandleChart = ({ candles }) => {
  if (!candles || candles.length === 0) {
    return <div className="chart-placeholder">Waiting for 15s candle data...</div>;
  }

  const points = candles.slice(-24);
  const highs = points.map((c) => c.high);
  const lows = points.map((c) => c.low);
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const range = Math.max(maxPrice - minPrice, 0.01);

  return (
    <div className="mini-candle-wrap">
      <div className="mini-candle-chart">
        {points.map((candle) => {
          const bodyTop = ((maxPrice - Math.max(candle.open, candle.close)) / range) * 100;
          const bodyBottom = ((maxPrice - Math.min(candle.open, candle.close)) / range) * 100;
          const wickTop = ((maxPrice - candle.high) / range) * 100;
          const wickBottom = ((maxPrice - candle.low) / range) * 100;
          const isBull = candle.close >= candle.open;

          return (
            <div key={`${candle.bucketTs}`} className="mini-candle-col" title={`${candle.time} O:${candle.open.toFixed(2)} H:${candle.high.toFixed(2)} L:${candle.low.toFixed(2)} C:${candle.close.toFixed(2)}`}>
              <div className="mini-candle-wick" style={{ top: `${wickTop}%`, bottom: `${wickBottom}%` }} />
              <div
                className={`mini-candle-body ${isBull ? 'bull' : 'bear'}`}
                style={{ top: `${bodyTop}%`, bottom: `${100 - bodyBottom}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mini-candle-footnote">15s candles • latest {points.length}</div>
    </div>
  );
};

const TradingMonitor = () => {
  const [watchlistData, setWatchlistData] = useState([]);
  const [positions, setPositions] = useState([]);
  const [lineSeries, setLineSeries] = useState({});
  const [candlesBySymbol, setCandlesBySymbol] = useState({});
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const [positionToExit, setPositionToExit] = useState(null);
  const [isExiting, setIsExiting] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchMonitorData = async () => {
    const now = new Date();
    try {
      const [watchRes, posRes, openTradesRes] = await Promise.all([
        fetch(`${API_BASE_URL}/market/watchlist`),
        fetch(`${API_BASE_URL}/portfolio/positions`),
        fetch(`${API_BASE_URL}/analytics/trades?status=OPEN&limit=100`),
      ]);

      if (!watchRes.ok) {
        throw new Error('Unable to fetch watchlist data');
      }

      const watchPayload = await watchRes.json();
      const watchSymbols = watchPayload.symbols || [];
      setWatchlistData(watchSymbols);

      const positionsPayload = posRes.ok ? await posRes.json() : { positions: [] };
      const openTradePayload = openTradesRes.ok ? await openTradesRes.json() : { trades: [] };

      const rawPositions = (positionsPayload.positions || []).filter((p) => asNumber(p.quantity) !== 0);

      // Show all positions from portfolio (live from Kite), don't filter by trades
      // (trades table might have logging delays or gaps)
      const monitorPositions = rawPositions;

      const enriched = monitorPositions.map((position) => {
        const symbol = toBaseSymbol(position.symbol);
        const exchange = position.exchange || 'NSE';
        const watchMatch = watchSymbols.find((item) => item.symbol === symbol && (!item.exchange || item.exchange === exchange))
          || watchSymbols.find((item) => item.symbol === symbol);

        const qty = asNumber(position.quantity);
        const avgPrice = asNumber(position.average_price);
        const currentPrice = asNumber(watchMatch?.last_price, asNumber(position.last_price, avgPrice));
        const side = qty >= 0 ? 'LONG' : 'SHORT';
        const absQty = Math.abs(qty);
        const estimatedPnl = side === 'LONG'
          ? (currentPrice - avgPrice) * absQty
          : (avgPrice - currentPrice) * absQty;
        const pnl = Number.isFinite(asNumber(position.pnl, NaN)) ? asNumber(position.pnl) : estimatedPnl;
        const notional = avgPrice * absQty;
        const pnlPercent = notional > 0 ? (pnl / notional) * 100 : 0;

        return {
          ...position,
          symbol,
          exchange,
          displaySymbol: `${exchange}:${symbol}`,
          side,
          absQty,
          currentPrice,
          avgPrice,
          pnl,
          pnlPercent,
          buyTrigger: asNumber(watchMatch?.trading_levels?.buy_trigger, null),
          sellTrigger: asNumber(watchMatch?.trading_levels?.sell_trigger, null),
        };
      });

      setPositions(enriched);

      setLineSeries((prev) => {
        let next = { ...prev };
        enriched.forEach((pos) => {
          next = updateLineSeries(next, pos.displaySymbol, pos.currentPrice, now);
        });
        return next;
      });

      setCandlesBySymbol((prev) => {
        let next = { ...prev };
        enriched.forEach((pos) => {
          next = updateCandles(next, pos.displaySymbol, pos.currentPrice, now);
        });
        return next;
      });

      setLastUpdated(now);
      setError('');
    } catch (err) {
      setError(err.message || 'Failed to fetch monitor data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMonitorData();
    const interval = setInterval(fetchMonitorData, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const openPositionSymbols = useMemo(
    () => new Set(positions.map((position) => position.symbol)),
    [positions]
  );

  const summary = useMemo(() => {
    const totalPnl = positions.reduce((sum, position) => sum + position.pnl, 0);
    const totalExposure = positions.reduce((sum, position) => sum + (position.avgPrice * position.absQty), 0);
    return {
      count: positions.length,
      totalPnl,
      exposure: totalExposure,
    };
  }, [positions]);

  const requestManualExit = (position) => {
    setPositionToExit(position);
    setShowExitConfirm(true);
  };

  const handleManualExit = async () => {
    if (!positionToExit) {
      return;
    }

    setIsExiting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/manual-exit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: positionToExit.displaySymbol,
          quantity: Math.abs(positionToExit.quantity),
          price: positionToExit.currentPrice,
        }),
      });

      if (response.ok) {
        setShowExitConfirm(false);
        setPositionToExit(null);
        await fetchMonitorData();
      } else {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || 'Failed to close position');
      }
    } catch (err) {
      alert('Error closing position: ' + err.message);
    } finally {
      setIsExiting(false);
    }
  };

  if (loading) return <div className="trading-monitor"><p>Loading market data...</p></div>;
  if (error) return <div className="trading-monitor"><p className="error">Error: {error}</p></div>;

  return (
    <div className="trading-monitor">
      <div className="monitor-header">
        <h1>🎯 Trade Monitor</h1>
        <div className="header-stats">
          <div className="header-chip">
            <span className="chip-label">Open Positions</span>
            <span className="chip-value">{summary.count}</span>
          </div>
          <div className="header-chip">
            <span className="chip-label">Open P&L</span>
            <span className={`chip-value ${summary.totalPnl >= 0 ? 'profit' : 'loss'}`}>
              ₹{summary.totalPnl.toFixed(2)}
            </span>
          </div>
          <div className="header-chip">
            <span className="chip-label">Exposure</span>
            <span className="chip-value">₹{summary.exposure.toFixed(2)}</span>
          </div>
          <div className="header-chip time-chip">
            <span className="chip-label">Last Refresh</span>
            <span className="chip-value">{lastUpdated ? formatClock(lastUpdated) : '--:--:--'}</span>
          </div>
        </div>
      </div>

      <div className="triggers-section">
        <h2>📍 Watchlist & Triggers</h2>
        <div className="triggers-grid">
          {Array.isArray(watchlistData) && watchlistData.map((symbol) => (
            <div key={symbol.symbol} className={`trigger-card ${openPositionSymbols.has(symbol.symbol) ? 'active-symbol' : ''}`}>
              <div className="card-header">
                <h3>{symbol.symbol}</h3>
                {openPositionSymbols.has(symbol.symbol) && <span className="badge">IN POSITION</span>}
              </div>
              <div className="card-body">
                <div className="price-display">
                  <span className="current-price">₹{symbol.last_price.toFixed(2)}</span>
                  <span className={`change ${symbol.price_change >= 0 ? 'positive' : 'negative'}`}>
                    {symbol.price_change >= 0 ? '📈' : '📉'} {Math.abs(symbol.price_change).toFixed(2)}
                  </span>
                </div>
                <div className="trigger-display">
                  <div className="trigger-item long">
                    <span>🟢 Long</span>
                    <span className="trigger-price">₹{symbol.trading_levels?.buy_trigger?.toFixed(2) || 'N/A'}</span>
                  </div>
                  <div className="trigger-item short">
                    <span>🔴 Short</span>
                    <span className="trigger-price">₹{symbol.trading_levels?.sell_trigger?.toFixed(2) || 'N/A'}</span>
                  </div>
                </div>
                <div className="ohlc">
                  <span>O: ₹{symbol.ohlc?.open?.toFixed(2) || 'N/A'}</span>
                  <span>H: ₹{symbol.ohlc?.high?.toFixed(2) || 'N/A'}</span>
                  <span>L: ₹{symbol.ohlc?.low?.toFixed(2) || 'N/A'}</span>
                  <span>C: ₹{symbol.ohlc?.close?.toFixed(2) || 'N/A'}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="positions-section">
        <h2>📊 Live Bot Positions (15s)</h2>

        {positions.length === 0 && (
          <div className="no-position">
            <p>No open bot positions right now. This section updates automatically every 15 seconds.</p>
          </div>
        )}

        {positions.length > 0 && (
          <div className="positions-grid">
            {positions.map((position) => {
              const series = lineSeries[position.displaySymbol] || [];
              const candles = candlesBySymbol[position.displaySymbol] || [];

              return (
                <div className="position-card" key={position.displaySymbol}>
                  <div className="position-top">
                    <div>
                      <h3>{position.displaySymbol}</h3>
                      <div className="position-meta">
                        <span className={`side-badge ${position.side === 'LONG' ? 'long' : 'short'}`}>{position.side}</span>
                        <span>Qty: {position.absQty}</span>
                        <span>Entry: ₹{position.avgPrice.toFixed(2)}</span>
                        <span>LTP: ₹{position.currentPrice.toFixed(2)}</span>
                      </div>
                    </div>
                    <div className="position-actions">
                      <div className={`position-pnl ${position.pnl >= 0 ? 'profit' : 'loss'}`}>
                        ₹{position.pnl.toFixed(2)} ({position.pnlPercent.toFixed(2)}%)
                      </div>
                      <button className="exit-btn" onClick={() => requestManualExit(position)}>Manual Exit</button>
                    </div>
                  </div>

                  <div className="position-levels">
                    <span>🟢 Trigger: {position.buyTrigger ? `₹${position.buyTrigger.toFixed(2)}` : 'N/A'}</span>
                    <span>🔴 Trigger: {position.sellTrigger ? `₹${position.sellTrigger.toFixed(2)}` : 'N/A'}</span>
                  </div>

                  <div className="position-charts">
                    <div className="chart-card">
                      <div className="chart-title">15s Line</div>
                      <ResponsiveContainer width="100%" height={170}>
                        <LineChart data={series}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                          <XAxis dataKey="time" hide />
                          <YAxis domain={['auto', 'auto']} width={55} tick={{ fill: '#a6b0cf', fontSize: 11 }} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#111827', border: '1px solid #25314d' }}
                            formatter={(value) => [`₹${asNumber(value).toFixed(2)}`, 'Price']}
                          />
                          <ReferenceLine y={position.avgPrice} stroke="#f59e0b" strokeDasharray="4 4" />
                          <Line type="monotone" dataKey="price" stroke="#38bdf8" strokeWidth={2} dot={false} isAnimationActive={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    <div className="chart-card">
                      <div className="chart-title">15s Candles</div>
                      <CandleChart candles={candles} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showExitConfirm && positionToExit && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3>Confirm Manual Exit</h3>
            <p>Close {positionToExit.displaySymbol} at current market price?</p>
            <div className="modal-summary">
              <p><strong>Side:</strong> {positionToExit.side}</p>
              <p><strong>Quantity:</strong> {positionToExit.absQty}</p>
              <p><strong>Current Price:</strong> ₹{positionToExit.currentPrice.toFixed(2)}</p>
              <p className={positionToExit.pnl >= 0 ? 'profit' : 'loss'}>
                <strong>Open P&L:</strong> ₹{positionToExit.pnl.toFixed(2)} ({positionToExit.pnlPercent.toFixed(2)}%)
              </p>
            </div>
            <div className="modal-buttons">
              <button className="confirm-btn" onClick={handleManualExit} disabled={isExiting}>
                {isExiting ? 'Exiting...' : 'Confirm Exit'}
              </button>
              <button
                className="cancel-btn"
                onClick={() => {
                  setShowExitConfirm(false);
                  setPositionToExit(null);
                }}
                disabled={isExiting}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TradingMonitor;
