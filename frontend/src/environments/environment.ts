/**
 * Development environment configuration.
 * API calls proxy to Django backend via proxy.conf.json.
 */

export const environment = {
  production: false,
  apiBaseUrl: '/api',
  adminUrl: 'http://localhost:8000/admin/',
  wsBaseUrl: 'ws://localhost:8000/ws',
  appVersion: '2.0.0',
};
