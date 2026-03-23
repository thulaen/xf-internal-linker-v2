/**
 * Production environment configuration.
 * API calls go to the same origin (served by Nginx, proxied to Django).
 */

export const environment = {
  production: true,
  apiBaseUrl: '/api',
  wsBaseUrl: `wss://${window.location.host}/ws`,
  appVersion: '2.0.0',
};
