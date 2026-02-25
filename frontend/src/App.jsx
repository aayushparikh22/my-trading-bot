import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Portfolio from './pages/Portfolio';
import APITesterPage from './pages/APITesterPage';
import LiveTerminalPage from './pages/LiveTerminalPage';
import MarketWatch from './pages/MarketWatch';
import TradingMonitor from './pages/TradingMonitor';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/api-tester" element={<APITesterPage />} />
        <Route path="/terminal" element={<LiveTerminalPage />} />
        <Route path="/market-watch" element={<MarketWatch />} />
        <Route path="/trading-monitor" element={<TradingMonitor />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
