# Report Registry

This file is the single index of all audit reports and individual issues found by AI sessions. Every AI must read this file before starting work (see Session Gate in `AI-CONTEXT.md`).

## Rules

**Blocker Rule:** Any AI whose work area overlaps with an `OPEN` finding must tell the user in chat before writing any code, and must then either resolve it or explicitly justify in writing (in the Current Session Note in `AI-CONTEXT.md`) why it is skipping it.

**Silence Is Forbidden Rule:** If an AI notices an open or reopened finding that overlaps with the area it is about to touch, it must not stay silent. It must tell the user in chat first. Silent continuation is a policy violation.

**Anti-Duplication Rule:** Before logging a new issue, search this file for existing entries. If the issue is already logged, add a note to the existing entry instead of creating a duplicate.

**Anti-Regression Rule:** Before changing code in any area, search the Resolved sections below for entries that touch the same files. If a match exists, read what was fixed and verify your changes don't undo it. Resolved entries are permanent history — never delete them.

**Recurrence Rule:** If a new feature or change re-introduces a previously resolved issue (same root cause, same affected area), reopen the original entry by moving it back to the Open section with a note explaining what brought it back. Do not create a duplicate.

**Logging Rule:** If you find any bug, performance bottleneck, logic flaw, missing validation, or code smell during your session — even if it's outside your current task scope — add it here. Don't ignore it. Future AIs will see it and can fix it.

---

## Open Reports

### RPT-001 — Research-Backed Business Logic Audit (2026-04-11)

- **Status:** OPEN (5 of 5 findings unresolved)
- **Report file:** [`repo-business-logic-audit-2026-04-11.md`](repo-business-logic-audit-2026-04-11.md)
- **Scope:** Import, ranking, reranking, attribution, and weight auto-tuning logic
- **Summary:** Five logic-quality gaps in shipped code paths. All fixable by extending existing FR-013, FR-017, and FR-018 implementations in place.

| # | Finding | Severity | Affected files | Status |
|---|---------|----------|----------------|--------|
| 1 | C# import lane hardcoded 5-page cap creates silent corpus bias | high | `PipelineServices.cs` | OPEN |
| 2 | Feedback reranker's inverse-propensity claim unsupported by stored signal granularity | high | `feedback_rerank.py`, `models.py` | OPEN |
| 3 | C++ fast path and Python reference path compute different math in feedback reranker | critical | `feedrerank.cpp`, `feedback_rerank.py` | OPEN |
| 4 | Attribution mixes two incompatible counterfactual models | high | `impact_engine.py`, `GSCAttributionService.cs` | OPEN |
| 5 | Auto-tuning optimizes a 4-number global summary instead of ranking quality | medium | `WeightObjectiveFunction.cs`, `WeightTunerService.cs` | OPEN |

---

## Open Individual Issues

### ISS-003 â€” FAISS startup index build hits the database during app initialization (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/pipeline/apps.py`, `backend/apps/pipeline/services/faiss_index.py`
- **Description:** Docker-side `showmigrations` and `makemigrations --check` emit Django's `APPS_NOT_READY_WARNING_MSG` because `PipelineConfig.ready()` calls `build_faiss_index()` during startup, which touches the database before app initialization is complete. This makes management-command startup noisy and risks future initialization fragility.
- **Status:** OPEN
- **Regression watch:** Keep FAISS index building out of `AppConfig.ready()` for management commands and other startup paths that should remain side-effect free.

### ISS-004 — celery-beat container marked unhealthy despite working correctly (2026-04-12)

- **Found by:** Claude
- **Severity:** low
- **Affected files:** `docker-compose.yml` (celery-beat healthcheck)
- **Description:** `xf_linker_celery_beat` shows `(unhealthy)` in `docker-compose ps` and has a failing streak of 260+, but the container is fully operational — it sends tasks every minute (pulse-heartbeat, watchdog-check, refresh-faiss-index, etc.). The health check runs `celery -A config.celery inspect scheduled -t 10 2>&1 | grep -q '{'` but `inspect scheduled` returns `- empty -` (no deferred tasks) instead of JSON, so grep fails. The health check script is testing for the wrong output format.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed health check to `grep -q beat /proc/1/cmdline` — verifies the beat process is running without depending on task queue state.
- **Regression watch:** The container uses a slim Python image without `pgrep`. Health checks must use `/proc/1/cmdline` or built-in tools only.

---

### ISS-005 — Nginx proxy on port 80 returns 500 for all routes (2026-04-12)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `nginx/nginx.conf`, `docker-compose.yml` (nginx volumes, frontend service)
- **Description:** Navigating to `http://localhost/` (port 80) returns a 500 with `rewrite or internal redirection cycle while internally redirecting to "/index.html"`. The nginx config sets `root /usr/share/nginx/html/browser;` but the Angular dev-server container never populates the `frontend_dist` Docker volume — it runs a live dev server on port 4200 instead of building static files. The `browser/` subdirectory does not exist, so `try_files $uri $uri/ /index.html` keeps trying to serve `index.html` which also doesn't exist, causing a redirect loop.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed nginx from static file serving to reverse proxy to `http://frontend:4200`. Removed unused `frontend_dist` volume mount from nginx.
- **Regression watch:** If a production build pipeline is added later, the nginx config will need to switch back to static file serving with the correct `root` path.

---

### ISS-006 — GET /api/system/status/weights/ returns 500 (WeightDiagnosticsView tuple bug) (2026-04-12)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/diagnostics/views.py` (`WeightDiagnosticsView.get`), `backend/apps/diagnostics/health.py` (`check_native_scoring`, `_result`)
- **Description:** `GET /api/system/status/weights/` always returns a 500 with `AttributeError: 'tuple' object has no attribute 'get'`. Root cause: `check_native_scoring()` in `health.py` returns a raw tuple `(state, explanation, next_step, metadata)` via `_result()`, but `WeightDiagnosticsView.get()` calls `native_status.get("module_statuses", [])` — treating the return value as a dict.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed line 218 to unpack: `_state, _expl, _step, native_metadata = check_native_scoring()` then use `native_metadata.get(...)`.
- **Regression watch:** `_result()` is used throughout `health.py` as a 4-tuple. Any new caller must unpack it correctly, not treat it as a dict.

---

### ISS-007 — GET /api/benchmarks/latest/ returns 404 on /performance page (2026-04-12)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `backend/apps/benchmarks/views.py`
- **Description:** The Performance page triggers `GET /api/benchmarks/latest/` which returns 404 and causes a "Resource not found" toast on every page load. No benchmarks have ever been run so no latest record exists — the view returns 404 instead of an empty response.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed to return `Response(None, status=status.HTTP_200_OK)` when no completed benchmark runs exist. Added `.order_by("-started_at")` for deterministic latest selection.
- **Regression watch:** Frontend must handle `null` response body from `/api/benchmarks/latest/`.

---

### ISS-008 — Performance page subtitle still references C# after decommission (2026-04-12)

- **Found by:** Claude
- **Severity:** low
- **Affected files:** `frontend/src/app/performance/performance.component.html`, `frontend/src/app/performance/performance.component.scss`
- **Description:** The Performance page subtitle reads "Benchmark results across C++, Python, and C#" — but the C# runtime was decommissioned.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Removed C# from subtitle, filter chip bar, language display ternary, and `.lang-csharp` CSS rule.
- **Regression watch:** If C# support is re-added, restore the filter chip and lang badge.

---

### ISS-009 — C# High-Performance Runtime health check still present after decommission (2026-04-12)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `frontend/src/app/health/health.component.ts`
- **Description:** System Health page shows "C# High-Performance Runtime — C# Runtime Service unreachable" as a red error. The C# runtime was decommissioned. The frontend hardcoded `'http_worker'` in the Infrastructure health group, but the backend has no such check registered.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Removed `'http_worker'` from the `SERVICE_GROUPS` array and removed its troubleshooting hint. Backend `diagnostics/models.py` still has `http_worker` and `scheduler_lane` as model choices — left in place to avoid a migration on historical data.
- **Regression watch:** Do not re-add `http_worker` to health groups unless a replacement service is deployed.

---

### ISS-010 — Disk space critically full at 93.2% (2026-04-12)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** Host machine disk
- **Description:** System Health page shows "Disk critically full — 93.2% used."
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Ran `docker image prune -f` and removed the decommissioned `xf-linker-http-worker` image (344MB). Main disk consumer remains the 13.5GB backend image.
- **Regression watch:** Run `docker image prune -f` after every `docker-compose build` per CLAUDE.md rules.

---

### ISS-011 — 101 stalled-job alerts flooding the Alerts page with 142× duplicates (2026-04-12)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `backend/apps/crawler/tasks.py` (watchdog_check)
- **Description:** The Alerts page shows 101 unread alerts, all of type "api sync appears stuck", with each individual job stall generating 142× duplicate alert entries. Stalled jobs were never cleaned up, and alert cooldown was only 15 minutes (default), causing new alert rows every 15 minutes per job.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Added auto-fail for sync jobs and crawl sessions stuck >24 hours. Added `cooldown_seconds=86400` (24h) to stalled-job alerts so only one alert is created per job per day. Narrowed the alert window to 30min–24h (jobs beyond 24h are auto-failed and stop generating alerts).
- **Regression watch:** If the 24-hour auto-fail threshold is too aggressive for some long-running jobs, increase it. The cooldown prevents alert floods regardless.

---

## Resolved Reports

_(None yet. When all findings in a report are resolved, move the report entry here with resolution dates.)_

---

## Resolved Individual Issues

### ISS-001 â€” Backend container could miss required `drf_spectacular` dependency and fail at startup (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/config/settings/base.py`, `backend/config/urls.py`, `backend/Dockerfile`, `docker-compose.yml`, `scripts/setup-dev.ps1`
- **Description:** The backend relied on `drf_spectacular` at runtime, but the running Docker container and some local setups could still start from a partially provisioned environment where that package was absent. This produced a confusing late failure during Django startup instead of a clear dependency-install failure.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-12
- **Regression watch:** Keep `drf_spectacular` required in Django settings and preserve the explicit import checks in Docker build/startup and local setup flows.

### ISS-002 â€” Local SQLite test database could drift behind migrations (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/plugins/apps.py`, `backend/apps/plugins/tests.py`, `scripts/setup-dev.ps1`
- **Description:** Local verification under `config.settings.test` could start against an incomplete `backend/test.sqlite3`, which made migration checks noisy and fragile. Plugin startup also needed to stay out of the way for test-settings and migration-oriented management commands.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-12
- **Regression watch:** Keep the plugin autoload skip for `.test` settings plus migration commands, and keep `scripts/setup-dev.ps1` running `migrate --settings=config.settings.test --noinput`.

---

## Templates

### New Report Entry

```markdown
### RPT-XXX — [Title] (YYYY-MM-DD)

- **Status:** OPEN (N of N findings unresolved)
- **Report file:** [`filename.md`](filename.md)
- **Scope:** [What code areas were audited]
- **Summary:** [One-line summary of key findings]

| # | Finding | Severity | Affected files | Status |
|---|---------|----------|----------------|--------|
| 1 | [description] | critical/high/medium/low | `file.py` | OPEN |
```

### New Individual Issue Entry

```markdown
### ISS-XXX — [Short description] (YYYY-MM-DD)

- **Found by:** [AI tool name, e.g. Claude / Codex / Gemini]
- **Severity:** critical / high / medium / low
- **Affected files:** `path/to/file.py`
- **Description:** [What the issue is and why it matters]
- **Status:** OPEN

_(When resolved, add:)_
- **Resolved:** YYYY-MM-DD
- **Fixed in:** [commit hash or session reference]
- **Regression watch:** [What to check if this area is changed again]
```
