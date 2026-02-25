import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import LiveTerminal from '../components/LiveTerminal';
import { botAPI } from '../services/api';
import './LiveTerminalPage.css';

const LiveTerminalPage = () => {
  const navigate = useNavigate();
  const [botStatus, setBotStatus] = useState(null);
  const [botRunning, setBotRunning] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchBotStatus();
    const interval = setInterval(fetchBotStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const fetchBotStatus = async () => {
    try {
      const response = await botAPI.status();
      const data = response.data;
      setBotStatus(data);
      // Check if status is RUNNING or READY (matches Dashboard logic)
      setBotRunning(data.status === 'RUNNING' || data.status === 'READY');
    } catch (error) {
      console.error('Failed to fetch bot status:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="live-terminal-page">
      <div className="page-header">
        <button className="back-btn" onClick={() => navigate('/dashboard')}>
          ← Back to Dashboard
        </button>
        <h1>📊 Live Terminal</h1>
        <div className="status-badge">
          <span className={`status-dot ${botRunning ? 'status-running' : 'status-stopped'}`}></span>
          <span className="status-text">Bot {botRunning ? 'Running' : 'Stopped'}</span>
        </div>
        <p className="page-description">Real-time trading logs, market data, and manual trading controls</p>
      </div>

      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading terminal...</p>
        </div>
      ) : (
        <div className="terminal-container">
          <LiveTerminal botStatus={botStatus} botRunning={botRunning} />
        </div>
      )}
    </div>
  );
};

export default LiveTerminalPage;
