import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';
import './Portfolio.css';

const Portfolio = () => {
  const navigate = useNavigate();
  const [portfolioData, setPortfolioData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchPortfolioData();
    // Refresh every 30 seconds
    const interval = setInterval(fetchPortfolioData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchPortfolioData = async () => {
    try {
      const response = await fetch('/api/portfolio/holdings');
      const data = await response.json();
      
      if (response.ok && data.success) {
        setPortfolioData(data);
        setError(null);
      } else {
        setError(data.error || 'Failed to fetch portfolio data');
      }
    } catch (err) {
      setError('Network error. Please check your connection.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="portfolio-container">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Loading Your Portfolio...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="portfolio-container">
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <h3>Error Loading Portfolio</h3>
          <p>{error}</p>
          <button onClick={fetchPortfolioData} className="retry-btn">Retry</button>
        </div>
      </div>
    );
  }

  const { summary, holdings } = portfolioData;

  // Prepare data for charts
  const holdingsDistribution = holdings.map(h => ({
    name: h.symbol,
    value: h.current_value,
    percentage: ((h.current_value / summary.current_value) * 100).toFixed(2)
  }));

  const pnlData = holdings.map(h => ({
    name: h.symbol,
    pnl: h.pnl,
    pnlPercentage: h.pnl_percentage
  })).sort((a, b) => b.pnl - a.pnl);

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D', '#FFC658', '#FF6B9D', '#C89BFA', '#4ECDC4'];

  const formatCurrency = (value) => {
    return `₹${Math.abs(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="portfolio-container">
      {/* Header */}
      <div className="portfolio-header">
        <div className="header-left-section">
          <button onClick={() => navigate('/dashboard')} className="back-btn">
            ← Back to Dashboard
          </button>
          <h1>📊 Portfolio Analysis</h1>
        </div>
        <button onClick={fetchPortfolioData} className="refresh-btn">
          🔄 Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="summary-grid">
        <div className="summary-card highlight">
          <div className="card-icon">💼</div>
          <div className="card-content">
            <span className="card-label">Portfolio Value</span>
            <span className="card-value">{formatCurrency(summary.portfolio_value)}</span>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">💰</div>
          <div className="card-content">
            <span className="card-label">Total Investment</span>
            <span className="card-value">{formatCurrency(summary.total_investment)}</span>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">📈</div>
          <div className="card-content">
            <span className="card-label">Current Value</span>
            <span className="card-value">{formatCurrency(summary.current_value)}</span>
          </div>
        </div>

        <div className={`summary-card ${summary.total_pnl >= 0 ? 'profit' : 'loss'}`}>
          <div className="card-icon">{summary.total_pnl >= 0 ? '📊' : '📉'}</div>
          <div className="card-content">
            <span className="card-label">Total P&L</span>
            <span className="card-value">{formatCurrency(summary.total_pnl)}</span>
            <span className={`card-percentage ${summary.total_pnl >= 0 ? 'positive' : 'negative'}`}>
              {summary.total_pnl >= 0 ? '+' : ''}{summary.overall_return_percentage.toFixed(2)}%
            </span>
          </div>
        </div>

        <div className={`summary-card ${summary.day_pnl >= 0 ? 'profit' : 'loss'}`}>
          <div className="card-icon">📅</div>
          <div className="card-content">
            <span className="card-label">Today's P&L</span>
            <span className="card-value">{formatCurrency(summary.day_pnl)}</span>
            <span className={`card-percentage ${summary.day_pnl >= 0 ? 'positive' : 'negative'}`}>
              {summary.day_pnl >= 0 ? '+' : ''}{summary.day_return_percentage.toFixed(2)}%
            </span>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">💵</div>
          <div className="card-content">
            <span className="card-label">Available Cash</span>
            <span className="card-value">{formatCurrency(summary.available_cash)}</span>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">📊</div>
          <div className="card-content">
            <span className="card-label">Total Holdings</span>
            <span className="card-value">{summary.total_holdings}</span>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">⚡</div>
          <div className="card-content">
            <span className="card-label">Used Margin</span>
            <span className="card-value">{formatCurrency(summary.used_margin)}</span>
          </div>
        </div>
      </div>

      {/* Charts Section */}
      <div className="charts-section">
        {/* Holdings Distribution Pie Chart */}
        <div className="chart-card">
          <h3>Holdings Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={holdingsDistribution}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percentage }) => `${name}: ${percentage}%`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {holdingsDistribution.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatCurrency(value)} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* P&L by Stock Bar Chart */}
        <div className="chart-card">
          <h3>Profit & Loss by Stock</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={pnlData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip 
                formatter={(value, name) => {
                  if (name === 'pnl') return [formatCurrency(value), 'P&L'];
                  return [value.toFixed(2) + '%', 'Return %'];
                }}
              />
              <Legend />
              <Bar dataKey="pnl" fill="#8884d8" name="P&L (₹)" />
              <Bar dataKey="pnlPercentage" fill="#82ca9d" name="Return %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Holdings Table */}
      <div className="holdings-table-container">
        <h3>📋 Detailed Holdings</h3>
        <div className="table-wrapper">
          <table className="holdings-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Exchange</th>
                <th>Qty</th>
                <th>Avg Price</th>
                <th>LTP</th>
                <th>Investment</th>
                <th>Current Value</th>
                <th>P&L</th>
                <th>Return %</th>
                <th>Day Change</th>
                <th>Day %</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding, index) => (
                <tr key={index} className={holding.pnl >= 0 ? 'profit-row' : 'loss-row'}>
                  <td className="symbol-cell">
                    <strong>{holding.symbol}</strong>
                  </td>
                  <td>{holding.exchange}</td>
                  <td>{holding.quantity}</td>
                  <td>{formatCurrency(holding.average_price)}</td>
                  <td className="ltp-cell">{formatCurrency(holding.last_price)}</td>
                  <td>{formatCurrency(holding.investment)}</td>
                  <td>{formatCurrency(holding.current_value)}</td>
                  <td className={holding.pnl >= 0 ? 'profit-text' : 'loss-text'}>
                    {holding.pnl >= 0 ? '+' : ''}{formatCurrency(holding.pnl)}
                  </td>
                  <td className={holding.pnl_percentage >= 0 ? 'profit-text' : 'loss-text'}>
                    {holding.pnl_percentage >= 0 ? '+' : ''}{holding.pnl_percentage.toFixed(2)}%
                  </td>
                  <td className={holding.day_change >= 0 ? 'profit-text' : 'loss-text'}>
                    {holding.day_change >= 0 ? '+' : ''}{formatCurrency(holding.day_change)}
                  </td>
                  <td className={holding.day_change_percentage >= 0 ? 'profit-text' : 'loss-text'}>
                    {holding.day_change_percentage >= 0 ? '+' : ''}{holding.day_change_percentage.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Portfolio;
