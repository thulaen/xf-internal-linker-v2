// Proxy target is set via API_PROXY_TARGET env var.
// In Docker (docker-compose) this defaults to the backend service name.
// For local dev outside Docker, run: API_PROXY_TARGET=http://localhost:8000 ng serve
const target = process.env['API_PROXY_TARGET'] ?? 'http://backend:8000';

export default {
  '/api': {
    target,
    secure: false,
    changeOrigin: true,
    logLevel: 'debug',
  },
  '/ws': {
    target,
    secure: false,
    ws: true,
    changeOrigin: true,
  },
  '/static': {
    target,
    secure: false,
    changeOrigin: true,
  },
  '/media': {
    target,
    secure: false,
    changeOrigin: true,
  },
  '/admin': {
    target,
    secure: false,
    changeOrigin: true,
  },
};
