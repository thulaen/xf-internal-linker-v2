# 2026-04-26 00:13 - Gemini 3.1 Pro (High)
[HANDOFF READ: 2026-04-25 by Antigravity — Stabilized frontend and Nginx infrastructure]

## Accomplishments
- **Login HTTP-to-HTTPS redirect fix**: Changed Nginx port 80 redirect from `301` to `308`. This preserves the POST method when the Service Worker traps the initial navigation on HTTP, preventing the login form from throwing a `405 Method Not Allowed`.
- **WebSocket Storms Fixed**: Fixed duplicate socket leaks in `PulseService` and `NotificationService` caused by multiple `isLoggedIn$` emissions. Appended missing auth token to `PulseService`.
- **Pull-To-Refresh Mobile Performance**: Re-engineered `appPullToRefresh`. Removed `@HostListener('pointermove')` which was flooding the Angular zone with >100 change detections per second during mobile swipes. Events are now bound manually using `Renderer2` wrapped in `NgZone.runOutsideAngular()`.

## Status
- **Nginx**: Healthy and correctly redirecting POST requests with 308.
- **Frontend**: Production build completed with performance and socket fixes.

## Next Steps for User
1. Test login flow and background telemetry.
2. Monitor system for any leftover toasts.

# 2026-04-25 22:35 - Antigravity
[HANDOFF READ: 2026-04-25 by Antigravity — Stabilized frontend and Nginx infrastructure]

## Accomplishments
- **Nginx 1.30 LTS Upgrade**: Rewrote config for HTTPS, HTTP/2, and dynamic DNS resolution (resolver 127.0.0.11).
- **Sluggishness Fix**: Reduced proxy_connect_timeout to 5s. This prevents Nginx from holding onto broken backend connections for 60s, which previously exhausted the browser's 6-connection-per-host limit and caused the UI to hang.
- **Login "Server error" Fix**: Auth-gated PulseService, AppearanceService, and FeatureFlagsService. They no longer hit authenticated endpoints before the user logs in, eliminating the 403 storms on the login page.
- **Build Recovery**: Fixed a missing MatCardModule import in DiagnosticsComponent that was breaking the production build of the frontend.
- **Service Worker Tuning**: Reconfigured ngsw-config.json to lazy-load chunks and cache boot-time settings, improving perceived startup speed.
- **Silent Error Cleanup**: Patched state-sync bugs in AppearanceService (logo/favicon removal) and added error handling to NotificationService summary loading.

## Status
- **Nginx**: Healthy (verified ok on /nginx-health).
- **Frontend**: Production build completed and assets published to frontend_dist.
- **SSL**: mkcert is active; https://localhost is ready.

## Next Steps for User
1. **Auto-Renewal**: Run scripts\install-cert-renewal-task.ps1 in an Administrator PowerShell to register the monthly certificate renewal task.
2. **Verify**: Visit https://localhost and confirm the green padlock and the absence of the "Server error" toast on login.
