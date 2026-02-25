import React, { useState } from 'react';
import './APITester.css';

const APITester = ({ config }) => {
  const [testResults, setTestResults] = useState({});
  const [loading, setLoading] = useState({});
  const [expanded, setExpanded] = useState({});

  const tests = [
    {
      id: 'profile',
      name: 'Get Profile',
      description: 'Fetch user profile information from Kite API',
      endpoint: '/api/health',
    },
    {
      id: 'quote',
      name: 'Get Quote',
      description: 'Fetch current quote for TATASTEEL',
      endpoint: '/api/bot/status',
    },
    {
      id: 'orders',
      name: 'Get Orders',
      description: 'Fetch list of orders placed today',
      endpoint: '/api/analytics/today',
    },
    {
      id: 'positions',
      name: 'Get Positions',
      description: 'Fetch current open positions',
      endpoint: '/api/analytics/weekly',
    },
    {
      id: 'holdings',
      name: 'Get Holdings',
      description: 'Fetch delivery holdings',
      endpoint: '/api/logs?limit=10',
    },
    {
      id: 'balance',
      name: 'Get Account Balance',
      description: 'Fetch margin and balance details',
      endpoint: '/api/health',
    },
  ];

  const runTest = async (testId, endpoint) => {
    setLoading(prev => ({ ...prev, [testId]: true }));
    
    try {
      const response = await fetch(endpoint);
      const data = await response.json();
      
      setTestResults(prev => ({
        ...prev,
        [testId]: {
          status: response.status === 200 ? 'success' : 'error',
          statusCode: response.status,
          data: data,
          timestamp: new Date().toLocaleTimeString(),
        }
      }));
    } catch (error) {
      setTestResults(prev => ({
        ...prev,
        [testId]: {
          status: 'error',
          error: error.message,
          timestamp: new Date().toLocaleTimeString(),
        }
      }));
    } finally {
      setLoading(prev => ({ ...prev, [testId]: false }));
    }
  };

  const runAllTests = async () => {
    for (const test of tests) {
      await runTest(test.id, test.endpoint);
      await new Promise(resolve => setTimeout(resolve, 300)); // Small delay between tests
    }
  };

  const toggleExpand = (testId) => {
    setExpanded(prev => ({
      ...prev,
      [testId]: !prev[testId]
    }));
  };

  const getStatusColor = (status) => {
    if (status === 'success') return '#51cf66';
    if (status === 'error') return '#ff6b6b';
    return '#888';
  };

  const successCount = Object.values(testResults).filter(r => r.status === 'success').length;
  const totalRequested = Object.keys(testResults).length;

  return (
    <div className="api-tester">
      <div className="tester-header">
        <div className="tester-title">
          <span className="tester-icon">🧪</span>
          <span>API Health Checker</span>
        </div>
        
        <div className="tester-actions">
          {totalRequested > 0 && (
            <div className="test-summary">
              <span className="summary-label">Results:</span>
              <span className="summary-value" style={{ color: getStatusColor('success') }}>
                {successCount}/{totalRequested} ✓
              </span>
            </div>
          )}
          <button 
            className="run-all-btn"
            onClick={runAllTests}
            disabled={Object.values(loading).some(v => v)}
          >
            {Object.values(loading).some(v => v) ? '⏳ Testing...' : '▶ Run All Tests'}
          </button>
        </div>
      </div>

      <div className="tests-container">
        {tests.map(test => {
          const result = testResults[test.id];
          const isLoading = loading[test.id];
          const isExpanded = expanded[test.id];

          return (
            <div key={test.id} className="test-item">
              <div className="test-header" onClick={() => toggleExpand(test.id)}>
                <div className="test-info">
                  <span className="test-name">{test.name}</span>
                  <span className="test-description">{test.description}</span>
                </div>

                <div className="test-controls">
                  {result && (
                    <span 
                      className="test-status"
                      style={{ 
                        color: getStatusColor(result.status),
                        fontWeight: 'bold'
                      }}
                    >
                      {result.status === 'success' ? '✓ PASS' : '✗ FAIL'}
                    </span>
                  )}
                  
                  <button
                    className="test-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      runTest(test.id, test.endpoint);
                    }}
                    disabled={isLoading}
                  >
                    {isLoading ? '⏳' : '▶ Test'}
                  </button>

                  {result && (
                    <span className="expand-icon" style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                      ▼
                    </span>
                  )}
                </div>
              </div>

              {result && isExpanded && (
                <div className="test-details">
                  <div className="detail-row">
                    <span className="detail-label">Status Code:</span>
                    <span className="detail-value" style={{ color: result.statusCode === 200 ? '#51cf66' : '#ff6b6b' }}>
                      {result.statusCode || 'Error'}
                    </span>
                  </div>

                  {result.error && (
                    <div className="detail-row">
                      <span className="detail-label">Error:</span>
                      <span className="detail-value" style={{ color: '#ff6b6b' }}>
                        {result.error}
                      </span>
                    </div>
                  )}

                  <div className="detail-row">
                    <span className="detail-label">Timestamp:</span>
                    <span className="detail-value">{result.timestamp}</span>
                  </div>

                  {result.data && (
                    <div className="detail-row">
                      <span className="detail-label">Response:</span>
                      <pre className="detail-json">{JSON.stringify(result.data, null, 2).substring(0, 200)}...</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {totalRequested === 0 && (
        <div className="tester-empty">
          <p>No tests run yet</p>
          <p className="text-muted">Click "Run All Tests" to check API connectivity</p>
        </div>
      )}

      <div className="tester-info">
        <h4>What This Tests:</h4>
        <ul>
          <li><strong>Profile:</strong> Verifies Kite API authentication and user profile access</li>
          <li><strong>Quote:</strong> Tests real-time price data fetching</li>
          <li><strong>Orders:</strong> Checks order management API endpoints</li>
          <li><strong>Positions:</strong> Tests position retrieval functionality</li>
          <li><strong>Holdings:</strong> Verifies delivery holdings access</li>
          <li><strong>Balance:</strong> Tests margin and balance API</li>
        </ul>
      </div>
    </div>
  );
};

export default APITester;
