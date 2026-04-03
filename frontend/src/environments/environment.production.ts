/**
 * Production environment configuration.
 * API calls go to the same origin (served by Nginx, proxied to Django).
 */

export const environment = {
  production: true,
  apiBaseUrl: '/api',
  adminUrl: `${window.location.origin}/admin/`,
  wsBaseUrl: `wss://${window.location.host}/ws`,
  appVersion: '2.0.0',
};
