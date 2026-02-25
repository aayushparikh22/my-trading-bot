import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

// Create axios instance with default config
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Handle response errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  register: (data) => apiClient.post('/auth/register', data),
  login: (email, password) => apiClient.post('/auth/login', { email, password }),
  logout: () => apiClient.post('/auth/logout'),
};

// Config API
export const configAPI = {
  getConfig: () => apiClient.get('/config'),
  updateConfig: (data) => apiClient.put('/config', data),
};

// Kite OAuth API
export const kiteAPI = {
  login: () => apiClient.get('/kite/login'),
};

// Bot Control API
export const botAPI = {
  start: () => apiClient.post('/bot/start'),
  stop: () => apiClient.post('/bot/stop'),
  status: () => apiClient.get('/bot/status'),
};

// Analytics API
export const analyticsAPI = {
  today: () => apiClient.get('/analytics/today'),
  weekly: () => apiClient.get('/analytics/weekly'),
  trades: (params) => apiClient.get('/analytics/trades', { params }),
  performance: () => apiClient.get('/analytics/performance'),
};

// Logs API
export const logsAPI = {
  get: (params) => apiClient.get('/logs', { params }),
};

export default apiClient;
