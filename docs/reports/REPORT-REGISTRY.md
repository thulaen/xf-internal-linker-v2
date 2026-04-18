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

### RPT-002 — Phase 2 Forward-Declared Research Library (2026-04-15)

- **Status:** OPEN — 337 forward-declared backlog items (0 of 337 implemented). 2026-04-15 follow-up: recipe completion pass replaced inert weight defaults (462 keys at 0.0/false) with researched starting values and algorithm hyperparameters (1470 keys with paper-cited defaults). FR-225 Meta Rotation Scheduler filed to coordinate the 249 metas without conflicts.
- **Scope:** 126 new ranking signals (FR-099 … FR-224) + 210 new meta-algorithms (META-40 … META-249) filed as spec stubs at user request. Each has full academic math, paper/patent citation, C++ implementation notes, Python fallback placeholder, benchmark plan, budget, scope-boundary vs existing signals, and test-plan bullets.
- **Summary:** Research-backed library covering classical IR (Block A), proximity/term-dependence (B), graph centrality (C), diversity rerankers (D), temporal dynamics (E), sketches (F), text structure (G), click models (H), query performance prediction (I), information-theoretic divergences (J), site/host authority (K), anti-spam (L), author reputation (M), structural page-quality/CWV (N), passage segmentation (O). Metas cover second-order optimisers (P1), advanced first-order (P2), Bayesian HPO (P3), multi-objective (P4), metaheuristics (P5), online learning (P6), listwise losses (P7), regularisation (P8), calibration (P9), LR schedules (P10), model averaging (P11), robustness/sampling (P12), MCMC (Q1), VI (Q2), evolutionary (Q3), advanced gradients (Q4), reg/noise (Q5), feature engineering (Q6), dim reduction (Q7), kernels (Q8), info-theoretic model selection (Q9), clustering (Q10), attribution (Q11), active learning (Q12), semi-supervised (Q13), causal (Q14), RL (Q15), contextual bandits (Q16), matrix factorisation (Q17), NN init/norm (Q18), calibration variants (Q19), feature selection (Q20), metric learning (Q21), anomaly detection (Q22), validation/PBT (Q23), streaming trees (Q24).
- **Spec directory:** `docs/specs/fr099-*.md` … `docs/specs/fr224-*.md` and `docs/specs/meta-40-*.md` … `docs/specs/meta-249-*.md`.
- **Forward weight keys:** `backend/apps/suggestions/recommended_weights_phase2_forward.py` (inert, disabled at 0.0).
- **Budget discipline:** Each signal ≤ 32 MB disk, ≤ 512 MB RAM; each meta ≤ 15 MB disk; 66-meta batch (P1-P12) ≤ 128 MB peak RAM sequential; 144-meta batch (Q1-Q24) ≤ 256 MB peak RAM sequential.
- **Regression watch:** No code changed — specs only. Future implementation sessions must verify no duplicate with existing FR-001..FR-098 or META-01..META-39 (already verified at filing). If overlap is discovered during implementation, supersede per the existing duplication rules in CLAUDE.md and `docs/BUSINESS-LOGIC-CHECKLIST.md`.

---

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
- **Resolved:** 2026-04-12 (health component); 2026-04-15 (diagnostics component follow-up)
- **Fixed in:** (1) Removed `'http_worker'` from the `SERVICE_GROUPS` array and removed its troubleshooting hint. (2) 2026-04-15 follow-up: `ServiceStatusViewSet` queryset now excludes `http_worker`; all C# references purged from `diagnostics.component.ts/.html/.scss` — removed `http_worker` execution card, renamed "C# Scheduler" → "Task Scheduler", removed `owner === 'csharp'` dead branch. Backend `diagnostics/models.py` still has `http_worker` and `scheduler_lane` as model choices — left in place to avoid a migration on historical data.
- **Regression watch:** Do not re-add `http_worker` to the view queryset or to any frontend card-builder unless a replacement C# service is deployed. `scheduler_lane` remains valid and is now correctly labelled as a Python/Celery service.

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

### ISS-020 — FR-045 ledger drift: anchor-diversity ships in code but ledger marks it pending (2026-04-18)

- **Found by:** Claude (during duplicate-check research for suggestion-quality telemetry Phase 1)
- **Severity:** low
- **Affected files:** `AI-CONTEXT.md` (line 322, Pending FRs list), `FEATURE-REQUESTS.md` (FR-045 status)
- **Description:** `AI-CONTEXT.md` lists `FR-045` among the 60 pending FRs, but the shipping evidence is present: `backend/apps/pipeline/services/anchor_diversity.py` implements `evaluate_anchor_diversity`; `Suggestion.score_anchor_diversity` exists with help text `"FR-045 anchor-diversity anti-spam score"`; migrations `0031_suggestion_anchor_diversity_diagnostics_and_more.py` and `0032_upsert_runtime_antispam_defaults.py` are applied; spec `docs/specs/fr045-anchor-diversity-exact-match-reuse-guard.md` exists. The ranker, diagnostic surface, and settings UI all reference FR-045. Either the implementation is effectively complete and the ledger needs updating, or some acceptance criterion is unmet and the gap should be documented. Per BLC §4.1 "If a feature is complete but marked partial or pending, fix the ledger. If it is partial but marked complete, fix the ledger."
- **Status:** OPEN
- **Regression watch:** Future sessions touching anchor-diversity telemetry should not create parallel `AnchorUsage` tables or over-optimised-anchor warning UIs — FR-045 already handles that surface via `score_anchor_diversity` and `anchor_diversity_diagnostics`.

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

### ISS-012 - `/api/health/disk/` and `/api/health/gpu/` returned 404 because router URLs shadowed explicit health routes (2026-04-14)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/api/urls.py`, `backend/apps/health/tests.py`
- **Description:** The frontend health screen triggered server errors because Django matched `/api/health/disk/` and `/api/health/gpu/` against the generic health viewset detail route before it reached the dedicated disk and GPU views. Requests were interpreted as `service_key="disk"` and `service_key="gpu"` and came back 404 instead of returning the dedicated payloads.
- **Status:** RESOLVED
- **Resolved:** 2026-04-14
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-14
- **Regression watch:** Keep specific utility routes ahead of `include(router.urls)` when their prefixes overlap with a viewset basename, or namespace them so the router cannot swallow them.

### ISS-013 - Alert detail page called a nonexistent notifications detail endpoint (2026-04-14)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/notifications/views.py`, `backend/apps/notifications/urls.py`, `backend/apps/notifications/tests.py`, `frontend/src/app/core/services/notification.service.ts`, `frontend/src/app/alerts/alert-detail/alert-detail.component.ts`
- **Description:** The alert detail screen requested `/api/notifications/<uuid>/`, but the backend exposed only the alerts list and test endpoints. Opening an alert always failed with a 404 and left the detail view unusable.
- **Status:** RESOLVED
- **Resolved:** 2026-04-14
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-14
- **Regression watch:** Keep the frontend alert-detail path aligned with the backend notifications URL map and prefer routing these calls through `NotificationService` so list/detail endpoints stay centralized.

### ISS-014 - Frontend Dockerfile recreated UID 1000 and could fail `docker compose build` (2026-04-14)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `frontend/Dockerfile`
- **Description:** The frontend image build tried to run `useradd -m -u 1000 appuser` even though the upstream `node:22-slim` image already reserves UID 1000 for the built-in `node` user. On this base image the repo-mandated Docker build could fail before verification completed.
- **Status:** RESOLVED
- **Resolved:** 2026-04-14
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-14
- **Regression watch:** Reuse the base image's non-root `node` user unless the Dockerfile first proves that the target UID/GID is free.

### ISS-015 — GPU thermal pause/resume helpers were defined but never called (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/services/embeddings.py`, `docs/PERFORMANCE.md`
- **Description:** `_check_gpu_temperature()` and `_wait_for_gpu_cooldown()` were defined in `embeddings.py` but no production code ever called them. The two encode loops in `generate_content_embeddings` and `generate_sentence_embeddings` ran `model.encode(...)` directly with no thermal check. `docs/PERFORMANCE.md` §6 claimed a per-batch pynvml temperature check that was not actually happening, so the GPU was free to climb to NVIDIA's default ~93°C throttle on long overnight runs. Helper-node heartbeat endpoint promised in §2 (`POST /api/settings/helpers/{id}/heartbeat/`) was also missing — same disease, smaller blast radius.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Same session as ISS-016/-017/-018 — wired both helpers into the encode loops, raised default ceiling to 86°C / resume 78°C, added the missing heartbeat stub endpoint.
- **Regression watch:** Any future refactor of the encode loops in `embeddings.py` must keep the `if not _check_gpu_temperature(): _wait_for_gpu_cooldown()` guard before each `model.encode()` call. Any new "pause/resume" helper added anywhere must include a call site, not only a definition.

### ISS-016 — Heavy/Medium task locks were defined but never acquired by any task (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/services/task_lock.py`, `backend/apps/pipeline/tasks.py`, `backend/apps/cooccurrence/tasks.py`, `backend/apps/pipeline/decorators.py` (new)
- **Description:** `acquire_task_lock()`, `release_task_lock()` and `is_lock_held()` had been implemented as a Redis-backed locking service to enforce the docs/PERFORMANCE.md §4 golden rule "Never run two Heavy tasks simultaneously." The functions worked correctly in isolation and were exercised by unit tests, but no `@shared_task` ever called them. The 30-second stagger in `backend/config/catchup.py` spaced *dispatch* but did not prevent two Heavy tasks from running concurrently for hours. Catch-up dispatch also did not consult `is_lock_held` before sending tasks. Result: the golden rule was unenforced for the entire life of the lock service.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Added `with_weight_lock(weight_class)` decorator at `backend/apps/pipeline/decorators.py` that wraps a `bind=True` Celery task, calls `acquire_task_lock` on entry, and on contention does `self.retry(countdown=60, max_retries=60)` for FIFO-style defer. Applied to `import_content` (heavy), `monthly_weight_tune` (medium), and `compute_session_cooccurrence` (medium, also added `bind=True`). Catch-up dispatch is automatically covered because it goes through the same `app.send_task()` path as Beat — the decorator runs at task entry regardless of dispatch source.
- **Regression watch:** Any new Heavy/Medium `@shared_task` added to the codebase must apply `@with_weight_lock("heavy"|"medium")` directly under `@shared_task(bind=True, ...)`. Removing the decorator on any of the three current call sites would silently re-introduce the gap.

### ISS-017 — Embedding bulk_update ran only at the end of each loop, losing all in-RAM work on crash (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/services/embeddings.py`
- **Description:** `generate_content_embeddings` and `generate_sentence_embeddings` accumulated encoded vectors in a Python list and called `bulk_update(..., fields=["embedding"], batch_size=500)` once at the very end of the loop. If the worker was killed mid-run (`docker-compose stop`, OOM, hard crash), every embedding computed since the function started was lost — they never reached the database. On resume, the existing `embedding__isnull=True` filter at the top of the function had nothing to skip because no partial work had been persisted, so the entire job restarted from item 1. For a long embed (74k items, ~hours on RTX 3050), this could waste the equivalent of an entire overnight run.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Extended the existing every-5-batch progress-throttle pattern (which already saved `embedding_items_completed` to the SyncJob row) to also flush partial embeddings via `bulk_update`. After the loop, a tail flush handles any remainder. The existence of an embedding on a row is now itself the checkpoint — no new column needed. On resume, the `embedding__isnull=True` filter naturally picks up where the killed run left off.
- **Regression watch:** Any future refactor of the encode loops must preserve the `if batch_num % 5 == 0:` flush block and the post-loop tail flush. Removing them would silently restore the all-or-nothing behaviour.

### ISS-018 — `cleanup-stuck-sync-jobs` never set `is_resumable=True`, leaving the resume path unreachable (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/tasks.py`
- **Description:** `cleanup_stuck_sync_jobs` (scheduled daily at 22:10 UTC) marked sync jobs stuck in `status="running"` for >2 hours as `status="failed"`. The `SyncJob` model has resume infrastructure (`is_resumable`, `checkpoint_stage`, `checkpoint_last_item_id`) and `import_content` honours it at line ~615 with a `Resuming import job ... from checkpoint` log line. But the cleanup task never set `is_resumable=True`, so jobs killed by `docker-compose down` or laptop shutdown were marked permanently failed even when a checkpoint existed and resume would have worked. The most common path that should have resumed never did.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Split the `stuck.update(...)` into two: jobs with `checkpoint_stage IS NOT NULL` are now marked failed *with* `is_resumable=True` and a "Resumable from last checkpoint." message; jobs without a checkpoint stay marked failed (no resumable infrastructure to use). Log message now reports both counts.
- **Regression watch:** Any future change to `cleanup_stuck_sync_jobs` must keep the checkpoint-aware split. Any new "stuck job" cleanup paths added elsewhere must follow the same pattern.

### ISS-019 — GPU thermal ceiling raised further to 90°C / 80°C at operator request, and the `getattr` fallbacks in `embeddings.py` were out of sync with the settings file (2026-04-15)

- **Found by:** Claude (during follow-up wiring audit after ISS-015/-016/-017/-018)
- **Severity:** medium
- **Affected files:** `backend/config/settings/base.py`, `backend/apps/pipeline/services/embeddings.py`, `docs/PERFORMANCE.md`
- **Description:** Two separate but related issues. (1) During the wiring audit it was found that `_check_gpu_temperature()` at `embeddings.py:166` used `getattr(django_settings, "GPU_TEMP_CEILING_C", 76)` and `_wait_for_gpu_cooldown()` at `embeddings.py:246` used a fallback of `68` — both defaults were 10°C below the actual settings.py values (86/78) and disagreed with their own docstrings ("default 86°C", "Resume threshold: 78°C"). Harmless in normal operation because Django settings are always loaded, but a silent trap if the setting key were ever removed. (2) Operator requested a further bump from 86°C/78°C → 90°C/80°C to trade ~3°C of thermal headroom (vs NVIDIA's ~93°C driver throttle) for more sustained throughput on overnight runs.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** `GPU_TEMP_CEILING_C` 86 → 90 and `GPU_TEMP_RESUME_C` 78 → 80 in `settings/base.py`. `getattr` fallbacks in `embeddings.py` aligned to the new 90 / 80. Docstrings updated. `docs/PERFORMANCE.md` §6 callout, three-layer table, and "Why Software Limits" paragraph all updated. History chain preserved in the §6 callout (76/68 → 86/78 → 90/80).
- **Regression watch:** The four locations (`settings/base.py`, two `getattr` calls in `embeddings.py`, `docs/PERFORMANCE.md` §6) must stay aligned. Any future ceiling change must touch all four or the code will silently disagree with the docs. Operator noted awareness that 90°C leaves only ~3°C of margin before NVIDIA's hardware throttle — this is by design, not a bug.

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
