import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { botAPI, analyticsAPI, configAPI, kiteAPI } from '../services/api';
import './Dashboard.css';

const Dashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [botStatus, setBotStatus] = useState(null);
  const [todayStats, setTodayStats] = useState(null);
  const [weeklyStats, setWeeklyStats] = useState(null);
  const [performanceStats, setPerformanceStats] = useState(null);
  const [botRunning, setBotRunning] = useState(false);
  const [config, setConfig] = useState(null);
  const [refreshInterval, setRefreshInterval] = useState(5000);
  const [toast, setToast] = useState(null);
  const oauthPollRef = useRef(null);
  
  // Settings modal state
  const [showSettings, setShowSettings] = useState(false);
  const [settingsData, setSettingsData] = useState({
    kite_api_key: '',
    kite_access_token: '',
    zerodha_user_id: '',
  });
  const [savingSettings, setSavingSettings] = useState(false);

  const showToast = (message, type = 'info') => {
    setToast({ message, type, id: Date.now() });
  };

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [status, today, weekly, performance] = await Promise.all([
          botAPI.status(),
          analyticsAPI.today(),
          analyticsAPI.weekly(),
          analyticsAPI.performance(),
        ]);

        setBotStatus(status.data);
        setTodayStats(today.data);
        setWeeklyStats(weekly.data);
        setPerformanceStats(performance.data);
        // Consider READY and RUNNING as active states
        setBotRunning(status.data?.status === 'RUNNING' || status.data?.status === 'READY');
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  // Separate effect to fetch config when modal opens
  useEffect(() => {
    if (showSettings) {
      const fetchConfig = async () => {
        try {
          const cfg = await configAPI.getConfig();
          if (cfg.data) {
            setConfig(cfg.data);
            setSettingsData({
              kite_api_key: cfg.data.kite_api_key || '',
              kite_access_token: cfg.data.kite_access_token || '',
              zerodha_user_id: cfg.data.zerodha_user_id || '',
            });
          }
        } catch (error) {
          console.error('Error fetching config:', error);
        }
      };
      fetchConfig();
    }
  }, [showSettings]);

  const handleStartBot = async () => {
    try {
      await botAPI.start();
      setBotRunning(true);
    } catch (error) {
      alert('Failed to start bot: ' + (error.response?.data?.error || error.message));
    }
  };

  const handleStopBot = async () => {
    try {
      await botAPI.stop();
      setBotRunning(false);
    } catch (error) {
      alert('Failed to stop bot: ' + (error.response?.data?.error || error.message));
    }
  };

  const handleSettingsChange = (e) => {
    const { name, value } = e.target;
    setSettingsData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      const updatePayload = {
        kite: {
          api_key: settingsData.kite_api_key,
          access_token: settingsData.kite_access_token,
          zerodha_user_id: settingsData.zerodha_user_id,
        }
      };
      await configAPI.updateConfig(updatePayload);
      alert('Kite API credentials saved successfully!');
      setShowSettings(false);
    } catch (error) {
      alert('Failed to save credentials: ' + (error.response?.data?.error || error.message));
    } finally {
      setSavingSettings(false);
    }
  };

  const startOAuthPolling = () => {
    if (oauthPollRef.current) {
      clearInterval(oauthPollRef.current);
    }

    let attempts = 0;
    const maxAttempts = 30;
    oauthPollRef.current = setInterval(async () => {
      attempts += 1;
      try {
        const cfg = await configAPI.getConfig();
        const accessToken = cfg.data?.kite_access_token;
        if (accessToken) {
          setConfig(cfg.data);
          setSettingsData({
            kite_api_key: cfg.data.kite_api_key || '',
            kite_access_token: cfg.data.kite_access_token || '',
            zerodha_user_id: cfg.data.zerodha_user_id || '',
          });
          showToast('Kite access token updated!', 'success');
          clearInterval(oauthPollRef.current);
          oauthPollRef.current = null;
          return;
        }
      } catch (error) {
        if (attempts === 1) {
          showToast('Waiting for Kite OAuth...', 'info');
        }
      }

      if (attempts >= maxAttempts) {
        clearInterval(oauthPollRef.current);
        oauthPollRef.current = null;
        showToast('Timed out waiting for OAuth. Try again.', 'error');
      }
    }, 2000);
  };

  const handleKiteLogin = async () => {
    try {
      const response = await kiteAPI.login();
      const loginUrl = response.data?.login_url;
      if (!loginUrl) {
        showToast('Kite login URL not available. Save your API key first.', 'error');
        return;
      }
      window.open(loginUrl, '_blank', 'noopener,noreferrer');
      showToast('Kite login opened. Complete OAuth in the new tab.', 'info');
      startOAuthPolling();
    } catch (error) {
      showToast('Failed to get Kite login URL: ' + (error.response?.data?.error || error.message), 'error');
    }
  };

  if (loading) {
    return <div className="dashboard-loading">Loading...</div>;
  }

  return (
    <div className="dashboard-container">
      {toast && (
        <div className={`toast toast-${toast.type}`} key={toast.id}>
          {toast.message}
        </div>
      )}
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <h1>Trading Bot Dashboard</h1>
          <p className="header-subtitle">Daily Trading Analytics</p>
        </div>
        <div className="header-right">
          <button
            className="nav-btn"
            onClick={() => navigate('/market-watch')}
          >
            📈 Market Watch
          </button>
          <button
            className="nav-btn"
            onClick={() => navigate('/portfolio')}
          >
            📊 Portfolio
          </button>
          <button
            className="nav-btn"
            onClick={() => navigate('/terminal')}
          >
            💻 Terminal
          </button>
          <button
            className="nav-btn"
            onClick={() => navigate('/api-tester')}
          >
            🔧 API Tests
          </button>
          <button
            className="nav-btn"
            onClick={() => navigate('/trading-monitor')}
          >
            🎯 Monitor Trade
          </button>
          <button
            className={`bot-toggle ${botRunning ? 'running' : ''}`}
            onClick={botRunning ? handleStopBot : handleStartBot}
          >
            {botRunning ? '🔴 Stop Bot' : '🟢 Start Bot'}
          </button>
          <button className="config-btn" onClick={() => setShowSettings(true)}>
            ⚙️ Settings
          </button>
        </div>
      </header>

      {/* Status Cards */}
      <div className="status-cards">
        {/* Today's Status */}
        <div className="status-card">
          <h3>Today's Status</h3>
          <div className="status-content">
            <div className="status-item">
              <label>Bot Status</label>
              <span className={`status-badge ${botRunning ? 'running' : 'stopped'}`}>
                {botStatus?.status === 'READY' ? 'Ready (Standby)' : 
                 botStatus?.status === 'RUNNING' ? 'Running' : 
                 botStatus?.status === 'ERROR' ? 'Error' : 'Stopped'}
              </span>
            </div>
            <div className="status-item">
              <label>Total Trades</label>
              <span className="status-value">{todayStats?.summary?.total_trades || 0}</span>
            </div>
            <div className="status-item">
              <label>Today's P&L</label>
              <span className={`status-value ${
                (todayStats?.summary?.total_pnl || 0) >= 0 ? 'positive' : 'negative'
              }`}>
                ₹{((todayStats?.summary?.total_pnl || 0).toFixed(2))}
              </span>
            </div>
          </div>
        </div>

        {/* Weekly Summary */}
        <div className="status-card">
          <h3>Weekly Summary (Last 7 Days)</h3>
          <div className="status-content">
            <div className="status-item">
              <label>Trading Days</label>
              <span className="status-value">{weeklyStats?.summary?.total_trading_days || 0}</span>
            </div>
            <div className="status-item">
              <label>Total Trades</label>
              <span className="status-value">{weeklyStats?.summary?.total_trades || 0}</span>
            </div>
            <div className="status-item">
              <label>Weekly P&L</label>
              <span className={`status-value ${
                (weeklyStats?.summary?.total_pnl || 0) >= 0 ? 'positive' : 'negative'
              }`}>
                ₹{((weeklyStats?.summary?.total_pnl || 0).toFixed(2))}
              </span>
            </div>
          </div>
        </div>

        {/* Performance Stats */}
        <div className="status-card">
          <h3>Performance (30 Days)</h3>
          <div className="status-content">
            <div className="status-item">
              <label>Win Rate</label>
              <span className="status-value">{(performanceStats?.win_rate || 0).toFixed(1)}%</span>
            </div>
            <div className="status-item">
              <label>Profit Factor</label>
              <span className="status-value">{(performanceStats?.profit_factor || 0).toFixed(2)}</span>
            </div>
            <div className="status-item">
              <label>Best Trade</label>
              <span className={`status-value ${(performanceStats?.best_trade || 0) >= 0 ? 'positive' : 'negative'}`}>
                ₹{((performanceStats?.best_trade || 0).toFixed(2))}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Charts Section */}
      <div className="charts-section">
        {/* Daily P&L Chart */}
        <div className="chart-container">
          <h3>Daily P&L (Last 7 Days)</h3>
          {weeklyStats?.daily_stats && weeklyStats.daily_stats.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={weeklyStats.daily_stats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="stats_date"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(date) => {
                    const d = new Date(date);
                    return `${d.getMonth() + 1}/${d.getDate()}`;
                  }}
                />
                <YAxis />
                <Tooltip
                  contentStyle={{ backgroundColor: '#f9fafb', border: '1px solid #e5e7eb' }}
                  formatter={(value) => `₹${value.toFixed(2)}`}
                />
                <Legend />
                <Bar dataKey="total_pnl" fill="#667eea" name="Daily P&L" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="no-data">No trading data available</p>
          )}
        </div>

        {/* Win/Loss Pie Chart */}
        <div className="chart-container">
          <h3>Win/Loss Distribution (30 Days)</h3>
          {performanceStats && performanceStats.total_trades > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={[
                    { name: 'Wins', value: performanceStats.winning_trades },
                    { name: 'Losses', value: performanceStats.losing_trades },
                  ]}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value, percent }) =>
                    `${name}: ${value} (${(percent * 100).toFixed(1)}%)`
                  }
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  <Cell fill="#10b981" />
                  <Cell fill="#ef4444" />
                </Pie>
                <Tooltip formatter={(value) => value} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="no-data">No trade data available</p>
          )}
        </div>

        {/* Cumulative P&L Chart */}
        <div className="chart-container full-width">
          <h3>Cumulative P&L (Last 7 Days)</h3>
          {weeklyStats?.daily_stats && weeklyStats.daily_stats.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={calculateCumulativePnL(weeklyStats.daily_stats)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="stats_date"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(date) => {
                    const d = new Date(date);
                    return `${d.getMonth() + 1}/${d.getDate()}`;
                  }}
                />
                <YAxis />
                <Tooltip
                  contentStyle={{ backgroundColor: '#f9fafb', border: '1px solid #e5e7eb' }}
                  formatter={(value) => `₹${value.toFixed(2)}`}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="cumulative_pnl"
                  stroke="#667eea"
                  strokeWidth={2}
                  dot={false}
                  name="Cumulative P&L"
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="no-data">No trading data available</p>
          )}
        </div>
      </div>



      {/* Live Status */}
      <div className="live-status">
        <h3>Live Status</h3>
        <div className="status-grid">
          <div className="status-item">
            <label>Current Time (IST)</label>
            <span>{new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
          </div>
          <div className="status-item">
            <label>Session Start</label>
            <span>{botStatus?.startTime ? new Date(botStatus.startTime).toLocaleTimeString() : 'N/A'}</span>
          </div>
          <div className="status-item">
            <label>Trades Today</label>
            <span>{botStatus?.trades_today || 0}</span>
          </div>
          <div className="status-item">
            <label>Current Position</label>
            <span>{botStatus?.current_position ? `${botStatus.current_position.side} ${botStatus.current_position.quantity}` : 'None'}</span>
          </div>
        </div>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Kite API Credentials</h2>
              <button className="modal-close" onClick={() => setShowSettings(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Kite API Key</label>
                <input
                  type="text"
                  name="kite_api_key"
                  value={settingsData.kite_api_key}
                  onChange={handleSettingsChange}
                  placeholder="Enter your Kite API Key"
                />
              </div>
              <div className="form-group">
                <label>Kite Access Token</label>
                <input
                  type="text"
                  name="kite_access_token"
                  value={settingsData.kite_access_token}
                  onChange={handleSettingsChange}
                  placeholder="Enter your Access Token (obtained after OAuth)"
                />
              </div>
              <div className="form-group">
                <label>Zerodha User ID</label>
                <input
                  type="text"
                  name="zerodha_user_id"
                  value={settingsData.zerodha_user_id}
                  onChange={handleSettingsChange}
                  placeholder="Enter your Zerodha User ID"
                />
              </div>
              <div className="form-note">
                <p>Get your credentials from:</p>
                <ol>
                  <li>Visit <a href="https://developers.kite.trade/login" target="_blank" rel="noopener noreferrer">Kite Developer Portal</a></li>
                  <li>Create or view your app to get API Key</li>
                  <li>Follow the OAuth flow to get Access Token</li>
                </ol>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={handleKiteLogin}>
                Open Kite Login
              </button>
              <button className="btn-cancel" onClick={() => setShowSettings(false)}>
                Cancel
              </button>
              <button 
                className="btn-save" 
                onClick={handleSaveSettings}
                disabled={savingSettings}
              >
                {savingSettings ? 'Saving...' : 'Save Credentials'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

function calculateCumulativePnL(dailyStats) {
  let cumulative = 0;
  return dailyStats.map((stat) => {
    cumulative += stat.total_pnl;
    return {
      ...stat,
      cumulative_pnl: cumulative,
    };
  });
}

export default Dashboard;
