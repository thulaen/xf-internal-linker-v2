# 2026-04-26 04:35 - Claude Opus 4.7 (1M context)
[HANDOFF READ: 2026-04-26 00:13 by Gemini 3.1 Pro - Login redirect 308 + WebSocket leak fixes + pull-to-refresh perf]

## Accomplishments
- **Permanent fix for "Docker Desktop spinning forever after every reboot"**: rooted to orphan AF_UNIX socket reparse points (`dockerInference`, `engine.sock`) that Windows cannot delete. Built `scripts/reset-docker-sockets.ps1` which renames any directory containing an unreadable reparse point, and `scripts/install-docker-socket-reset-task.ps1` which registers a user-level Windows Scheduled Task `XFLinker-ResetDockerSockets` (AtLogOn, Hidden window, ExecutionPolicy Bypass). Task is now active.
- **Disabled Docker Inference Manager**: set `EnableDockerAI: false` and `InferenceCanUseGPUVariant: false` in `%APPDATA%\Docker\settings-store.json` so the Inference Manager does not even spawn. Linker stack does not use Docker Model Runner.
- **Trimmed backend `command:` in `docker-compose.yml`**: removed `pip install -r requirements.txt`, `import drf_spectacular` probe (both already done at build time in `backend/Dockerfile:62-63`). Container now goes from start to healthy in ~33s instead of ~90-180s, and there is no network dependency at container start so a cold-boot reboot will not loop the container forever. Kept `build_ext --inplace` because the bind mount of `./backend → /app` hides image-baked `.so` files.
- **CLAUDE.md updated** under Docker Rules with the orphan-socket fix, the autostart-off rule, and the lean-command rule. `scripts/start.ps1` got a header comment explaining the new boot semantics.

## Status
- **Docker Desktop**: 29.4.0, currently running and healthy.
- **Linker stack**: all 7 services `(healthy)`, GlitchTip profile services also up.
- **AutoStart in settings-store.json**: `false` (was already off when I arrived).
- **Scheduled Task XFLinker-ResetDockerSockets**: registered, ran successfully once (renamed a fresh secrets-engine orphan as a smoke test).
- **Backend image**: NOT rebuilt; `docker compose up -d` recreated only the backend container with the new compose-file command. Image is unchanged (still has pip install at build time).

## Next Steps for User
1. **Real test**: reboot the laptop. After login, do nothing for 30s, then click Docker Desktop. Whale icon should settle in ~30-60s (no spin), and `restart: always` should bring all containers back up (no need to run `start.ps1`).
2. If a future Docker Desktop release introduces a new orphan-socket location, append the path to `$candidateDirs` in `scripts/reset-docker-sockets.ps1`.
3. Optional follow-up: clean up the leftover `priceless_feistel` container (unrelated test scratch container, exited 11 hours ago). `docker rm priceless_feistel`.

## Files Touched
- `docker-compose.yml` — backend `command:` block (lines 118-127, now lean)
- `scripts/start.ps1` — header comment update
- `scripts/reset-docker-sockets.ps1` — NEW
- `scripts/install-docker-socket-reset-task.ps1` — NEW
- `CLAUDE.md` — two new bullets under Docker Rules
- `%APPDATA%\Docker\settings-store.json` — EnableDockerAI/InferenceCanUseGPUVariant set to false

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
