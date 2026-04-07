# FR-093 - Extended Nightly Data Retention

## Confirmation

- **Backlog confirmed**: `FR-093 - Extended Nightly Data Retention` is a pending Tier 1 data retention task.
- **Repo confirmed**: `backend/apps/pipeline/tasks.py` contains the existing `nightly_data_retention` task that deletes stale rows from several tables each night.
- **Repo confirmed**: The 6 tables targeted by FR-093 (`django_celery_results_taskresult`, `notifications_operatoralert`, `sync_syncjob`, `analytics_analyticssyncrun`, `analytics_telemetrycoveragedaily`, `audit_reviewerscorecard`) are not covered by the existing nightly retention task.
- **Repo confirmed**: These 6 tables currently grow without any automatic pruning.

## Engineering Rationale

FR-093 is not derived from a patent. It is a data hygiene task that extends an existing retention mechanism.

The existing `nightly_data_retention` task already prunes several tables (e.g., old pipeline runs, stale suggestions). Six additional tables were missed when the retention task was first written. These tables accumulate rows indefinitely, wasting disk space and slowing queries that scan them.

FR-093 adds 6 new DELETE statements to the existing nightly task, each with a table-appropriate retention period.

## Plain-English Summary

Simple version first.

The system already has a nightly cleanup job that deletes old rows from certain tables. Six tables were left out of that cleanup job, so they grow forever. FR-093 adds those 6 tables to the nightly cleanup, each with its own expiry period: Celery task results after 7 days, resolved operator alerts after 30 days, completed sync jobs after 60 days, analytics sync runs after 90 days, telemetry coverage snapshots after 90 days, and reviewer scorecards after 180 days.

Think of it like adding 6 more items to an existing cleaning checklist.

## Problem Statement

Today 6 tables grow without bounds:

| Table | Growth rate | Current size after 1 year |
|---|---|---|
| `django_celery_results_taskresult` | ~1000 rows/day | ~365,000 rows, ~1.4 GB |
| `notifications_operatoralert` | ~10 rows/day | ~3,600 rows, ~7 MB |
| `sync_syncjob` | ~2 rows/day | ~730 rows, ~730 KB |
| `analytics_analyticssyncrun` | ~2 rows/day | ~730 rows, ~365 KB |
| `analytics_telemetrycoveragedaily` | ~1 row/day | ~365 rows, ~73 KB |
| `audit_reviewerscorecard` | ~0.5 rows/day | ~180 rows, ~90 KB |

Celery task results dominate. After a year without pruning, the task result table alone reaches ~1.4 GB and slows admin queries against it.

## Goals

FR-093 should:

- add 6 DELETE statements to the existing `nightly_data_retention` task;
- use table-appropriate retention periods (7d, 30d, 60d, 90d, 90d, 180d);
- log the number of rows deleted per table per run;
- not affect any table already covered by the existing retention task;
- reclaim ~6-8 GB of disk per year (Celery results dominate).

## Non-Goals

FR-093 does not:

- create a new Celery task (it extends the existing `nightly_data_retention` task);
- change retention periods for any table already in the nightly task;
- prune analytics tables (those are handled by FR-094, a separate weekly task);
- prune suggestion diagnostics JSON (that is handled by FR-096, a separate monthly task);
- add a new settings UI or feature flag;
- change any ranking signal, pipeline algorithm, or frontend component.

## Math-Fidelity Note

### Deletion queries

```sql
-- 1. Celery task results: 7 days
DELETE FROM django_celery_results_taskresult
WHERE date_done < NOW() - INTERVAL '7 days';
-- Row size: ~4 KB (task_name, result JSON, traceback, meta)
-- Growth: ~1000 rows/day
-- Rows deleted per nightly run: ~1000
-- Space reclaimed per run: ~4 MB
-- Yearly savings: ~1.4 GB

-- 2. Resolved operator alerts: 30 days after resolution
DELETE FROM notifications_operatoralert
WHERE resolved_at IS NOT NULL AND resolved_at < NOW() - INTERVAL '30 days';
-- Row size: ~2 KB (message, severity, context JSON)
-- Growth: ~10 resolved alerts/day
-- Rows deleted per nightly run: ~10
-- Space reclaimed per run: ~20 KB
-- Yearly savings: ~7 MB

-- 3. Completed sync jobs: 60 days
DELETE FROM sync_syncjob
WHERE status IN ('completed', 'failed') AND completed_at < NOW() - INTERVAL '60 days';
-- Row size: ~1 KB (job type, timestamps, result summary)
-- Growth: ~2 rows/day
-- Rows deleted per nightly run: ~2
-- Space reclaimed per run: ~2 KB
-- Yearly savings: ~730 KB

-- 4. Analytics sync run audit: 90 days
DELETE FROM analytics_analyticssyncrun
WHERE started_at < NOW() - INTERVAL '90 days';
-- Row size: ~500 bytes (timestamps, row counts, error flag)
-- Growth: ~2 rows/day
-- Rows deleted per nightly run: ~2
-- Space reclaimed per run: ~1 KB
-- Yearly savings: ~365 KB

-- 5. Telemetry coverage daily: 90 days
DELETE FROM analytics_telemetrycoveragedaily
WHERE date < (NOW() - INTERVAL '90 days')::date;
-- Row size: ~200 bytes (date, coverage percentage, counts)
-- Growth: ~1 row/day
-- Rows deleted per nightly run: ~1
-- Space reclaimed per run: ~200 bytes
-- Yearly savings: ~73 KB

-- 6. Reviewer scorecards: 180 days
DELETE FROM audit_reviewerscorecard
WHERE period_end < (NOW() - INTERVAL '180 days')::date;
-- Row size: ~500 bytes (reviewer ID, period dates, scores)
-- Growth: ~0.5 rows/day (biweekly scorecards)
-- Rows deleted per nightly run: ~0-1
-- Space reclaimed per run: ~0-500 bytes
-- Yearly savings: ~90 KB
```

### Total yearly savings

```
Celery task results:       ~1.4 GB
Operator alerts:           ~7 MB
Sync jobs:                 ~730 KB
Analytics sync runs:       ~365 KB
Telemetry coverage:        ~73 KB
Reviewer scorecards:       ~90 KB
---
Total:                     ~1.4 GB/year (conservative)
                           ~6-8 GB/year (including index bloat reclaimed by VACUUM)
```

### Retention period rationale

| Table | Period | Why |
|---|---|---|
| Celery TaskResult | 7d | Task results are debugging artifacts. After 7 days they have no operational value. |
| OperatorAlert | 30d | Resolved alerts are historical. 30 days gives enough lookback for trend analysis. |
| SyncJob | 60d | Completed/failed syncs are audit trails. 60 days covers two full monthly review cycles. |
| AnalyticsSyncRun | 90d | Sync run metadata supports quarterly performance reviews. |
| TelemetryCoverageDaily | 90d | Daily coverage snapshots support quarterly trend analysis. |
| ReviewerScorecard | 180d | Scorecards cover 6-month performance reviews. |

## Scope Boundary

FR-093 must stay separate from:

- **Existing nightly retention** -- FR-093 adds new DELETE statements but does not modify or remove any existing ones.
- **FR-094** (weekly analytics pruning) -- FR-094 handles heavy analytics tables on a weekly schedule. FR-093 handles lightweight operational tables nightly.
- **FR-095** (quarterly database maintenance) -- FR-095 does VACUUM FULL and REINDEX. FR-093 only does DELETE.
- **FR-096** (monthly safe prune) -- FR-096 prunes BrokenLink, ImpactReport, and diagnostics JSON. FR-093 prunes Celery results, alerts, sync jobs, and scorecards. Zero table overlap.

Hard rule: FR-093 must not modify any existing retention period or delete from any table not listed above.

## Inputs Required

FR-093 uses only data already available:

- `backend/apps/pipeline/tasks.py` -- the existing `nightly_data_retention` task (extended with 6 new DELETE statements)
- The 6 target tables -- all already exist in the database with standard Django models

Explicitly disallowed inputs:

- No new models or migrations
- No new settings keys
- No API or frontend changes

## Settings And Feature-Flag Plan

No new operator-facing settings. The retention periods are hardcoded in the task, matching the pattern used by the existing retention statements in `nightly_data_retention`.

If an operator needs to change a retention period, they modify the INTERVAL value in the task code. This is intentionally not a runtime setting because retention periods are operational policy, not tuning knobs.

## Diagnostics And Explainability Plan

### Log output per run

Each DELETE statement logs the number of rows deleted:

```
[Retention] Celery TaskResult: deleted 1,043 rows older than 7 days
[Retention] OperatorAlert (resolved): deleted 12 rows older than 30 days
[Retention] SyncJob (completed/failed): deleted 2 rows older than 60 days
[Retention] AnalyticsSyncRun: deleted 1 row older than 90 days
[Retention] TelemetryCoverageDaily: deleted 1 row older than 90 days
[Retention] ReviewerScorecard: deleted 0 rows older than 180 days
[Retention] Tier 1 complete. Total deleted: 1,059 rows.
```

### Error handling

If any single DELETE fails (e.g., foreign key constraint), the task logs the error and continues to the next table. It does not abort the entire retention run.

## Storage / Model / API Impact

### Suggestion model

No changes.

### Content model

No changes.

### Database models

No changes. All 6 target tables already exist.

### Migrations

No new migrations needed.

### Backend API

No changes.

### Frontend

No changes.

## Backend Service Touch Points

Implementation files:

- `backend/apps/pipeline/tasks.py` -- add 6 DELETE statements inside the existing `nightly_data_retention` task

Files that must stay untouched:

- All model files (no schema changes)
- All ranking, scoring, and signal files
- All frontend files
- The Celery beat schedule in `settings/base.py` (the nightly task is already scheduled)

## Test Plan

### 1. Celery TaskResult pruning

- Insert 100 TaskResult rows with `date_done` set to 8 days ago.
- Run `nightly_data_retention`.
- Verify all 100 rows are deleted.
- Verify TaskResult rows from today are untouched.

### 2. OperatorAlert pruning (resolved only)

- Insert 10 resolved alerts with `resolved_at` set to 31 days ago.
- Insert 5 unresolved alerts with `created_at` set to 60 days ago.
- Run `nightly_data_retention`.
- Verify 10 resolved alerts are deleted.
- Verify 5 unresolved alerts are untouched (no `resolved_at`, so they are kept regardless of age).

### 3. SyncJob pruning (completed/failed only)

- Insert 5 completed jobs with `completed_at` set to 61 days ago.
- Insert 3 running jobs with `started_at` set to 90 days ago.
- Run `nightly_data_retention`.
- Verify 5 completed jobs are deleted.
- Verify 3 running jobs are untouched (status is not 'completed' or 'failed').

### 4. Row count logging

- Run `nightly_data_retention` on a database with known row counts.
- Verify log output matches expected deletion counts.

### 5. Error isolation

- Temporarily add a foreign key constraint that would block one DELETE.
- Run `nightly_data_retention`.
- Verify the blocked DELETE logs an error but all other DELETEs still run.

### 6. Existing retention unaffected

- Verify that all existing DELETE statements in `nightly_data_retention` still execute with the same logic and retention periods as before.

## Risk List

- The Celery TaskResult table may have a large backlog on first run (e.g., 365,000 rows if the table has never been pruned). The first DELETE may take 30-60 seconds. Subsequent runs delete ~1,000 rows and take <1 second.
- Foreign key constraints on any of the 6 tables could block deletion. Mitigation: the task catches exceptions per-table and continues. The operator sees the error in logs and can investigate.
- Deleting resolved OperatorAlerts means they cannot be referenced in historical reports. Mitigation: 30 days is enough lookback; older alerts have no operational value.
