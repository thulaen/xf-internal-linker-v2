# FR-022 - Data Source & System Health Check Dashboard

## Confirmation

- `FR-022` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 25`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - GA4 and GSC settings already exist but no connection-status check is surfaced in the UI;
  - XenForo sync already exists (`apps/sync/`) but no live health status is exposed;
  - WordPress sync already exists (`apps/sync/services/wordpress_api.py`) but no live health status is exposed;
  - R analytics service exists as a separate Docker container (`services/r-analytics/`) with no health endpoint wired into the main app;
  - `AppSetting` stores connection credentials and config but no "last successful connection" or "last error" status fields;
  - `ErrorLog` stores background failures but they are not surfaced as per-source health indicators;
  - `FR-019` adds the notification center and alert system that this FR connects into;
  - no dedicated health dashboard page exists today.

## Current Repo Map

### Sync services

- `backend/apps/sync/`
  - XenForo API sync tasks and services.
- `backend/apps/sync/services/wordpress_api.py`
  - WordPress REST API read-only client.
- `backend/apps/sync/tasks.py`
  - Celery tasks for scheduled and manual syncs.

### Analytics / credentials storage

- `backend/apps/analytics/models.py`
  - `SearchMetric` — daily coarse GSC / GA4 metrics per content item.
  - `ImpactReport` — before/after comparison rows.
- `backend/apps/core/models.py`
  - `AppSetting` — typed key/value store for all credentials and config.

### Error log

- `backend/apps/audit/models.py`
  - `ErrorLog` — background job failures with `job_type`, `step`, `error_message`, `acknowledged`.

### External services

- `services/r-analytics/` — standalone R + Shiny Docker service.
- `services/http-worker/` — .NET 9 HttpWorker for broken-link scanning, URL fetching, health checking, sitemap crawling.

### Pipeline and algorithm

- `backend/apps/pipeline/tasks.py` — main pipeline Celery task.
- `backend/apps/pipeline/services/` — ranking, embedding, scoring services.

### Notification system

- `backend/apps/notifications/` — added by `FR-019` (operator alert persistence and delivery).

### Existing shell

- `frontend/src/app/app.component.html` — top-level shell.
- No health dashboard page or route exists today.

## Workflow Drift / Doc Mismatch Found During Inspection

- `docs/v2-master-plan.md` references a settings page with connection details but does not describe a live health check UI.
- GA4 property ID and GSC site URL are stored in settings but the app never verifies whether the credentials actually work.
- A silent token expiry or wrong property ID would not surface until the user notices empty analytics data.
- XenForo and WordPress syncs fail silently into `ErrorLog`; there is no at-a-glance indicator that data is flowing.
- R analytics runs as a Docker container; if it goes down, no part of the main app raises an alert.
- The algorithm pipeline could run successfully but produce zero suggestions due to misconfiguration; no health check flags this.

## Source Summary

### Industry research used

- GA4 Dashboard Best Practices 2025 — 1ClickReport
- How to Conduct a Google Analytics Health Check — Fresh Egg
- GA4 Status Checker — Capacity Interactive
- Offshore SEO Reporting: GA4 + GSC Dashboard Recipes — Versatile Club
- Google Analytics 4 Audit Checklist 2025 — MeasureSchool

### Key findings

- A dedicated health check tab is considered a best practice signal of reliability and professionalism.
- GA4 and GSC can take up to 48 hours to update; a health card should show last-data-received timestamp, not just "connected".
- Silent broken connections are the most common issue; a visible status panel catches them immediately.
- Segmenting branded vs non-branded queries requires GSC data flowing correctly; a broken GSC connection silently corrupts this.

### What was clear

- Each data source and service needs its own health card.
- Each card must show: connection status, last successful data received, last error, and a re-test / re-sync action.
- Cards must connect to `FR-019` alert system for push notifications when a source goes unhealthy.

### What remained ambiguous

- Whether GA4 health verification requires a live API call or can be inferred from `SearchMetric` recency alone.
- Whether the R analytics health check uses a simple HTTP ping or a real computation check.
- Whether Celery worker health should be one card or broken into queue-depth + worker-count sub-indicators.

## Problem Definition

Simple version first.

Right now the app stores credentials and runs syncs, but it never tells the user clearly "everything is connected and working" or "this thing broke two days ago." A silent broken connection looks exactly the same as a healthy one until the user notices empty data.

The fix is a dedicated health dashboard page with one card per data source and service. Each card answers three questions at a glance:

1. Is it connected?
2. When did data last arrive?
3. Is anything wrong?

## Health Cards — Full List

### 1. GA4 Health Card

**Purpose:** Confirm Google Analytics 4 is configured, credentials are valid, and traffic data is flowing.

**Status indicators:**

- `Connected` — credentials exist and last API call succeeded.
- `No data` — credentials exist but no `SearchMetric(source="ga4")` rows have arrived in the last N days.
- `Auth error` — last API call returned a 401 or 403.
- `Misconfigured` — property ID or measurement ID is missing.
- `Not set up` — no GA4 credentials stored at all.

**Displayed fields:**

- Connection status badge.
- GA4 property ID (masked for security, show last 4 digits only).
- Last successful data received: date + row count.
- Last error: message + timestamp (if any).
- Data freshness lag: hours since the most recent `SearchMetric(source="ga4")` row.
- Events tracked this week (count of `suggestion_link_impression`, `suggestion_link_click` if `FR-016` is active).

**Actions:**

- "Test Connection" — runs a lightweight GA4 API call and reports pass/fail.
- "Go to GA4 Settings" — links to the GA4 settings panel.

**Alert integration (`FR-019`):**

- Emit `data_source.ga4_auth_error` when a 401/403 is returned.
- Emit `data_source.ga4_no_data` when no data has arrived for more than `ga4_stale_threshold_hours` (default: 72).

---

### 2. GSC Health Card

**Purpose:** Confirm Google Search Console is configured, credentials are valid, and search data is flowing.

**Status indicators:**

- `Connected` — credentials exist and last API call succeeded.
- `No data` — credentials present but no `SearchMetric(source="gsc")` rows in the last N days.
- `Auth error` — last call returned 401 or 403.
- `Misconfigured` — site URL is missing or not verified in GSC.
- `Not set up` — no GSC credentials stored.

**Displayed fields:**

- Connection status badge.
- GSC site URL.
- Last successful data received: date + row count.
- Last error: message + timestamp.
- Data freshness lag: hours since most recent `SearchMetric(source="gsc")` row.
- Total impressions tracked this week.
- Total clicks tracked this week.
- Note: "GSC data has a natural 48-hour reporting delay. This is normal."

**Actions:**

- "Test Connection" — lightweight GSC API call.
- "Go to GSC Settings" — links to the GSC settings panel.
- "Trigger GSC Sync Now" — manual sync button.

**Alert integration (`FR-019`):**

- Emit `data_source.gsc_auth_error` on 401/403.
- Emit `data_source.gsc_no_data` when stale beyond threshold.

---

### 3. XenForo Sync Health Card

**Purpose:** Confirm XenForo data is being received and synced correctly.

**Status indicators:**

- `Syncing` — last sync succeeded and is within expected schedule.
- `Stale` — last sync was more than N hours ago.
- `Error` — last sync produced an `ErrorLog` entry.
- `Not configured` — no XenForo API credentials stored.

**Displayed fields:**

- Connection status badge.
- XenForo API base URL (display only).
- Last successful sync: timestamp + item count (threads + resources).
- Next scheduled sync: estimated time.
- Last error: message + timestamp.
- Total XenForo `ContentItem` count currently stored.
- Sync coverage: percentage of known threads that have been distilled.

**Actions:**

- "Test Connection" — ping the XenForo API.
- "Sync Now" — triggers a manual XenForo sync.
- "Go to XenForo Settings" — links to sync settings.

**Alert integration (`FR-019`):**

- Emit `data_source.xenforo_sync_error` on sync failure.
- Emit `data_source.xenforo_stale` when sync is overdue.

---

### 4. WordPress Sync Health Card

**Purpose:** Confirm WordPress data is being received and synced correctly.

**Status indicators:**

- `Syncing` — last sync succeeded within schedule.
- `Stale` — last sync was more than N hours ago.
- `Error` — last sync produced an `ErrorLog` entry.
- `Not configured` — no WordPress URL or credentials stored.

**Displayed fields:**

- Connection status badge.
- WordPress REST API base URL (display only).
- Auth method: Application Password / public.
- Last successful sync: timestamp + item count (posts + pages).
- Next scheduled sync: estimated time.
- Last error: message + timestamp.
- Total WordPress `ContentItem` count currently stored.

**Actions:**

- "Test Connection" — ping the WordPress REST API.
- "Sync Now" — triggers manual WordPress sync.
- "Go to WordPress Settings" — links to sync settings.

**Alert integration (`FR-019`):**

- Emit `data_source.wordpress_sync_error` on sync failure.
- Emit `data_source.wordpress_stale` when sync is overdue.

---

### 5. C# Analytics Worker Health Card

**Purpose:** Confirm the C# Analytics Worker inside `services/http-worker` is running and producing content-value scores and weight-tuning runs. The former R analytics service has been removed; this card replaces it.

**Status indicators:**

- `Running` — HTTP ping to `http-worker-api` health endpoint returns 200 and analytics worker reports healthy.
- `Down` — HTTP ping fails or times out.
- `Stale` — Service is reachable but last content-value computation run was more than N hours ago.
- `Not configured` — Analytics worker is not enabled in settings.

**Displayed fields:**

- Connection status badge.
- Last successful content-value computation run: timestamp + count of content items scored.
- Last weight-tuning run: timestamp + champion weight version promoted (if any).
- Last error: message + timestamp.
- MathNet.Numerics version (from assembly metadata).

**Actions:**

- "Ping Service" — lightweight HTTP health check against `http-worker-api`.
- "Trigger Computation Run" — POST to analytics worker trigger endpoint.

**Alert integration (`FR-019`):**

- Emit `service.analytics_worker_down` when ping fails.
- Emit `service.analytics_worker_stale` when last run is overdue.

---

### 6. Algorithm Pipeline Health Card

**Purpose:** Confirm the main link-suggestion pipeline is running, completing successfully, and producing suggestions.

**Status indicators:**

- `Healthy` — last pipeline run succeeded and produced suggestions.
- `Warning` — last run succeeded but suggestion count dropped significantly vs baseline.
- `Error` — last pipeline run failed.
- `Never run` — no pipeline run recorded yet.

**Displayed fields:**

- Status badge.
- Last pipeline run: start timestamp, end timestamp, duration.
- Suggestions generated in last run: total count.
- Suggestion count delta vs previous run: `+N` or `-N` with percentage.
- Algorithm version active.
- Scoring signals enabled (list of active FR signal modules).
- Last error: message + timestamp.

**Actions:**

- "Run Pipeline Now" — triggers a manual pipeline run.
- "View Pipeline Runs" — links to the Jobs page filtered to pipeline runs.

**Alert integration (`FR-019`):**

- Emit `pipeline.run_failed` on failure.
- Emit `pipeline.suggestion_count_drop` if suggestion count drops more than `suggestion_drop_threshold_pct` (default: 30%) vs the trailing 7-day average.

---

### 7. Auto-Tuning Algorithm Health Card

**Purpose:** Confirm the FR-018 auto-tuning system is in a valid state (only visible once FR-018 is implemented).

**Status indicators:**

- `Active champion` — a dated weight set is promoted and in use.
- `Manual weights` — no promoted model; hand-tuned settings are active.
- `Challenger in shadow` — a challenger is being evaluated alongside the champion.
- `Promotion blocked` — latest challenger did not clear promotion gates.
- `Not enabled` — auto-tuning is disabled.

**Displayed fields:**

- Status badge.
- Active model / weight set: name + promotion date.
- Last training run: timestamp + sample size.
- Challenger state (if any): name, shadow-mode entry date, metrics vs champion.
- Last gate check result: pass/fail per gate.
- Last automatic change: type + timestamp.
- Rollback available: yes/no + rollback target version.

**Actions:**

- "View Adaptation History" — links to the FR-018 history screen.
- "Go to Auto-Tuning Settings".

**Alert integration (`FR-019`):**

- Connects to existing FR-018 promotion/rollback alerts.
- Emit `autotuning.promotion_blocked` when gates fail.

---

### 8. Embedding Model Health Card

**Purpose:** Confirm the active embedding model is downloaded, loaded, and ready.

**Status indicators:**

- `Ready` — model is loaded and usable.
- `Warming` — model is loading into memory.
- `Downloading` — model files are being fetched.
- `Not downloaded` — model is configured but not yet on disk.
- `Failed` — model load failed.

**Displayed fields:**

- Status badge.
- Model name and family.
- Model file size on disk.
- Load time (seconds, from last warmup).
- Last used: timestamp.
- Last error: message + timestamp.

**Actions:**

- "Download Model" — triggers model download if not present.
- "Reload Model" — triggers a warmup cycle.

**Alert integration (`FR-019`):**

- Connects to existing FR-019 model status alerts.

---

### 9. Celery Worker Health Card

**Purpose:** Confirm background task workers are running and the task queue is not backed up.

**Status indicators:**

- `Healthy` — at least one worker is online, queue depth is normal.
- `Warning` — queue depth is elevated.
- `No workers` — no Celery workers are responding.
- `Queue backed up` — queue depth exceeds `celery_queue_depth_warning` threshold (default: 50 tasks).

**Displayed fields:**

- Status badge.
- Active worker count.
- Total tasks in queue (pending + reserved).
- Tasks processed in the last hour.
- Last task completed: type + timestamp.
- Last task failed: type + message + timestamp.

**Actions:**

- No dangerous actions exposed in UI; workers are managed at the OS/Docker level.
- "View Error Log" — links to the error log filtered to recent task failures.

**Alert integration (`FR-019`):**

- Emit `worker.no_workers` when worker ping returns empty.
- Emit `worker.queue_backed_up` when queue depth exceeds threshold.

---

### 10. HttpWorker Service Health Card

**Purpose:** Confirm the .NET 9 HttpWorker microservice (broken-link scanner, URL fetcher, sitemap crawler) is reachable.

**Status indicators:**

- `Running` — HTTP health endpoint returns 200.
- `Down` — ping fails or times out.
- `Not configured` — HttpWorker URL is not set.

**Displayed fields:**

- Status badge.
- HttpWorker base URL.
- Last successful task: type + timestamp.
- Last error: message + timestamp.
- Version / build info (if exposed by the service).

**Actions:**

- "Ping Service" — lightweight HTTP health check.
- "Go to Link Health" — links to the broken-link scanner page.

**Alert integration (`FR-019`):**

- Emit `service.http_worker_down` when ping fails.

---

### 11. Database Health Card

**Purpose:** Confirm the PostgreSQL database is reachable and migrations are current.

**Status indicators:**

- `Healthy` — connection succeeds, all migrations applied.
- `Pending migrations` — unapplied migrations detected.
- `Connection error` — database is unreachable.

**Displayed fields:**

- Status badge.
- Database engine and host (display only, no credentials).
- Migration state: all applied / N pending.
- Last migration applied: name + timestamp.
- DB size on disk (MB).

**Actions:**

- "Check Migrations" — runs a read-only migration state check.
- No destructive database actions exposed in UI.

**Alert integration (`FR-019`):**

- Emit `system.db_connection_error` if DB ping fails.
- Emit `system.pending_migrations` if unapplied migrations are detected.

---

### 12. Redis / Channel Layer Health Card

**Purpose:** Confirm Redis (used by Celery broker and Django Channels) is reachable.

**Status indicators:**

- `Running` — Redis ping returns PONG.
- `Down` — connection refused or timeout.
- `Not configured` — Redis URL not set.

**Displayed fields:**

- Status badge.
- Redis host (display only, no credentials).
- Last successful ping: timestamp.
- Redis memory used (if INFO command is available).

**Actions:**

- "Ping Redis" — PING command check.

**Alert integration (`FR-019`):**

- Emit `system.redis_down` when ping fails.

---

## Backend Design

### New backend app

Add: `backend/apps/health/`

Files:

- `backend/apps/health/models.py`
- `backend/apps/health/services.py`
- `backend/apps/health/views.py`
- `backend/apps/health/serializers.py`
- `backend/apps/health/tasks.py`

### `ServiceHealthRecord` model

Stores the most recent health check result per service.

Fields:

- `service_key` (CharField, unique, indexed)
  - examples: `ga4`, `gsc`, `xenforo`, `wordpress`, `r_analytics`, `pipeline`, `auto_tuning`, `embedding_model`, `celery`, `http_worker`, `database`, `redis`
- `status` (CharField: `healthy`, `warning`, `error`, `down`, `stale`, `not_configured`, `not_enabled`)
- `status_label` (CharField — plain-English one-liner)
- `last_check_at` (DateTimeField)
- `last_success_at` (DateTimeField, null/blank)
- `last_error_at` (DateTimeField, null/blank)
- `last_error_message` (TextField, blank)
- `metadata` (JSONField, default dict — service-specific extra fields)
- `created_at`, `updated_at`

### Health check service

One checker function per card:

```python
check_ga4_health() -> ServiceHealthResult
check_gsc_health() -> ServiceHealthResult
check_xenforo_health() -> ServiceHealthResult
check_wordpress_health() -> ServiceHealthResult
check_r_analytics_health() -> ServiceHealthResult
check_pipeline_health() -> ServiceHealthResult
check_auto_tuning_health() -> ServiceHealthResult
check_embedding_model_health() -> ServiceHealthResult
check_celery_health() -> ServiceHealthResult
check_http_worker_health() -> ServiceHealthResult
check_database_health() -> ServiceHealthResult
check_redis_health() -> ServiceHealthResult
```

Each returns a `ServiceHealthResult` dataclass:

```python
@dataclass
class ServiceHealthResult:
    service_key: str
    status: str
    status_label: str
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_message: str
    metadata: dict
```

### Periodic health check task

- `run_all_health_checks` Celery task:
  - runs all checker functions;
  - upserts `ServiceHealthRecord` rows;
  - emits `FR-019` alerts for any newly-degraded services;
  - resolves alerts for services that have recovered.
  - Default schedule: every 5 minutes.
  - Configurable via `AppSetting`: `health.check_interval_minutes`.

### REST API

- `GET /api/health/status/`
  - returns all `ServiceHealthRecord` rows;
  - summary: overall system health state (`all_healthy`, `some_degraded`, `critical`).

- `GET /api/health/status/<service_key>/`
  - returns a single service card with full metadata.

- `POST /api/health/check/<service_key>/`
  - triggers an immediate health check for one service;
  - returns the updated result.

- `POST /api/health/check-all/`
  - triggers an immediate check for all services.

- `GET /api/settings/health/`
- `PUT /api/settings/health/`
  - `check_interval_minutes` (int, default: 5)
  - `ga4_stale_threshold_hours` (int, default: 72)
  - `gsc_stale_threshold_hours` (int, default: 72)
  - `xenforo_stale_threshold_hours` (int, default: 48)
  - `wordpress_stale_threshold_hours` (int, default: 48)
  - `r_analytics_stale_threshold_hours` (int, default: 24)
  - `celery_queue_depth_warning` (int, default: 50)
  - `pipeline_suggestion_drop_threshold_pct` (int, default: 30)
  - `http_worker_timeout_seconds` (int, default: 5)
  - `redis_timeout_seconds` (int, default: 3)

## Frontend Design

### New page and route

Add route: `/health`

Label in nav: **System Health**

### Page layout

- Top summary bar:
  - overall system status badge: `All systems healthy` / `N services degraded` / `Critical issue detected`
  - last checked: timestamp
  - "Check All Now" button.

- Grid of health cards (12 cards).
  - Card size: compact but readable.
  - Each card: service name, status badge, key metric (last data received or last success), last error (if any), action button(s).
  - Cards with `error`, `down`, or `stale` status are visually highlighted.

- Cards are sorted: errors first, then warnings, then healthy, then not-configured.

### Real-time updates

- Poll `GET /api/health/status/` every 30 seconds while the health page is open.
- Subscribe to `FR-019` WebSocket notification stream to immediately refresh a card when an alert fires.

### Nav link

- Add "System Health" link to the sidebar navigation.
- Add a small status indicator dot next to the nav link when any service is degraded.
- This dot also appears in the top toolbar next to the FR-019 bell icon.

## Alert Integration Summary

| Service | Alert event type | Trigger condition |
|---|---|---|
| GA4 | `data_source.ga4_auth_error` | 401/403 from API |
| GA4 | `data_source.ga4_no_data` | No data for 72h |
| GSC | `data_source.gsc_auth_error` | 401/403 from API |
| GSC | `data_source.gsc_no_data` | No data for 72h |
| XenForo | `data_source.xenforo_sync_error` | Sync failed |
| XenForo | `data_source.xenforo_stale` | Sync overdue |
| WordPress | `data_source.wordpress_sync_error` | Sync failed |
| WordPress | `data_source.wordpress_stale` | Sync overdue |
| R Analytics | `service.r_analytics_down` | Ping failed |
| R Analytics | `service.r_analytics_stale` | No run for 24h |
| Pipeline | `pipeline.run_failed` | Pipeline failed |
| Pipeline | `pipeline.suggestion_count_drop` | >30% drop |
| Auto-Tuning | `autotuning.promotion_blocked` | Gates failed |
| Celery | `worker.no_workers` | No workers |
| Celery | `worker.queue_backed_up` | Queue > 50 |
| HttpWorker | `service.http_worker_down` | Ping failed |
| Database | `system.db_connection_error` | Connection failed |
| Database | `system.pending_migrations` | Unapplied migrations |
| Redis | `system.redis_down` | Ping failed |

All alerts use the `FR-019` `emit_operator_alert()` helper.
All alerts use dedupe keys so a persistently-down service does not flood the alert center.

## Test Plan

### Backend tests

- Each checker function returns the correct status for a healthy service.
- Each checker function returns `error` or `down` when the service is unavailable.
- `ServiceHealthRecord` upserts correctly on repeated checks.
- Periodic task runs all checkers and writes all records.
- API returns all records with correct shape.
- Per-service immediate check endpoint triggers a fresh check and returns updated result.
- Settings API reads and writes all threshold fields.

### Frontend tests

- Health page renders all 12 cards.
- Error/warning cards appear first.
- Status dot appears in nav when any service is degraded.
- "Check All Now" button triggers the check-all endpoint and refreshes the UI.

### Manual verification

- Disable GA4 credentials and verify `ga4` card shows `Auth error` and an FR-019 alert fires.
- Stop the R analytics Docker container and verify `r_analytics` card shows `Down`.
- Let XenForo sync go overdue and verify `xenforo` card shows `Stale`.
- Restore each service and verify card returns to `Healthy` and alert resolves.

## Acceptance Criteria

- Every data source and service has its own health card.
- Each card shows: status, last success, last error, and at least one action.
- The overall system health summary is visible at the top of the page.
- A degraded service creates a `FR-019` alert automatically.
- A recovered service resolves its alert automatically.
- Health checks run on a configurable schedule without user interaction.
- The health page is reachable from the sidebar navigation.
- A status dot in the nav/toolbar makes degraded state visible from any page.

## Out-of-Scope Follow-Up

- Email / SMS / Slack health status notifications (belongs to a later notification channel FR).
- Historical uptime charts and SLA tracking.
- Per-user health check permissions.
- External uptime monitoring integration (Uptime Robot, Better Uptime, etc.).
- Health check API exposed externally for monitoring tools.
