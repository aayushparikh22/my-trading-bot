import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import APITester from '../components/APITester';
import { configAPI } from '../services/api';
import './APITesterPage.css';

const APITesterPage = () => {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const data = await configAPI.getConfig();
      setConfig(data);
    } catch (error) {
      console.error('Failed to fetch config:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="api-tester-page">
      <div className="page-header">
        <button className="back-btn" onClick={() => navigate('/dashboard')}>
          ← Back to Dashboard
        </button>
        <h1>🔧 API Health Checker</h1>
        <p className="page-description">Test and verify all API endpoints and Kite integration</p>
      </div>

      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading configuration...</p>
        </div>
      ) : (
        <div className="api-tester-container">
          <APITester config={config} />
        </div>
      )}
    </div>
  );
};

export default APITesterPage;
